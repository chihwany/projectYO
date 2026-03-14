"""
당근마켓 (Daangn) 스크래퍼

수집 방식: Remix SSR HTML 파싱 (window.__remixContext)
Fallback:  BeautifulSoup HTML 파싱
참고 문서: docs/daangn.md

표준 스키마 10필드:
  id, title, price, price_str, image_url, status, location, time, url, source

지역 선택 방식:
  - 사용자가 당근 Location API로 검색한 location id(name3Id)를 직접 전달
  - 구/군 검색 시 다수의 location_id 목록을 병렬 검색

당근은 스케줄러 폴링 없음 — 앱 탭에서 직접 검색만 사용.
"""

import asyncio
import json
import logging
import os
import re

import aiohttp
import redis
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── 상수 ────────────────────────────────────────────────────────────────────────

SEARCH_URL = "https://www.daangn.com/kr/buy-sell/s/"
PRODUCT_URL = "https://www.daangn.com/kr/buy-sell/{pid}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.daangn.com/",
}

STATUS_MAP = {
    "Ongoing": "판매중",
    "Reserved": "예약중",
    "Completed": "거래완료",
}

REQUEST_TIMEOUT = 3

# remixContext 추출 정규식
_REMIX_RE = re.compile(r"window\.__remixContext\s*=\s*(\{.*?\})\s*;", re.DOTALL)

# ── aiohttp 커넥터 (커넥션 풀) ────────────────────────────────────────────────
_AIOHTTP_POOL_LIMIT = int(os.getenv("DAANGN_DISTRICT_WORKERS", "100"))

# ── Redis (지역 정보 캐싱) ────────────────────────────────────────────────────
_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_LOCATION_CACHE_TTL = 60 * 60 * 24  # 24시간
_LOCATION_CACHE_PREFIX = "daangn:location:"

try:
    _redis = redis.from_url(_REDIS_URL, decode_responses=True)
    _redis.ping()
    logger.info("Redis 연결 성공: %s", _REDIS_URL)
except Exception as e:
    logger.warning("Redis 연결 실패 (캐시 없이 동작): %s", e)
    _redis = None


# ── 헬퍼 함수 ──────────────────────────────────────────────────────────────────


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _format_price_str(price: int) -> str:
    if price <= 0:
        return "가격미정"
    return f"{price:,}원"


def _extract_product_id(raw_id) -> str:
    """'/kr/buy-sell/abc123' → 'abc123'"""
    if isinstance(raw_id, str) and "/" in raw_id:
        return raw_id.rstrip("/").rsplit("/", 1)[-1]
    return str(raw_id or "")


def _extract_remix_context(html: str) -> dict | None:
    """HTML에서 window.__remixContext JSON 추출"""
    match = _REMIX_RE.search(html)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _find_articles(remix_data: dict) -> list:
    """remixContext → loaderData → fleamarketArticles 추출"""
    try:
        loader_data = remix_data["state"]["loaderData"]
        page_data = loader_data.get("routes/kr.buy-sell.s", {})
        all_page = page_data.get("allPage", {})
        articles = all_page.get("fleamarketArticles", [])
        return articles if isinstance(articles, list) else []
    except (KeyError, TypeError):
        return []


def _parse_item(raw: dict) -> dict:
    """remixContext 아이템 → 표준 스키마 10필드"""
    pid = _extract_product_id(raw.get("id", ""))
    price = _safe_int(raw.get("price"))
    status_raw = raw.get("status", "Ongoing")
    region = raw.get("region", {})

    return {
        "id": pid,
        "title": str(raw.get("title", "")),
        "price": price,
        "price_str": _format_price_str(price),
        "image_url": str(raw.get("thumbnail", "")),
        "status": STATUS_MAP.get(status_raw, "판매중"),
        "location": str(region.get("name", "") if isinstance(region, dict) else ""),
        "time": str(raw.get("createdAt") or raw.get("boostedAt", "")),
        "url": PRODUCT_URL.format(pid=pid),
        "source": "daangn",
    }


def _parse_html_fallback(html: str) -> list[dict]:
    """remixContext 실패 시 BeautifulSoup HTML 파싱 fallback"""
    soup = BeautifulSoup(html, "lxml")
    items: list[dict] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=re.compile(r"/kr/buy-sell/[^?s]")):
        href = link.get("href", "")
        pid = href.rstrip("/").rsplit("/", 1)[-1]
        if not pid or pid in seen:
            continue
        seen.add(pid)

        title = link.get_text(strip=True)
        img = link.find("img")
        image_url = img.get("src", "") if img else ""

        items.append(
            {
                "id": pid,
                "title": title,
                "price": 0,
                "price_str": "가격미정",
                "image_url": image_url,
                "status": "판매중",
                "location": "",
                "time": "",
                "url": PRODUCT_URL.format(pid=pid),
                "source": "daangn",
            }
        )

    return items


def _parse_items_from_html(html: str, keyword: str) -> list[dict]:
    """HTML → 아이템 리스트 (remixContext 우선, fallback HTML 파싱)"""
    remix_data = _extract_remix_context(html)
    if remix_data:
        articles = _find_articles(remix_data)
        return [_parse_item(a) for a in articles]
    else:
        logger.warning("당근 remixContext 파싱 실패, HTML fallback (keyword=%s)", keyword)
        return _parse_html_fallback(html)


# ── Location API ──────────────────────────────────────────────────────────────

LOCATION_API_URL = "https://www.daangn.com/v1/api/search/kr/location"
LOCATION_API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.daangn.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}
LOCATION_API_TIMEOUT = 10


def _fetch_from_location_api(keyword: str) -> dict:
    """
    당근 Location API 직접 호출 (fallback 전용).

    Redis에 스케줄러 데이터가 없는 경우에만 사용합니다.
    """
    async def _fetch():
        timeout = aiohttp.ClientTimeout(total=LOCATION_API_TIMEOUT)
        async with aiohttp.ClientSession(headers=LOCATION_API_HEADERS, timeout=timeout) as session:
            async with session.get(LOCATION_API_URL, params={"keyword": keyword}) as resp:
                resp.raise_for_status()
                return await resp.json()

    body = asyncio.run(_fetch())
    locations = body.get("locations", [])

    # Redis 캐시 저장
    cache_key = f"{_LOCATION_CACHE_PREFIX}{keyword}"
    if _redis and locations:
        try:
            _redis.setex(cache_key, _LOCATION_CACHE_TTL, json.dumps(locations, ensure_ascii=False))
        except Exception as e:
            logger.warning("Redis 캐시 저장 실패: %s", e)

    logger.info("당근 Location API (fallback): keyword=%s → %d건", keyword, len(locations))
    return {"locations": locations}


def search_location(keyword: str) -> dict:
    """
    당근 지역 검색 — Redis 우선 조회.

    스케줄러가 수집한 Redis 데이터에서 검색하고,
    Redis에 데이터가 없는 경우에만 fallback으로 Location API를 호출합니다.

    Args:
        keyword: 지역 검색어 (예: '강남구', '역삼동', '능곡')

    Returns:
        {
          "locations": [
            {
              "regionId": 381,          # 구/군 검색 시
              "name": "강남구",
              "province": "서울특별시",
              "depth": 2
            }
            또는
            {
              "id": 1540,               # Location API fallback 시
              "name": "능곡동",
              "name1": "경기도",
              "name2": "고양시 덕양구",
              "name3": "능곡동",
              "name1Id": 1256,
              "name2Id": 1529,
              "name3Id": 1540,
              "depth": 3
            }
          ]
        }

    Raises:
        requests.exceptions.Timeout: fallback API 타임아웃 발생 시
        requests.exceptions.RequestException: fallback 네트워크 오류 발생 시
    """
    # 1순위: Redis에서 스케줄러 수집 데이터 검색 (daangn:districts:all)
    if _redis:
        try:
            districts_json = _redis.get("daangn:districts:all")
            if districts_json:
                all_districts = json.loads(districts_json)
                matched = [d for d in all_districts if keyword in d["name"]]
                if matched:
                    logger.info("당근 지역 검색 (Redis): keyword=%s → %d건", keyword, len(matched))
                    return {"locations": matched}
        except Exception as e:
            logger.warning("Redis districts 조회 실패: %s", e)

    # 2순위: 기존 location 캐시 확인 (daangn:location:{keyword})
    cache_key = f"{_LOCATION_CACHE_PREFIX}{keyword}"
    if _redis:
        try:
            cached = _redis.get(cache_key)
            if cached:
                locations = json.loads(cached)
                logger.info("당근 지역 검색 (캐시): keyword=%s → %d건", keyword, len(locations))
                return {"locations": locations}
        except Exception as e:
            logger.warning("Redis 캐시 조회 실패: %s", e)

    # 3순위 (fallback): Redis에 데이터가 전혀 없는 경우에만 Location API 호출
    logger.warning("당근 지역 검색: Redis에 데이터 없음, fallback API 호출 (keyword=%s)", keyword)
    return _fetch_from_location_api(keyword)


# ── 검색 함수 ──────────────────────────────────────────────────────────────────


def search_by_district(keyword: str, district: str, count: int = 20) -> dict:
    """
    구/군명으로 지역 검색 후 하위 동 전체를 병렬 검색.

    동작 흐름:
      1. search_location(district)를 호출하여 당근 Location API 결과 수집
      2. depth=3(동/읍/면) 항목의 name3Id만 추줄 → 하위 동 location_id 목록
      3. multi_location_search(keyword, location_ids)로 병렬 검색
      4. 중복 제거 + 최신순 정렬 후 반환

    Args:
        keyword:  검색어 (예: '닌텐도', '아이폰')
        district: 구/군명 (예: '덕양구', '종로구', '수진구')
        count:    최대 스과 결과 수

    Returns:
        {
          "items": [...],       # 표준 스키마 10필드
          "total": 12,
          "district": "덕양구",
          "dong_count": 18      # 실제 검색에 사용된 동 수
        }

    Raises:
        ValueError: district에 해당하는 depth=3 지역이 없을 때
        requests.exceptions.RequestException: Location API 호출 실패 시
    """
    # 1. 구/군명으로 Location API 호출
    location_result = search_location(district)
    locations = location_result["locations"]

    # 2. depth=3(동/읍/면)인 항목의 name3Id만 추줄
    dong_ids = [
        loc["name3Id"]
        for loc in locations
        if loc.get("depth") == 3 and loc.get("name3Id")
    ]

    if not dong_ids:
        logger.warning(
            "search_by_district: '%s'에 해당하는 depth=3 지역 없음 (완전일치 필요)",
            district,
        )
        raise ValueError(
            f"'{district}'에 해당하는 동/읍/면 지역이 없습니다. "
            "정확한 구/군명을 입력해 주세요. (예: '덕양구', '종로구')"
        )

    logger.info(
        "search_by_district: district=%s → %d개 동 수집, keyword=%s 검색 시작",
        district, len(dong_ids), keyword,
    )

    # 3. 수집된 동 location_id로 병렬 검색
    result = multi_location_search(keyword, dong_ids, count=count)

    # 4. 구/군 정보 추가
    result["district"] = district
    result["dong_count"] = len(dong_ids)
    return result


def search(
    keyword: str,
    location_id: int | None = None,
    page: int = 1,
    count: int = 20,
) -> dict:
    """
    당근 단건 검색.

    location_id는 당근 Location API(/v1/api/search/kr/location)의
    응답 필드 name3Id(동 레벨) 또는 name2Id(구/군 레벨) 값을 사용합니다.

    Args:
        keyword:     검색어 (필수)
        location_id: 당근 내부 location id (name3Id), None이면 전체
        page:        페이지 번호 (1-based)
        count:       결과 수
    """
    params: dict = {"search": keyword, "only_on_sale": "true"}
    if location_id is not None:
        params["in"] = location_id
    if page > 1:
        params["page"] = page

    async def _fetch():
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
            async with session.get(SEARCH_URL, params=params) as resp:
                resp.raise_for_status()
                return await resp.text(encoding="utf-8")

    try:
        html = asyncio.run(_fetch())
    except Exception as e:
        logger.error("당근 검색 실패 (keyword=%s, location_id=%s): %s", keyword, location_id, e)
        return {"items": [], "total": 0}

    items = _parse_items_from_html(html, keyword)
    items = items[:count]

    logger.info(
        "당근 검색: keyword=%s location_id=%s page=%d → %d건",
        keyword,
        location_id,
        page,
        len(items),
    )

    return {"items": items, "total": len(items)}


async def _async_search_one(
    session: aiohttp.ClientSession,
    keyword: str,
    location_id: int,
    count: int,
) -> list[dict]:
    """aiohttp 세션을 공유하는 비동기 단건 검색"""
    params: dict = {"search": keyword, "only_on_sale": "true", "in": location_id}

    try:
        async with session.get(SEARCH_URL, params=params) as resp:
            resp.raise_for_status()
            html = await resp.text(encoding="utf-8")
    except Exception as e:
        logger.warning("당근 async 검색 실패 (location_id=%s): %s", location_id, e)
        return []

    items = _parse_items_from_html(html, keyword)
    return items[:count]


def search_district_direct(
    keyword: str,
    district: str,
    count: int = 300,
) -> dict:
    """
    구/군 레벨 regionId로 직접 키워드 검색 (Remix _data loader).

    기존 search_by_district()가 동 레벨 N번 요청하는 것과 달리,
    구 레벨 regionId 1번 요청으로 하위 동 전체 매물을 가져온다.

    Args:
        keyword:  검색어 (예: '닌텐도', '아이폰')
        district: 구/군명 (예: '덕양구', '종로구')
        count:    최대 결과 수 (기본 300, 최대 ~300건 반환)

    Returns:
        {
          "items": [...],        # 표준 스키마 10필드
          "total": 248,
          "district": "덕양구",
          "regionId": 1529
        }
    """
    # 1. 구/군명으로 regionId 조회
    location_result = search_location(district)
    locations = location_result["locations"]

    # Redis districts에서 온 경우 regionId 직접 사용
    region_id = None
    for loc in locations:
        if loc.get("regionId"):
            region_id = loc["regionId"]
            break
        # Location API fallback인 경우 name2Id 사용
        if loc.get("name2Id") and loc.get("depth") == 2:
            region_id = loc["name2Id"]
            break
        if loc.get("name2Id") and loc.get("depth") == 3:
            region_id = loc["name2Id"]
            break

    if not region_id:
        raise ValueError(
            f"'{district}'에 해당하는 구/군 regionId를 찾을 수 없습니다."
        )

    # 2. _data loader로 구 레벨 직접 검색 (1번 요청)
    data_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "application/json",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    async def _fetch():
        params = {
            "search": keyword,
            "in": region_id,
            "_data": "routes/kr.buy-sell.s",
        }
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(headers=data_headers, timeout=timeout) as session:
            async with session.get(SEARCH_URL, params=params) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)

    try:
        data = asyncio.run(_fetch())
    except Exception as e:
        logger.error("당근 district-search 실패 (keyword=%s, regionId=%s): %s", keyword, region_id, e)
        return {"items": [], "total": 0, "district": district, "regionId": region_id}

    articles = (
        data.get("allPage", {})
        .get("fleamarketArticles", [])
    )

    # 3. 표준 스키마로 변환
    items = [_parse_item(a) for a in articles]
    items = items[:count]

    logger.info(
        "당근 district-search: keyword=%s district=%s regionId=%s → %d건",
        keyword, district, region_id, len(items),
    )

    return {
        "items": items,
        "total": len(items),
        "district": district,
        "regionId": region_id,
    }


def multi_location_search(
    keyword: str,
    location_ids: list[int],
    count: int = 20,
) -> dict:
    """
    여러 location_id(동 레벨)에 대해 비동기 병렬 검색 → 중복 제거 → 최신순 정렬.

    asyncio + aiohttp로 단일 커넥션 풀을 공유하여
    스레드 오버헤드 없이 대량 동시 요청을 처리합니다.

    Args:
        keyword:      검색어
        location_ids: 당근 location id 목록 (name3Id)
        count:        최대 결과 수
    """
    if not location_ids:
        logger.warning("당근 multi_location_search: location_ids 없음")
        return {"items": [], "total": 0}

    async def _fetch_all():
        connector = aiohttp.TCPConnector(limit=_AIOHTTP_POOL_LIMIT)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(
            headers=HEADERS, connector=connector, timeout=timeout
        ) as session:
            tasks = [
                _async_search_one(session, keyword, loc_id, count)
                for loc_id in location_ids
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

    results = asyncio.run(_fetch_all())

    all_items: list[dict] = []
    seen_ids: set[str] = set()

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning("당근 location_id=%s 검색 실패: %s", location_ids[i], result)
            continue
        for item in result:
            if item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                all_items.append(item)

    # 최신순 정렬
    all_items.sort(key=lambda x: x.get("time", ""), reverse=True)
    all_items = all_items[:count]

    logger.info(
        "당근 multi_location_search: keyword=%s, %d개 location → %d건",
        keyword,
        len(location_ids),
        len(all_items),
    )

    return {"items": all_items, "total": len(all_items)}
