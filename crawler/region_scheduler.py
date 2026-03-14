"""
당근 전국 지역 데이터 수집 스케줄러

매일 새벽 4시 실행:
  1단계: https://www.daangn.com/kr/regions/ 에서 시/도 + 구/군 수집
  2단계: 각 구/군의 동/읍/면 정보를 Location API로 40개씩 병렬 수집

Redis 키:
  daangn:regions:all       — 시/도 + 구/군 계층 목록 (TTL 48h)
  daangn:districts:all     — 구/군 플랫 리스트 (TTL 48h)
  daangn:dongs:{regionId}  — 구/군별 동 목록 (TTL 48h)
  daangn:location:{name}   — 기존 location 캐시 갱신 (TTL 24h)
"""

import asyncio
import json
import logging
import os
import re

import aiohttp
import redis
import requests

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────────────────────────────

REGIONS_URL = "https://www.daangn.com/kr/regions/"
LOCATION_API_URL = "https://www.daangn.com/v1/api/search/kr/location"

CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

LOCATION_API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.daangn.com/",
    "User-Agent": CHROME_UA,
}

BATCH_SIZE = 50
TTL_48H = 86400 * 2
TTL_24H = 86400

_REMIX_RE = re.compile(r"window\.__remixContext\s*=\s*(\{.*?\})\s*;", re.DOTALL)

# ── Redis 연결 ────────────────────────────────────────────────────────────────

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

try:
    _redis = redis.from_url(_REDIS_URL, decode_responses=True)
    _redis.ping()
    logger.info("[region_scheduler] Redis 연결 성공: %s", _REDIS_URL)
except Exception as e:
    logger.warning("[region_scheduler] Redis 연결 실패: %s", e)
    _redis = None


# ── 1단계: regions 페이지에서 시/도 + 구/군 수집 ──────────────────────────────


def _fetch_regions_page() -> dict:
    """당근 regions 페이지에서 remixContext JSON 추출"""
    resp = requests.get(REGIONS_URL, headers=HEADERS, timeout=15)
    resp.encoding = "utf-8"
    resp.raise_for_status()

    match = _REMIX_RE.search(resp.text)
    if not match:
        raise ValueError("remixContext를 찾을 수 없습니다.")

    return json.loads(match.group(1))


def _parse_regions(remix_data: dict) -> tuple[list[dict], list[dict]]:
    """remixContext에서 시/도(provinces) + 구/군(districts) 파싱"""
    provinces = []
    districts = []

    # remixContext 내 지역 데이터 경로: routes/kr.regions._index > allRegions
    loader_data = remix_data.get("state", {}).get("loaderData", {})
    regions_data = loader_data.get("routes/kr.regions._index", {})
    regions = regions_data.get("allRegions")

    if not regions:
        raise ValueError(
            "remixContext에서 allRegions 데이터를 찾을 수 없습니다. "
            f"loaderData keys: {list(loader_data.keys())}"
        )

    for province in regions:
        province_name = province.get("regionName", "")
        province_info = {
            "name": province_name,
            "depth": 1,
            "districts": [],
        }
        for child in province.get("childrenRegion", []):
            district_info = {
                "regionId": child.get("regionId"),
                "name": child.get("regionName", ""),
                "province": province_name,
                "depth": 2,
            }
            province_info["districts"].append(district_info)
            districts.append(district_info)
        provinces.append(province_info)

    return provinces, districts


# ── 2단계: 동/읍/면 수집 (20개씩 병렬) ─────────────────────────────────────────


async def _fetch_dongs_for_district(
    session: aiohttp.ClientSession, district: dict
) -> tuple[str, int]:
    """단일 구/군의 동 목록을 비동기로 수집하여 Redis에 저장"""
    name = district["name"]
    region_id = district["regionId"]

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.get(
            LOCATION_API_URL, params={"keyword": name}, timeout=timeout
        ) as resp:
            body = await resp.json()

        locations = body.get("locations", [])
        dong_list = [loc for loc in locations if loc.get("depth") == 3]

        if _redis:
            # 구/군별 동 목록 저장
            _redis.set(
                f"daangn:dongs:{region_id}",
                json.dumps(dong_list, ensure_ascii=False),
                ex=TTL_48H,
            )
            # 기존 location 캐시도 갱신
            _redis.setex(
                f"daangn:location:{name}",
                TTL_24H,
                json.dumps(locations, ensure_ascii=False),
            )

        return name, len(dong_list)

    except Exception as e:
        logger.error("동 수집 실패 [%s]: %s", name, e)
        return name, -1


async def _collect_dongs_in_batches(districts: list[dict]):
    """구/군 목록을 BATCH_SIZE(20)개씩 나누어 병렬 수집"""
    total_batches = (len(districts) + BATCH_SIZE - 1) // BATCH_SIZE
    total_success = 0
    total_fail = 0

    connector = aiohttp.TCPConnector(limit=BATCH_SIZE)
    async with aiohttp.ClientSession(
        connector=connector, headers=LOCATION_API_HEADERS
    ) as session:
        for i in range(0, len(districts), BATCH_SIZE):
            batch = districts[i : i + BATCH_SIZE]
            tasks = [_fetch_dongs_for_district(session, d) for d in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            batch_success = 0
            for r in results:
                if isinstance(r, tuple) and r[1] >= 0:
                    batch_success += 1
                else:
                    total_fail += 1

            total_success += batch_success
            batch_num = i // BATCH_SIZE + 1
            logger.info(
                "[region_scheduler] 배치 %d/%d 완료 (%d/%d 성공)",
                batch_num,
                total_batches,
                batch_success,
                len(batch),
            )

            # 마지막 배치가 아니면 delay
            if i + BATCH_SIZE < len(districts):
                await asyncio.sleep(0.3)

    return total_success, total_fail


# ── 메인 수집 함수 ─────────────────────────────────────────────────────────────


def collect_all_regions():
    """전국 지역 데이터 수집 → Redis 저장 (1단계 + 2단계)"""
    if not _redis:
        logger.error("[region_scheduler] Redis 연결 없음 — 수집 중단")
        return

    logger.info("[region_scheduler] 전국 지역 데이터 수집 시작")

    # ── 1단계: 시/도 + 구/군 수집 ──
    try:
        remix_data = _fetch_regions_page()
        provinces, districts = _parse_regions(remix_data)
    except Exception as e:
        logger.error("[region_scheduler] 1단계 실패: %s", e)
        # 재시도 1회
        try:
            logger.info("[region_scheduler] 1단계 재시도...")
            remix_data = _fetch_regions_page()
            provinces, districts = _parse_regions(remix_data)
        except Exception as e2:
            logger.error("[region_scheduler] 1단계 재시도 실패: %s — 수집 중단", e2)
            return

    # Redis에 저장
    _redis.set(
        "daangn:regions:all",
        json.dumps(provinces, ensure_ascii=False),
        ex=TTL_48H,
    )
    _redis.set(
        "daangn:districts:all",
        json.dumps(districts, ensure_ascii=False),
        ex=TTL_48H,
    )

    logger.info(
        "[region_scheduler] 1단계 완료: %d개 시/도, %d개 구/군",
        len(provinces),
        len(districts),
    )

    # ── 2단계: 동/읍/면 수집 (20개씩 병렬) ──
    try:
        success, fail = asyncio.run(_collect_dongs_in_batches(districts))
        logger.info(
            "[region_scheduler] 2단계 완료: 성공 %d / 실패 %d (전체 %d개 구/군)",
            success,
            fail,
            len(districts),
        )
    except Exception as e:
        logger.error("[region_scheduler] 2단계 실패: %s", e)

    logger.info("[region_scheduler] 전국 지역 데이터 수집 완료")


# ── APScheduler 등록 ──────────────────────────────────────────────────────────

def create_region_scheduler():
    """스케줄러 인스턴스 생성 및 job 등록"""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        collect_all_regions,
        trigger=CronTrigger(hour=4, minute=0),
        id="daangn_region_collector",
        name="당근 전국 지역 데이터 수집",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    return scheduler
