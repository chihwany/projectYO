"""
중고나라 (Joongna) 스크래퍼
web.joongna.com 매물을 검색하고 조회하는 모듈
"""

import requests
import json
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote


class JoongnaScraper:
    """중고나라 매물 스크래퍼"""

    BASE_URL = "https://web.joongna.com"
    SEARCH_API_URL = "https://search-api.joongna.com/v25/search/product"

    SORT_MAP = {
        "recommend": "RECOMMEND_SORT",
        "recent": "RECENT_SORT",
        "price_asc": "PRICE_ASC_SORT",
        "price_desc": "PRICE_DESC_SORT",
    }

    CATEGORY_MAP = {
        1: "수입명품", 2: "패션의류", 3: "패션잡화", 4: "뷰티",
        5: "출산/유아동", 6: "모바일/태블릿", 7: "가전제품", 8: "노트북/PC",
        9: "카메라/캠코더", 10: "가구/인테리어", 11: "리빙/생활", 12: "게임",
        13: "반려동물/취미", 14: "도서/음반/문구", 15: "티켓/쿠폰", 16: "스포츠",
        17: "레저/여행", 19: "오토바이", 20: "공구/산업용품", 21: "무료나눔",
    }

    # 주요 카테고리 (매물이 많은 인기 카테고리 우선)
    POPULAR_CATEGORIES = [6, 7, 8, 2, 3, 12, 16, 1, 10, 11]

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://web.joongna.com/",
        })
        self._last_request_time = 0

    # ──────────────────────────────────────────────────────────────────
    # 내부 유틸
    # ──────────────────────────────────────────────────────────────────

    def _throttle(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()

    def _parse_next_data(self, html: str) -> Optional[dict]:
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html, re.DOTALL,
        )
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return None
        return None

    def _extract_search_results(self, next_data: dict) -> dict:
        """__NEXT_DATA__ 에서 검색 결과 블록 추출 (queryKey 무관하게 items 탐색)"""
        queries = (
            next_data.get("props", {})
            .get("pageProps", {})
            .get("dehydratedState", {})
            .get("queries", [])
        )
        # 1) 정확한 키 우선
        for query in queries:
            qk = query.get("queryKey", [])
            if isinstance(qk, list) and qk and qk[0] == "get-search-products":
                data = query.get("state", {}).get("data", {}).get("data", {})
                if data:
                    return data
        # 2) items 필드가 있는 첫 번째 query 반환 (키워드 없는 카테고리 페이지 대응)
        for query in queries:
            data = query.get("state", {}).get("data", {}).get("data", {})
            if isinstance(data, dict) and "items" in data:
                return data
        return {}

    @staticmethod
    def _parse_dt(item: dict) -> datetime:
        raw = str(item.get("time") or "").strip().rstrip("Z")
        for fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        return datetime.min

    def _parse_item(self, item: dict) -> dict:
        image_url = item.get("imageUrl") or (
            item["imageUrls"][0] if item.get("imageUrls") else ""
        )
        price = item.get("price", 0)
        if isinstance(price, str):
            price = int(re.sub(r"[^\d]", "", price) or 0)

        sale_status = item.get("saleStatus", "")
        status_map = {"SALE": "판매중", "RSRV": "예약중", "SOLD": "판매완료", "CMPT": "판매완료"}
        status = status_map.get(sale_status, sale_status)

        return {
            "id": item.get("seq", item.get("productSeq", "")),
            "title": item.get("title", item.get("productTitle", "")),
            "price": price,
            "price_str": f"{price:,}원" if price > 0 else "가격미정",
            "image_url": image_url,
            "status": status,
            "location": item.get("locationName", item.get("area", "")),
            "time": item.get("sortDate", item.get("regDate", "")),
            "url": f"{self.BASE_URL}/product/{item.get('seq', item.get('productSeq', ''))}",
            "seller": item.get("storeName", item.get("sellerName", "")),
            "likes": item.get("wishCount", item.get("likeCount", 0)),
            "views": item.get("viewCount", 0),
            "safe_payment": item.get("jnPayYn", False),
            "category": item.get("categoryName", ""),
        }

    # ──────────────────────────────────────────────────────────────────
    # 키워드 검색
    # ──────────────────────────────────────────────────────────────────

    def search(
        self,
        keyword: str,
        page: int = 1,
        count: int = 50,
        sort: str = "recommend",
        category: Optional[int] = None,
        min_price: int = 0,
        max_price: int = 100_000_000,
        exclude_sold: bool = True,
    ) -> list[dict]:
        """중고나라 키워드 검색"""
        self._throttle()

        encoded_keyword = quote(keyword)
        params: dict = {"keywordSource": "INPUT_KEYWORD", "page": page}

        if category:
            params["category"] = category
        if min_price > 0:
            params["minPrice"] = min_price
        if max_price < 100_000_000:
            params["maxPrice"] = max_price
        if sort != "recommend":
            params["sort"] = self.SORT_MAP.get(sort, "RECOMMEND_SORT")
        if not exclude_sold:
            params["saleYn"] = "ALL"

        url = f"{self.BASE_URL}/search/{encoded_keyword}"

        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"[오류] 요청 실패: {e}")
            return []

        next_data = self._parse_next_data(response.text)
        if not next_data:
            print("[오류] 페이지 데이터를 파싱할 수 없습니다.")
            return []

        search_data = self._extract_search_results(next_data)
        items = search_data.get("items", [])
        total_size = search_data.get("totalSize", 0)

        results = [self._parse_item(i) for i in items[:count] if i.get("title", i.get("productTitle"))]

        if results:
            print(f"[검색완료] '{keyword}' - 총 {total_size}개 중 {len(results)}개 조회")
        else:
            print(f"[검색완료] '{keyword}' - 검색 결과 없음")
        return results

    # ──────────────────────────────────────────────────────────────────
    # 최근 매물 (전체 카테고리 병렬 수집)
    # ──────────────────────────────────────────────────────────────────

    def _fetch_category_recent(
        self,
        category_code: int,
        page: int = 1,
        count: int = 50,
        min_price: int = 0,
        max_price: int = 100_000_000,
        exclude_sold: bool = True,
    ) -> list[dict]:
        """
        카테고리 페이지(/search?category=N&sort=RECENT_SORT)에서 최신 매물을 가져옵니다.

        중고나라 SSR 제약사항:
          - /search?sort=RECENT_SORT (키워드 없이, 카테고리 없이) → 500 에러
          - /search?category=N&sort=RECENT_SORT → 정상 동작 ✓
          - search-api.joongna.com 직접 호출 → 404 (외부 접근 차단)

        따라서 반드시 category를 함께 전달해야 합니다.
        """
        self._throttle()

        cat_name = self.CATEGORY_MAP.get(category_code, str(category_code))

        params: dict = {
            "page": page,
            "sort": "RECENT_SORT",
            "category": category_code,
        }
        if min_price > 0:
            params["minPrice"] = min_price
        if max_price < 100_000_000:
            params["maxPrice"] = max_price
        if not exclude_sold:
            params["saleYn"] = "ALL"

        try:
            response = self.session.get(f"{self.BASE_URL}/search", params=params, timeout=15)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"  [{cat_name}] 요청 실패: {e}")
            return []

        next_data = self._parse_next_data(response.text)
        if not next_data:
            print(f"  [{cat_name}] __NEXT_DATA__ 파싱 실패 (status={response.status_code})")
            return []

        search_data = self._extract_search_results(next_data)
        items = search_data.get("items", [])

        results = []
        for item in items[:count]:
            parsed = self._parse_item(item)
            if parsed["title"]:
                if not parsed["category"]:
                    parsed["category"] = cat_name
                results.append(parsed)

        print(f"  [{cat_name}] {len(results)}개 수집")
        return results

    def get_recent_listings(
        self,
        count: int = 30,
        categories: Optional[list] = None,
        min_price: int = 0,
        max_price: int = 100_000_000,
        exclude_sold: bool = True,
        max_workers: int = 5,
        within_minutes: Optional[int] = None,
    ) -> list[dict]:
        """
        전체 최신 매물을 수집합니다.

        중고나라 제약사항:
          - /search?sort=RECENT_SORT (키워드·카테고리 없이) → 500 에러
          - search-api.joongna.com 직접 호출 → 404 (외부 접근 차단)
          - /search?category=N&sort=RECENT_SORT → 정상 동작 ✓

        따라서 전체 카테고리(20개)를 병렬로 조회하여 통합합니다.

        Args:
            count         : 카테고리당 수집 개수 (기본 50, 최대 50)
            categories    : 조회할 카테고리 코드 리스트. None 이면 전체 20개 카테고리.
            min_price     : 최소 가격
            max_price     : 최대 가격
            exclude_sold  : 판매완료 제외 (기본 True)
            max_workers   : 병렬 스레드 수 (기본 5)
            within_minutes: 지정 시, 현재 시각 기준 N분 이내 등록된 매물만 반환.

        Returns:
            수집된 매물 리스트 (등록 시간 최신순 정렬)
        """
        start = time.time()
        target_cats = categories if categories else list(self.CATEGORY_MAP.keys())
        per_cat = min(count, 50)

        print(
            f"[최근매물] 카테고리 {len(target_cats)}개 병렬 수집 시작 "
            f"(카테고리당 최대 {per_cat}개, workers={max_workers}"
            + (f", 최근 {within_minutes}분 이내" if within_minutes else "")
            + ")"
        )

        all_results: list[dict] = []
        seen_ids: set = set()

        def _fetch(cat: int) -> list[dict]:
            return self._fetch_category_recent(
                cat, page=1, count=per_cat,
                min_price=min_price, max_price=max_price,
                exclude_sold=exclude_sold,
            )

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_fetch, c): c for c in target_cats}
            for future in as_completed(futures):
                try:
                    for item in future.result():
                        item_id = item.get("id")
                        if item_id and item_id not in seen_ids:
                            seen_ids.add(item_id)
                            all_results.append(item)
                except Exception as e:
                    print(f"  [카테고리:{futures[future]}] 수집 오류: {e}")

        # 시간 필터
        if within_minutes is not None:
            cutoff = datetime.now() - timedelta(minutes=within_minutes)
            before = len(all_results)
            all_results = [r for r in all_results if self._parse_dt(r) >= cutoff]
            print(f"[최근매물] 시간 필터({within_minutes}분): {before}개 → {len(all_results)}개")

        # 최신순 정렬
        all_results.sort(key=self._parse_dt, reverse=True)

        elapsed = round(time.time() - start, 2)
        print(f"[최근매물] 최종 {len(all_results)}개 수집 완료 - 중복 제거 후 ({elapsed}초)")
        return all_results

    # ──────────────────────────────────────────────────────────────────
    # 다중 페이지 검색
    # ──────────────────────────────────────────────────────────────────

    def search_all(self, keyword: str, max_pages: int = 5, **kwargs) -> list[dict]:
        all_results = []
        for page in range(1, max_pages + 1):
            results = self.search(keyword, page=page, **kwargs)
            if not results:
                break
            all_results.extend(results)
            print(f"  ... {page}페이지 완료 (누적 {len(all_results)}개)")
        return all_results

    # ──────────────────────────────────────────────────────────────────
    # 상품 상세
    # ──────────────────────────────────────────────────────────────────

    def get_product_detail(self, product_id: int) -> Optional[dict]:
        self._throttle()
        url = f"{self.BASE_URL}/product/{product_id}"

        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"[오류] 상세 조회 실패: {e}")
            return None

        next_data = self._parse_next_data(response.text)
        if not next_data:
            return None

        queries = (
            next_data.get("props", {})
            .get("pageProps", {})
            .get("dehydratedState", {})
            .get("queries", [])
        )
        for query in queries:
            qk = query.get("queryKey", [])
            if isinstance(qk, list) and qk:
                if "product-detail" in str(qk[0]) or "product" in str(qk[0]).lower():
                    data = query.get("state", {}).get("data", {}).get("data", {})
                    if data:
                        return data
        return None

    # ──────────────────────────────────────────────────────────────────
    # 포맷팅
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def format_results(results: list[dict], show_url: bool = True) -> str:
        if not results:
            return "검색 결과가 없습니다."

        lines = [f"{'='*60}", f" 검색 결과: {len(results)}개", f"{'='*60}"]
        for i, item in enumerate(results, 1):
            lines.append(f"\n[{i}] {item['title']}")
            lines.append(f"    💰 가격: {item['price_str']}")
            if item.get("status"):
                lines.append(f"    📌 상태: {item['status']}")
            if item.get("location"):
                lines.append(f"    📍 지역: {item['location']}")
            if item.get("time"):
                lines.append(f"    🕐 등록: {item['time']}")
            if item.get("seller"):
                lines.append(f"    👤 판매자: {item['seller']}")
            if show_url:
                lines.append(f"    🔗 링크: {item['url']}")
            lines.append(f"    {'─'*40}")
        return "\n".join(lines)
