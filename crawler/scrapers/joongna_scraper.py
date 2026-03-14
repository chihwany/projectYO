"""
중고나라 (Joonggonara) 스크래퍼

수집 방식: Next.js SSR HTML 파싱 (__NEXT_DATA__)
참고 문서: docs/joongna.md

표준 스키마 10필드:
  id, title, price, price_str, image_url, status, location, time, url, source
"""

import json
import logging
import os
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── 상수 ────────────────────────────────────────────────────────────────────────

SEARCH_URL = "https://web.joongna.com/search/{keyword}"
PRODUCT_URL = "https://web.joongna.com/product/{pid}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://web.joongna.com/",
}

SORT_MAP = {
    "recommend": None,  # 파라미터 미포함 = 추천순
    "recent": "RECENT_SORT",
    "price_asc": "PRICE_ASC_SORT",
    "price_desc": "PRICE_DESC_SORT",
}

STATUS_MAP = {
    "SALE": "판매중",
    "RSRV": "예약중",
    "SOLD": "판매완료",
    "CMPT": "판매완료",
}

REQUEST_TIMEOUT = 15


# ── 헬퍼 함수 ──────────────────────────────────────────────────────────────────


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _format_price_str(price: int) -> str:
    if price <= 0:
        return "가격미정"
    return f"{price:,}원"


def _extract_next_data(html: str) -> dict | None:
    """HTML에서 <script id="__NEXT_DATA__"> JSON 추출"""
    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return None
    try:
        return json.loads(script.string)
    except json.JSONDecodeError:
        return None


def _find_products(next_data: dict) -> tuple[list, int]:
    """__NEXT_DATA__ → queries[] → 상품 목록 + totalSize 추출"""
    try:
        queries = next_data["props"]["pageProps"]["dehydratedState"]["queries"]
    except (KeyError, TypeError):
        return [], 0

    for q in queries:
        qk = q.get("queryKey", [])
        if qk and qk[0] == "get-search-products":
            try:
                wrapper = q["state"]["data"]["data"]
                if isinstance(wrapper, dict):
                    items = wrapper.get("items", [])
                    total = _safe_int(wrapper.get("totalSize"))
                    if isinstance(items, list):
                        return items, total
                elif isinstance(wrapper, list):
                    return wrapper, len(wrapper)
            except (KeyError, TypeError):
                continue

    return [], 0


STATUS_CODE_MAP = {
    0: "판매중",
    1: "예약중",
    2: "판매완료",
}


def _parse_item(raw: dict) -> dict:
    """원본 JSON → 표준 스키마 10필드"""
    pid = str(raw.get("seq") or raw.get("productSeq", ""))
    price = _safe_int(raw.get("price"))

    # status: 문자열(SALE/RSRV/SOLD) 또는 정수(0/1/2) 모두 처리
    status_raw = raw.get("saleStatus") or raw.get("state")
    if isinstance(status_raw, int):
        status = STATUS_CODE_MAP.get(status_raw, "판매중")
    else:
        status = STATUS_MAP.get(str(status_raw), "판매중")

    # 이미지: url 필드 우선 (검색 결과), imageUrl fallback (상세)
    image_url = raw.get("url", "") or raw.get("imageUrl", "")
    if not image_url:
        urls = raw.get("imageUrls")
        if isinstance(urls, list) and urls:
            image_url = urls[0]

    return {
        "id": pid,
        "title": str(raw.get("title") or raw.get("productTitle", "")),
        "price": price,
        "price_str": _format_price_str(price),
        "image_url": str(image_url),
        "status": status,
        "location": str(raw.get("mainLocationName") or raw.get("locationName", "")),
        "time": str(raw.get("sortDate") or raw.get("regDate", "")),
        "url": PRODUCT_URL.format(pid=pid),
        "source": "joongna",
    }


# ── 검색 함수 (Step 1-4: 앱 탭 키워드 검색) ────────────────────────────────────


def search(
    keyword: str,
    page: int = 1,
    count: int = 20,
    min_price: int | None = None,
    max_price: int | None = None,
    sort: str = "recent",
) -> dict:
    """
    중고나라 키워드 검색 (앱 탭 검색용).

    __NEXT_DATA__ 파싱을 통한 HTML 우회.
    카테고리 병렬 처리 없음 (앱 검색 = 단순 키워드).
    """
    delay = float(os.getenv("CRAWLER_DELAY", "0.5"))

    encoded = quote(keyword)
    url = SEARCH_URL.format(keyword=encoded)

    params: dict = {
        "keywordSource": "INPUT_KEYWORD",
        "page": page,
    }

    sort_val = SORT_MAP.get(sort)
    if sort_val:
        params["sort"] = sort_val

    if min_price is not None and min_price > 0:
        params["minPrice"] = min_price
    if max_price is not None and max_price > 0 and max_price < 100_000_000:
        params["maxPrice"] = max_price

    time.sleep(delay)

    try:
        resp = requests.get(
            url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("중고나라 검색 실패 (keyword=%s): %s", keyword, e)
        return {"items": [], "total": 0}

    next_data = _extract_next_data(resp.text)
    if not next_data:
        logger.warning("중고나라 __NEXT_DATA__ 파싱 실패 (keyword=%s)", keyword)
        return {"items": [], "total": 0}

    raw_items, total = _find_products(next_data)
    items = [_parse_item(item) for item in raw_items][:count]

    logger.info(
        "중고나라 검색: keyword=%s page=%d → %d건 (total=%d)",
        keyword,
        page,
        len(items),
        total,
    )

    return {"items": items, "total": total}
