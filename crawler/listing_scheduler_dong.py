"""
당근 전국 매물 수집 스케줄러 (동 레벨 HTML 파싱 방식)

구 레벨 _data API(listing_scheduler.py)가 불안정할 때 사용하는 대체 스케줄러.
동(name3Id) 단위로 HTML을 파싱하여 매물을 수집한다.

매 5분마다 실행:
  1. Redis에서 279개 구/군 → 8,208개 동 목록 로드
  2. 동 단위 병렬 수집 (구별로 순차, 구 내 동은 병렬)
  3. Redis seen_ids와 비교 → 새 매물 감지
  4. 키워드 매칭 → 알림 발송

특징:
  - 동 레벨 HTML 파싱 (Remix __remixContext) — 안정적
  - 구 단위 배치 + 딜레이로 429 방지
  - 전국 ~4분 30초 소요 → 5분 주기 적합

Redis 키:
  daangn:listing_dong:seen:{regionId}  — 구/군별 확인된 매물 ID 목록 (TTL 24h)
  daangn:listing_dong:last_run         — 최근 수집 상태 요약
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

import aiohttp
import redis

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────────────────────────────

SEARCH_URL = "https://www.daangn.com/kr/buy-sell/s/"

CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.daangn.com/",
}

BATCH_SIZE_PER_DISTRICT = 30  # 구 내 동 동시 요청 수
DISTRICT_DELAY = 0.2          # 구 사이 딜레이 (초)
TTL_24H = 86400
INTERVAL_MINUTES = 5
MAX_RETRY = 3
DISTRICTS_PER_RUN = 50        # 1회 실행당 처리할 구 수 (라운드 로빈)

KST = timezone(timedelta(hours=9))

_REMIX_RE = re.compile(r"window\.__remixContext\s*=\s*(\{.*?\})\s*;", re.DOTALL)

STATUS_MAP = {
    "Ongoing": "판매중",
    "Reserved": "예약중",
    "Completed": "거래완료",
}

# ── Redis 연결 ────────────────────────────────────────────────────────────────

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

try:
    _redis = redis.from_url(_REDIS_URL, decode_responses=True)
    _redis.ping()
    logger.info("[listing_dong] Redis 연결 성공: %s", _REDIS_URL)
except Exception as e:
    logger.warning("[listing_dong] Redis 연결 실패: %s", e)
    _redis = None


# ── HTML 파싱 ────────────────────────────────────────────────────────────────


def _parse_items_from_html(html: str) -> list[dict]:
    """Remix __remixContext에서 매물 목록 파싱"""
    m = _REMIX_RE.search(html)
    if not m:
        return []

    try:
        ctx = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []

    loader_data = ctx.get("state", {}).get("loaderData", {})
    route_data = loader_data.get("routes/kr.buy-sell.s", {})
    articles = route_data.get("allPage", {}).get("fleamarketArticles", [])

    items = []
    for a in articles:
        price_raw = a.get("price")
        if isinstance(price_raw, str):
            price_raw = re.sub(r"[^\d]", "", price_raw)
            price_raw = int(price_raw) if price_raw else 0
        elif price_raw is None:
            price_raw = 0

        status_raw = a.get("status", "")
        status = STATUS_MAP.get(status_raw, status_raw)

        items.append({
            "id": a.get("id", ""),
            "title": a.get("title", ""),
            "price": price_raw,
            "status": status,
            "image_url": a.get("thumbnail", ""),
            "href": a.get("href", ""),
            "createdAt": a.get("createdAt", ""),
            "content": a.get("content", ""),
            "user": a.get("user", {}),
        })

    return items


# ── 동 단위 수집 ─────────────────────────────────────────────────────────────


async def _fetch_dong(
    session: aiohttp.ClientSession, dong_id: int
) -> tuple[int, list[dict], bool]:
    """
    단일 동의 최신 매물 수집 (HTML 파싱).

    Returns: (dong_id, items, rate_limited)
    """
    params = {"in": dong_id}
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.get(SEARCH_URL, params=params, timeout=timeout) as resp:
            if resp.status == 429:
                return dong_id, [], True
            if resp.status != 200:
                return dong_id, [], False
            html = await resp.text(encoding="utf-8")
    except Exception:
        return dong_id, [], False

    items = _parse_items_from_html(html)
    return dong_id, items, False


DISTRICT_BATCH_COOLDOWN = 3.0  # 구 배치 사이 쿨다운 (초)


async def _collect_one_district(
    session: aiohttp.ClientSession, region_id: int
) -> tuple[int, list[dict], bool]:
    """단일 구의 하위 동 매물을 배치로 수집."""
    dongs_raw = _redis.get(f"daangn:dongs:{region_id}") if _redis else None
    if not dongs_raw:
        return region_id, [], False

    dongs = json.loads(dongs_raw)
    dong_ids = [x["name3Id"] for x in dongs if x.get("name3Id")]
    if not dong_ids:
        return region_id, [], False

    seen_ids: set[str] = set()
    items: list[dict] = []
    rate_limited = False

    for bi in range(0, len(dong_ids), BATCH_SIZE_PER_DISTRICT):
        batch_dongs = dong_ids[bi:bi + BATCH_SIZE_PER_DISTRICT]
        tasks = [_fetch_dong(session, did) for did in batch_dongs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                continue
            _, dong_items, rl = r
            if rl:
                rate_limited = True
            for item in dong_items:
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    items.append(item)

        if bi + BATCH_SIZE_PER_DISTRICT < len(dong_ids):
            await asyncio.sleep(0.15)

    return region_id, items, rate_limited


async def _collect_all_listings_dong(districts: list[dict]) -> dict[int, list[dict]]:
    """
    구/군의 하위 동 매물을 순차 수집.

    429 방지를 위해 구 사이 딜레이 + 일정 구 수마다 쿨다운.
    전체 구를 한 번에 처리하지 않고 DISTRICTS_PER_RUN개만 처리 (라운드 로빈).
    """
    all_results: dict[int, list[dict]] = {}
    pending = list(districts)

    connector = aiohttp.TCPConnector(limit=BATCH_SIZE_PER_DISTRICT)
    async with aiohttp.ClientSession(
        connector=connector, headers=HEADERS
    ) as session:

        for attempt in range(1, MAX_RETRY + 1):
            if not pending:
                break

            next_pending = []

            for idx, d in enumerate(pending):
                region_id = d["regionId"]
                if region_id in all_results:
                    continue

                rid, items, rl = await _collect_one_district(session, region_id)
                if rl:
                    next_pending.append(d)
                else:
                    all_results[rid] = items

                await asyncio.sleep(DISTRICT_DELAY)

                # 20개 구마다 쿨다운
                if (idx + 1) % 20 == 0 and idx + 1 < len(pending):
                    await asyncio.sleep(DISTRICT_BATCH_COOLDOWN)

            logger.info(
                "[listing_dong] %d차: 성공 %d / 실패 %d",
                attempt, len(all_results), len(next_pending),
            )

            pending = next_pending
            if pending and attempt < MAX_RETRY:
                wait = 15.0 * attempt
                logger.info("[listing_dong] %.0f초 대기 후 %d개 재시도", wait, len(pending))
                await asyncio.sleep(wait)

        if pending:
            logger.warning(
                "[listing_dong] %d개 구 수집 실패 (최대 재시도 초과)", len(pending)
            )
            for d in pending:
                all_results.setdefault(d["regionId"], [])

    return all_results


# ── 새 매물 감지 ──────────────────────────────────────────────────────────────


def _detect_new_listings(region_id: int, articles: list[dict]) -> list[dict]:
    """Redis seen_ids와 비교하여 새 매물 감지"""
    if not _redis or not articles:
        return []

    seen_key = f"daangn:listing_dong:seen:{region_id}"
    seen_raw = _redis.get(seen_key)
    seen_ids = set(json.loads(seen_raw)) if seen_raw else set()

    current_ids = {a["id"] for a in articles}
    new_ids = current_ids - seen_ids

    new_articles = [a for a in articles if a["id"] in new_ids]

    # seen_ids 갱신
    _redis.setex(seen_key, TTL_24H, json.dumps(list(current_ids), ensure_ascii=False))

    return new_articles


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


def collect_listings_dong(test_keyword: str | None = None) -> dict:
    """
    전국 매물 수집 (동 레벨 HTML 파싱) → seen_ids 기반 새 매물 감지 → 키워드 매칭.

    Args:
        test_keyword: 테스트용 키워드. 지정 시 새 매물 중 매칭 결과도 반환.

    Returns:
        수집 결과 요약 dict
    """
    if not _redis:
        logger.error("[listing_dong] Redis 연결 없음 — 수집 중단")
        return {"error": "Redis 연결 없음"}

    start_time = time.time()

    # 1. 구/군 목록 로드
    districts_json = _redis.get("daangn:districts:all")
    if not districts_json:
        logger.error("[listing_dong] 구/군 목록 없음 — 지역 스케줄러 실행 필요")
        return {"error": "구/군 목록 없음 (daangn:districts:all)"}

    districts = json.loads(districts_json)

    # 2. 라운드 로빈: 이번 회차에 처리할 구 선택
    round_key = "daangn:listing_dong:round_offset"
    offset = int(_redis.get(round_key) or 0)
    target_districts = districts[offset:offset + DISTRICTS_PER_RUN]
    next_offset = offset + DISTRICTS_PER_RUN
    if next_offset >= len(districts):
        next_offset = 0
    _redis.set(round_key, str(next_offset))

    logger.info(
        "[listing_dong] 라운드 로빈: offset=%d, 이번 %d개 구 수집 (전체 %d개)",
        offset, len(target_districts), len(districts),
    )

    # 3. 매물 수집 (동 레벨)
    all_listings = asyncio.run(_collect_all_listings_dong(target_districts))

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

    duration = round(time.time() - start_time, 2)

    # 4. 키워드 매칭 (새 매물 대상)
    keyword_matched = []
    if test_keyword and all_new_articles:
        keyword_matched = _match_keywords(all_new_articles, test_keyword)

    # ── 알림 발송 (키워드 매칭된 매물) ──
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
    #             },
    #         }
    #         # send_fcm_notification(user_fcm_token, notification)

    # 수집 상태 Redis에 저장
    last_run = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": "dong",
        "districts_checked": len(districts),
        "districts_success": len([v for v in all_listings.values() if v]),
        "total_articles": total_articles,
        "new_listings": total_new,
        "duration_seconds": duration,
    }
    _redis.set("daangn:listing_dong:last_run", json.dumps(last_run, ensure_ascii=False))

    logger.info(
        "[listing_dong] 수집 완료: %d/%d 구/군, 전체 %d건, 새 매물 %d건, 소요 %.1f초",
        last_run["districts_success"],
        len(districts),
        total_articles,
        total_new,
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


def create_listing_dong_scheduler():
    """스케줄러 인스턴스 생성 및 job 등록 (5분 주기)"""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        collect_listings_dong,
        trigger=CronTrigger(minute="*/5", second=0),  # 매 5분 정각
        id="daangn_listing_dong_collector",
        name="당근 전국 매물 수집 (동 레벨)",
        replace_existing=True,
        max_instances=1,
    )
    return scheduler


# ── 직접 실행 ─────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    test_keyword = os.getenv("TEST_KEYWORD", "닌텐도")

    logger.info("[listing_dong] 스케줄러 시작 (주기: %d분, 키워드: %s)", INTERVAL_MINUTES, test_keyword)

    # 최초 1회 즉시 실행 (seen_ids 초기화)
    logger.info("[listing_dong] === 최초 수집 (seen_ids 초기화) ===")
    result = collect_listings_dong(test_keyword=test_keyword)
    logger.info(
        "[listing_dong] 초기화 완료: %d/%d 구/군, 전체 %d건, 소요 %.1f초",
        result.get("districts_success", 0),
        result.get("districts_checked", 0),
        result.get("total_articles", 0),
        result.get("duration_seconds", 0),
    )

    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BlockingScheduler()
    scheduler.add_job(
        collect_listings_dong,
        trigger=CronTrigger(minute="*/5", second=0),
        id="daangn_listing_dong_collector",
        name="당근 전국 매물 수집 (동 레벨)",
        kwargs={"test_keyword": test_keyword},
        replace_existing=True,
        max_instances=1,
    )

    logger.info("[listing_dong] 스케줄러 등록 완료. 매 5분 정각에 수집합니다. (Ctrl+C로 종료)")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[listing_dong] 스케줄러 종료")
