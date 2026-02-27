"""
당근 지역 검색 모듈
daangn.com/kr/regions/ 페이지를 파싱하여 지역 목록을 제공합니다.
별도 크롤링/캐시 파일 불필요 — 서버 메모리 TTL 캐시(1시간)로 동작합니다.
"""

import requests
import re
import time
from urllib.parse import unquote
from bs4 import BeautifulSoup
from typing import Optional

REGIONS_PAGE_URL = "https://www.daangn.com/kr/regions/"
REGIONS_CACHE_TTL = 3600  # 1시간

_regions_cache: Optional[list[dict]] = None
_regions_cache_time: float = 0.0


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    })
    return s


def _parse_regions_page(html: str) -> list[dict]:
    """
    daangn.com/kr/regions/ HTML을 파싱하여 전체 지역 목록 반환.

    <h2> 태그 = 시/도 구분자
    <a href="?in=지역명-코드"> 태그 = 구/군 링크

    반환:
    [
      {"name": "강남구", "code": "강남구-10", "city": "서울특별시", "full": "서울특별시 강남구"},
      ...
    ]
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()
    current_city = ""

    main = soup.find("main") or soup
    for tag in main.find_all(["h2", "a"]):
        if tag.name == "h2":
            current_city = tag.get_text(strip=True)
        elif tag.name == "a" and current_city:
            href = tag.get("href", "")
            match = re.search(r'[?&]in=([^&]+)', href)
            if not match:
                continue
            code_raw = unquote(match.group(1))
            parts = code_raw.rsplit("-", 1)
            if len(parts) != 2 or not parts[1].isdigit():
                continue
            name, code = parts[0], code_raw
            if code not in seen:
                seen.add(code)
                results.append({
                    "name": name,
                    "code": code,
                    "city": current_city,
                    "full": f"{current_city} {name}",
                })

    return results


def fetch_regions(session: Optional[requests.Session] = None) -> list[dict]:
    """
    daangn.com/kr/regions/ 를 요청하여 전체 지역 목록 반환.
    TTL 1시간 메모리 캐시 사용.

    반환: [{"name", "code", "city", "full"}, ...]
    Raises: RuntimeError (요청/파싱 실패 시)
    """
    global _regions_cache, _regions_cache_time

    now = time.time()
    if _regions_cache is not None and (now - _regions_cache_time) < REGIONS_CACHE_TTL:
        return _regions_cache

    s = session or _make_session()
    try:
        resp = s.get(REGIONS_PAGE_URL, timeout=15)
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        regions = _parse_regions_page(resp.text)
        if not regions:
            raise RuntimeError("파싱된 지역 목록이 비어있습니다. 페이지 구조가 변경되었을 수 있습니다.")
        _regions_cache = regions
        _regions_cache_time = now
        return regions
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"당근 지역 페이지 요청 실패: {e}")


def search_region_live(query: str, limit: int = 20) -> list[dict]:
    """
    지역명 실시간 검색 (부분 일치).

    Args:
        query: 검색어 (예: "강남", "판교", "서초구")
        limit: 최대 결과 수 (기본 20)

    Returns:
        [{"name": "강남구", "code": "강남구-10", "city": "서울특별시", "full": "서울특별시 강남구"}, ...]
    """
    query = query.strip()
    if not query:
        return []

    all_regions = fetch_regions()
    results = []
    for item in all_regions:
        if query in item["full"] or query in item["name"]:
            results.append(item)
            if len(results) >= limit:
                break
    return results


def get_cities() -> list[str]:
    """
    시/도 목록 반환.
    Returns: ["서울특별시", "부산광역시", ...]
    """
    seen: list[str] = []
    for item in fetch_regions():
        if item["city"] not in seen:
            seen.append(item["city"])
    return seen


def get_districts(city: str) -> list[dict]:
    """
    특정 시/도의 구/군 목록 반환.

    Args:
        city: 시/도명 (예: "서울특별시", "경기도")

    Returns:
        [{"name": "강남구", "code": "강남구-10", "city": "서울특별시", "full": "서울특별시 강남구"}, ...]
    """
    return [r for r in fetch_regions() if r["city"] == city]


# ───────────────────────────────────────
# 당근 내부 location API 프록시
# ───────────────────────────────────────

DANGN_LOCATION_API_URL = "https://www.daangn.com/v1/api/search/kr/location"

# 캐시: keyword → (timestamp, result_list)
_location_cache: dict[str, tuple[float, list[dict]]] = {}
_LOCATION_CACHE_TTL = 3600  # 1시간


def search_location(keyword: str) -> list[dict]:
    """
    당근 내부 location 검색 API를 호출하여 결과를 반환합니다.
    https://www.daangn.com/v1/api/search/kr/location?keyword=<keyword>
    와 동일한 결과를 반환합니다.

    Args:
        keyword: 검색어 (예: "경기도", "덕양구", "행신동")

    Returns:
        [
            {
                "id": 1590,
                "name1": "경기도",
                "name2": "남양주시",
                "name3": "화도읍",
                "name": "화도읍",
                "name1Id": 1256,
                "name2Id": 1587,
                "name3Id": 1590,
                "depth": 3
            },
            ...
        ]

    Raises:
        RuntimeError: 당근 API 요청 실패 시
    """
    keyword = keyword.strip()
    if not keyword:
        return []

    # 캐시 확인
    now = time.time()
    cache_key = keyword
    if cache_key in _location_cache:
        cached_time, cached_data = _location_cache[cache_key]
        if (now - cached_time) < _LOCATION_CACHE_TTL:
            return cached_data

    # 당근 API 호출
    s = _make_session()
    # JSON API이므로 Accept 헤더 조정
    s.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.daangn.com/",
    })

    try:
        resp = s.get(
            DANGN_LOCATION_API_URL,
            params={"keyword": keyword},
            timeout=15,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")

        data = resp.json()
        locations = data.get("locations", [])

        # 캐시 저장
        _location_cache[cache_key] = (now, locations)
        return locations

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"당근 location API 요청 실패: {e}")


# ───────────────────────────────────────
# CLI: python daangn_regions.py --search 강남
# ───────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="당근 지역 검색")
    parser.add_argument("--search", type=str, default="", help="지역 검색어 (예: 강남)")
    parser.add_argument("--cities", action="store_true", help="시/도 목록 출력")
    parser.add_argument("--districts", type=str, default="", help="특정 시/도의 구/군 목록 (예: 서울특별시)")
    args = parser.parse_args()

    if args.search:
        results = search_region_live(args.search)
        print(f"\n'{args.search}' 검색 결과: {len(results)}개\n")
        for r in results:
            print(f"  {r['full']}  →  {r['code']}")
    elif args.cities:
        cities = get_cities()
        print(f"\n시/도 목록: {len(cities)}개\n")
        for c in cities:
            print(f"  {c}")
    elif args.districts:
        districts = get_districts(args.districts)
        if not districts:
            print(f"'{args.districts}' 시/도를 찾을 수 없습니다.")
        else:
            print(f"\n{args.districts} 구/군 목록: {len(districts)}개\n")
            for d in districts:
                print(f"  {d['name']}  →  {d['code']}")
    else:
        parser.print_help()
