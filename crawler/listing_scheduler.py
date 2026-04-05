"""
당근 전국 매물 수집 스케줄러

매 1분마다 실행:
  1. Redis에서 279개 구/군 목록 로드
  2. 전국 매물 병렬 수집 (20개씩 배치, rate limit 적응형 delay)
  3. Redis seen_ids와 비교 → 새 매물 감지
  4. 1분 이내 등록된 새 매물 필터
  5. 키워드 매칭 → 알림 발송

새 매물 감지: seen_ids 비교로 "이전에 없던 매물"을 감지한 뒤,
createdAt 기준 1분 이내 등록된 매물만 알림 대상으로 필터링한다.

Redis 키:
  daangn:listing:seen:{regionId}  — 구/군별 확인된 매물 ID 목록 (TTL 24h)
  daangn:listing:last_run         — 최근 수집 상태 요약
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import aiohttp
import redis

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────────────────────────────

SEARCH_DATA_URL = "https://www.daangn.com/kr/buy-sell/s/"

CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "application/json",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

BATCH_SIZE = 50
TTL_24H = 86400
INTERVAL_MINUTES = 1
MAX_RETRY = 2

KST = timezone(timedelta(hours=9))

# ── Redis 연결 ────────────────────────────────────────────────────────────────

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

try:
    _redis = redis.from_url(_REDIS_URL, decode_responses=True)
    _redis.ping()
    logger.info("[listing_scheduler] Redis 연결 성공: %s", _REDIS_URL)
except Exception as e:
    logger.warning("[listing_scheduler] Redis 연결 실패: %s", e)
    _redis = None


# ── 매물 수집 ─────────────────────────────────────────────────────────────────


async def _fetch_listings_for_district(
    session: aiohttp.ClientSession, region_id: int
) -> tuple[int, list[dict], bool, bool]:
    """
    단일 구/군의 최신 매물 수집 (Remix _data loader로 JSON 직접 수신).

    Returns: (region_id, articles, rate_limited, ok)
    """
    try:
        params = {
            "in": region_id,
            "_data": "routes/kr.buy-sell.s",
        }
        timeout = aiohttp.ClientTimeout(total=3)
        async with session.get(SEARCH_DATA_URL, params=params, timeout=timeout) as resp:
            if resp.status == 429:
                return region_id, [], True, False
            if resp.status != 200:
                return region_id, [], False, False

            data = await resp.json(content_type=None)
            if not data:
                return region_id, [], False

        articles = (
            data.get("allPage", {})
            .get("fleamarketArticles", [])
        )
        # HTTP 200이면 articles=[]이어도 성공 (매물이 없는 지역)
        return region_id, articles, False, True

    except Exception as e:
        logger.warning("[listing_scheduler] 매물 수집 실패 (regionId=%s): %s", region_id, e)
        return region_id, [], False, False


async def _collect_all_listings(districts: list[dict]) -> dict[int, list[dict]]:
    """
    전국 구/군 매물을 배치로 병렬 수집.

    100% 성공을 목표로 최대 MAX_RETRY회 재시도.
    Rate limit(429) 감지 시 delay를 자동 증가.
    """
    all_results = {}
    pending_ids = [d["regionId"] for d in districts]
    delay = 0.5

    connector = aiohttp.TCPConnector(limit=BATCH_SIZE)
    async with aiohttp.ClientSession(
        connector=connector, headers=HEADERS
    ) as session:

        for attempt in range(1, MAX_RETRY + 1):
            if not pending_ids:
                break

            batch_size = BATCH_SIZE if attempt <= 2 else max(5, BATCH_SIZE // attempt)
            total_batches = (len(pending_ids) + batch_size - 1) // batch_size
            next_pending = []
            rate_limited_count = 0

            for i in range(0, len(pending_ids), batch_size):
                batch_ids = pending_ids[i : i + batch_size]
                tasks = [
                    _fetch_listings_for_district(session, rid)
                    for rid in batch_ids
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                batch_success = 0
                for r in results:
                    if isinstance(r, tuple) and len(r) == 4:
                        region_id, articles, rate_limited, ok = r
                        if ok:
                            all_results[region_id] = articles
                            batch_success += 1
                        elif rate_limited:
                            next_pending.append(region_id)
                            rate_limited_count += 1
                        else:
                            next_pending.append(region_id)

                batch_num = i // batch_size + 1
                if attempt == 1 and batch_num % 3 == 0:
                    logger.info(
                        "[listing_scheduler] 수집 %d/%d 배치 (%d건 성공)",
                        batch_num, total_batches, len(all_results),
                    )

                # Rate limit 감지 시 delay 증가
                if rate_limited_count > 0 and delay < 3.0:
                    delay = min(delay + 0.3, 3.0)

                if i + batch_size < len(pending_ids):
                    await asyncio.sleep(delay)

            logger.info(
                "[listing_scheduler] %d차 수집 완료: 성공 %d / 실패 %d (rate-limited %d), delay=%.1fs",
                attempt, len(all_results), len(next_pending), rate_limited_count, delay,
            )

            pending_ids = next_pending
            if pending_ids:
                wait = 3.0 * attempt
                logger.info("[listing_scheduler] %.0f초 대기 후 %d개 재시도", wait, len(pending_ids))
                await asyncio.sleep(wait)
                delay = max(1.5, delay)

    if pending_ids:
        logger.warning(
            "[listing_scheduler] %d개 구/군 수집 실패 (최대 재시도 초과)", len(pending_ids)
        )

    return all_results


# ── 새 매물 감지 ──────────────────────────────────────────────────────────────


def _detect_new_listings(region_id: int, articles: list[dict]) -> list[dict]:
    """Redis seen_ids와 비교하여 새 매물 감지"""
    if not _redis or not articles:
        return []

    seen_key = f"daangn:listing:seen:{region_id}"
    seen_raw = _redis.get(seen_key)
    seen_ids = set(json.loads(seen_raw)) if seen_raw else set()

    current_ids = {a["id"] for a in articles}
    new_ids = current_ids - seen_ids

    new_articles = [a for a in articles if a["id"] in new_ids]

    # seen_ids 갱신
    _redis.setex(seen_key, TTL_24H, json.dumps(list(current_ids), ensure_ascii=False))

    return new_articles


# ── 1분 이내 매물 필터 ────────────────────────────────────────────────────────


def _filter_recent(articles: list[dict], minutes: int = INTERVAL_MINUTES) -> list[dict]:
    """createdAt 기준으로 최근 N분 이내 등록된 매물만 반환"""
    now = datetime.now(KST)
    cutoff = now - timedelta(minutes=minutes)
    recent = []

    for a in articles:
        created_str = a.get("createdAt", "")
        if not created_str:
            continue
        try:
            created = datetime.fromisoformat(created_str)
            if created >= cutoff:
                recent.append(a)
        except (ValueError, TypeError):
            continue

    return recent


# ── 키워드 매칭 ───────────────────────────────────────────────────────────────


def _match_keywords(articles: list[dict], keyword: str) -> list[dict]:
    """매물 목록에서 키워드가 포함된 매물 필터링"""
    keyword_lower = keyword.lower()
    matched = []
    for a in articles:
        text = f"{a.get('title', '')} {a.get('content', '')}".lower()
        if keyword_lower in text:
            matched.append(a)
    return matched


# ── 메인 수집 함수 ────────────────────────────────────────────────────────────


def collect_listings(test_keyword: str | None = None) -> dict:
    """
    전국 매물 수집 → seen_ids 기반 새 매물 감지 → 1분 이내 필터 → 키워드 매칭.

    Args:
        test_keyword: 테스트용 키워드. 지정 시 새 매물 중 매칭 결과도 반환.

    Returns:
        수집 결과 요약 dict
    """
    if not _redis:
        logger.error("[listing_scheduler] Redis 연결 없음 — 수집 중단")
        return {"error": "Redis 연결 없음"}

    start_time = time.time()

    # 1. 구/군 목록 로드
    districts_json = _redis.get("daangn:districts:all")
    if not districts_json:
        logger.error("[listing_scheduler] 구/군 목록 없음 — 지역 스케줄러 실행 필요")
        return {"error": "구/군 목록 없음 (daangn:districts:all)"}

    districts = json.loads(districts_json)

    # 2. 전국 매물 수집
    all_listings = asyncio.run(_collect_all_listings(districts))

    # 3. 새 매물 감지 (seen_ids 비교)
    total_articles = 0
    total_new = 0
    all_new_articles = []

    for region_id, articles in all_listings.items():
        total_articles += len(articles)
        new_articles = _detect_new_listings(region_id, articles)
        if new_articles:
            total_new += len(new_articles)
            all_new_articles.extend(new_articles)

    # 4. 1분 이내 등록된 새 매물만 필터
    recent_articles = _filter_recent(all_new_articles, INTERVAL_MINUTES)

    duration = round(time.time() - start_time, 2)

    # 5. 키워드 매칭 (1분 이내 새 매물 대상)
    keyword_matched = []
    if test_keyword and recent_articles:
        keyword_matched = _match_keywords(recent_articles, test_keyword)

    # ── 알림 발송 (1분 이내 + 키워드 매칭된 매물만) ──
    # TODO: DB에서 사용자 등록 키워드 목록 조회
    # TODO: 매칭된 매물에 대해 FCM 알림 발송
    # if keyword_matched:
    #     for article in keyword_matched:
    #         notification = {
    #             "title": f"[당근] {article.get('title', '')}",
    #             "body": f"{article.get('price')}원 · {article.get('user', {}).get('region', {}).get('name', '')}",
    #             "data": {
    #                 "url": article.get("href", ""),
    #                 "platform": "daangn",
    #                 "keyword": test_keyword,
    #                 "price": article.get("price"),
    #                 "region": article.get("user", {}).get("region", {}).get("name", ""),
    #             },
    #         }
    #         # send_fcm_notification(user_fcm_token, notification)
    #         # save_notification_history(user_id, article["id"], notification)

    # 수집 상태 Redis에 저장
    last_run = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "districts_checked": len(districts),
        "districts_success": len(all_listings),
        "total_articles": total_articles,
        "new_listings": total_new,
        "recent_listings": len(recent_articles),
        "duration_seconds": duration,
    }
    _redis.set("daangn:listing:last_run", json.dumps(last_run, ensure_ascii=False))

    logger.info(
        "[listing_scheduler] 수집 완료: %d/%d 구/군, 전체 %d건, 새 매물 %d건, 1분 이내 %d건, 소요 %.1f초",
        len(all_listings),
        len(districts),
        total_articles,
        total_new,
        len(recent_articles),
        duration,
    )

    result = {
        **last_run,
        "keyword_test": None,
    }

    if test_keyword:
        result["keyword_test"] = {
            "keyword": test_keyword,
            "total_new": total_new,
            "recent_count": len(recent_articles),
            "matched_count": len(keyword_matched),
            "matched_items": [
                {
                    "title": a.get("title", ""),
                    "price": a.get("price"),
                    "region": a.get("user", {}).get("region", {}).get("name", ""),
                    "createdAt": a.get("createdAt", ""),
                    "href": a.get("href", ""),
                }
                for a in keyword_matched[:20]
            ],
        }

    return result


# ── APScheduler 등록 ──────────────────────────────────────────────────────────


def create_listing_scheduler():
    """스케줄러 인스턴스 생성 및 job 등록 (매분 정각 실행)"""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        collect_listings,
        trigger=CronTrigger(second=0),  # 매분 00초에 실행
        id="daangn_listing_collector",
        name="당근 전국 매물 수집 및 알림",
        replace_existing=True,
        max_instances=1,
    )
    return scheduler


# ── 직접 실행 (1분 주기 스케줄러) ─────────────────────────────────────────────


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # 테스트 키워드 (환경변수 또는 기본값)
    test_keyword = os.getenv("TEST_KEYWORD", "닌텐도")

    logger.info("[listing_scheduler] 스케줄러 시작 (주기: %d분, 키워드: %s)", INTERVAL_MINUTES, test_keyword)

    # 최초 1회 즉시 실행 (seen_ids 초기화)
    logger.info("[listing_scheduler] === 최초 수집 (seen_ids 초기화) ===")
    result = collect_listings(test_keyword=test_keyword)
    logger.info("[listing_scheduler] 초기화 완료: %d/%d 구/군, 새 매물 %d건",
                result.get("districts_success", 0),
                result.get("districts_checked", 0),
                result.get("new_listings", 0))

    # APScheduler CronTrigger로 매분 정각 실행
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BlockingScheduler()
    scheduler.add_job(
        collect_listings,
        trigger=CronTrigger(second=0),  # 매분 00초에 실행
        id="daangn_listing_collector",
        name="당근 전국 매물 수집 및 알림",
        kwargs={"test_keyword": test_keyword},
        replace_existing=True,
        max_instances=1,
    )

    logger.info("[listing_scheduler] 스케줄러 등록 완료. 매분 정각에 수집합니다. (Ctrl+C로 종료)")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[listing_scheduler] 스케줄러 종료")
