"""
번개장터 (Bunjang) 스크래퍼

수집 방식: 공개 JSON REST API (api.bunjang.co.kr) 직접 호출
참고 문서: docs/bunjang.md

표준 스키마 10필드:
  id, title, price, price_str, image_url, status, location, time, url, source
"""

import logging
import os
import time
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

# ── 상수 ────────────────────────────────────────────────────────────────────────

API_BASE = "https://api.bunjang.co.kr/api/1/find_v2.json"
PRODUCT_URL = "https://m.bunjang.co.kr/products/{pid}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://m.bunjang.co.kr/",
    "Origin": "https://m.bunjang.co.kr",
}

SORT_MAP = {
    "recommend": "score",
    "recent": "date",
    "price_asc": "price",
    "price_desc": "price_desc",
}

STATUS_MAP = {
    0: "판매중",
    1: "예약중",
    2: "판매완료",
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


def _unix_to_iso(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
    except (TypeError, ValueError):
        return ""


def _parse_item(raw: dict) -> dict:
    """API 응답 아이템 → 표준 스키마 10필드"""
    pid = str(raw.get("pid") or raw.get("product_id", ""))
    price = _safe_int(raw.get("price"))
    status_code = _safe_int(raw.get("status"), default=-1)

    return {
        "id": pid,
        "title": str(raw.get("name") or raw.get("title", "")),
        "price": price,
        "price_str": _format_price_str(price),
        "image_url": str(raw.get("product_image") or raw.get("image", "")),
        "status": STATUS_MAP.get(status_code, "판매중"),
        "location": str(raw.get("location", "")),
        "time": _unix_to_iso(raw.get("update_time")),
        "url": PRODUCT_URL.format(pid=pid),
        "source": "bunjang",
    }


# ── 검색 함수 (Step 1-3: 앱 탭 키워드 검색) ────────────────────────────────────


def search(
    keyword: str,
    page: int = 1,
    count: int = 20,
    min_price: int | None = None,
    max_price: int | None = None,
    sort: str = "recent",
) -> dict:
    """
    번개장터 키워드 검색 (앱 탭 검색용).

    Args:
        keyword:   검색어 (필수)
        page:      페이지 번호 (1-based → 내부 0-based 변환)
        count:     결과 수 (기본 20, 최대 100)
        min_price: 최소 가격 필터 (None=제한없음)
        max_price: 최대 가격 필터 (None=제한없음)
        sort:      정렬 (recommend | recent | price_asc | price_desc)

    Returns:
        {"items": [표준스키마 10필드], "total": int}
    """
    delay = float(os.getenv("CRAWLER_DELAY", "0.5"))

    # 1-based → 0-based
    api_page = max(0, page - 1)
    count = max(1, min(count, 100))
    order = SORT_MAP.get(sort, "date")

    params: dict = {
        "q": keyword,
        "order": order,
        "page": api_page,
        "n": count,
        "stat": "v2",
        "req_ref": "search",
        "stat_status": "s",  # 판매중만
    }

    if min_price is not None and min_price > 0:
        params["price_min"] = min_price
    if max_price is not None and max_price > 0:
        params["price_max"] = max_price

    time.sleep(delay)

    try:
        resp = requests.get(
            API_BASE, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error("번개장터 검색 실패 (keyword=%s): %s", keyword, e)
        return {"items": [], "total": 0}

    raw_list = data.get("list", [])
    total = _safe_int(data.get("num_found"))
    items = [_parse_item(item) for item in raw_list]

    logger.info(
        "번개장터 검색: keyword=%s page=%d count=%d → %d건 (total=%d)",
        keyword,
        page,
        count,
        len(items),
        total,
    )

    return {"items": items, "total": total}
