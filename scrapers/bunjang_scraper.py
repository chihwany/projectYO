"""
번개장터 (Bunjang) 스크래퍼
m.bunjang.co.kr / api.bunjang.co.kr 매물을 검색하고 조회하는 모듈
"""

import requests
import json
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from urllib.parse import quote
from typing import Optional


class BunjangScraper:
    """번개장터 매물 스크래퍼"""

    BASE_URL = "https://m.bunjang.co.kr"
    # 번개장터 공개 검색 API
    SEARCH_API_URL = "https://api.bunjang.co.kr/api/1/find_v2.json"

    SORT_MAP = {
        "recommend": "score",
        "recent": "date",
        "price_asc": "price",
        "price_desc": "price_desc",
    }

    CATEGORY_MAP = {
        310: "여성의류", 320: "남성의류", 300: "패션잡화",
        400: "뷰티", 500: "출산/유아동",
        600: "모바일/태블릿", 601: "스마트폰", 602: "태블릿",
        700: "가전제품", 800: "노트북/PC",
        900: "카메라", 110: "가구/인테리어",
        120: "리빙/생활", 130: "게임",
        140: "반려동물/취미", 150: "도서/음반/문구",
        160: "티켓/쿠폰", 170: "스포츠/레저",
        180: "자동차/오토바이",
    }

    # 번개장터 카테고리 API
    CATEGORIES_API_URL = "https://api.bunjang.co.kr/api/1/categories/list.json"

    # 카테고리 캐시 (런타임 중 API에서 동적으로 로드)
    _api_categories_cache: Optional[dict] = None  # {id: {id, title, parent_id, depth, children: [...]}}
    _api_top_categories_cache: Optional[list] = None  # 최상단 카테고리 목록

    # ── 하위(중분류) 카테고리 ──
    # find_v2 API로 키워드 없이 최근 매물을 조회할 때 사용하는 카테고리.
    # 상위 카테고리 일부는 하위 카테고리가 없어도 조회 가능하지만,
    # 일부(160 등)는 반드시 하위 카테고리를 사용해야 합니다.
    SUBCATEGORY_MAP = {
        # 여성의류 (310)
        310100: "여성 상의", 310200: "여성 하의", 310300: "여성 원피스/스커트",
        310400: "여성 아우터", 310500: "여성 정장/세트",
        # 남성의류 (320)
        320100: "남성 상의", 320200: "남성 하의", 320300: "남성 아우터",
        320400: "남성 정장/세트",
        # 패션잡화 (300)
        300100: "신발", 300200: "가방", 300300: "시계",
        300400: "패션액세서리", 300500: "모자",
        # 뷰티 (400)
        400100: "스킨케어", 400200: "메이크업", 400300: "헤어케어",
        400400: "바디케어", 400500: "향수",
        # 출산/유아동 (500)
        500100: "유아동 의류", 500200: "유아용품", 500300: "출산용품",
        500400: "유아동 장난감",
        # 모바일/태블릿 (600)
        601: "스마트폰", 602: "태블릿", 600300: "모바일 액세서리",
        600400: "웨어러블",
        # 가전제품 (700)
        700100: "주방가전", 700200: "생활가전", 700300: "계절가전",
        700400: "영상가전", 700500: "음향가전",
        # 노트북/PC (800)
        800100: "노트북", 800200: "데스크탑", 800300: "PC 부품",
        800400: "모니터", 800500: "PC 주변기기",
        # 카메라 (900)
        900100: "디지털카메라", 900200: "캠코더", 900300: "렌즈",
        900400: "카메라 액세서리",
        # 가구/인테리어 (110)
        110100: "침대/매트리스", 110200: "책상/테이블", 110300: "의자/소파",
        110400: "수납/선반", 110500: "인테리어 소품",
        # 리빙/생활 (120)
        120100: "주방용품", 120200: "욕실용품", 120300: "청소용품",
        120400: "세탁용품", 120500: "생활잡화",
        # 게임 (130)
        130100: "게임기", 130200: "게임 타이틀", 130300: "게임 액세서리",
        # 반려동물/취미 (140)
        140100: "반려동물용품", 140200: "키덜트/피규어", 140300: "핸드메이드",
        140400: "악기", 140500: "식물",
        # 도서/음반/문구 (150)
        150100: "도서", 150200: "음반/DVD", 150300: "문구",
        150400: "아이돌 굿즈",
        # 티켓/쿠폰 (160)
        160100: "티켓", 160200: "쿠폰", 160300: "상품권",
        # 스포츠/레저 (170)
        170100: "골프", 170200: "캠핑", 170300: "자전거",
        170400: "헬스/요가", 170500: "수상스포츠",
        170600: "스키/보드", 170700: "등산/아웃도어",
        # 자동차/오토바이 (180)
        180100: "자동차", 180200: "오토바이", 180300: "자동차 용품",
    }

    def __init__(self, delay: float = 1.0):
        """
        Args:
            delay: 요청 간 대기 시간(초)
        """
        self.delay = delay
        self._subcategory_cache: Optional[dict] = None  # 동적 카테고리 캐시
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://m.bunjang.co.kr/",
            "Origin": "https://m.bunjang.co.kr",
        })
        self._last_request_time = 0

    def _throttle(self):
        """요청 간격 제한"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()

    def _parse_item(self, item: dict) -> dict:
        """상품 아이템 파싱"""
        pid = str(item.get("pid", item.get("product_id", "")))

        # 가격
        price = item.get("price", "0")
        if isinstance(price, str):
            price = int(re.sub(r'[^\d]', '', price) or 0)
        else:
            price = int(price)

        # 이미지
        image_url = ""
        if item.get("product_image"):
            image_url = item["product_image"]
        elif item.get("image"):
            image_url = item["image"]
        elif item.get("img"):
            image_url = item["img"]

        # 상태
        status_raw = item.get("status", "")
        if status_raw in ("0", 0, "판매중"):
            status = "판매중"
        elif status_raw in ("1", 1, "예약중"):
            status = "예약중"
        elif status_raw in ("2", 2, "판매완료"):
            status = "판매완료"
        elif status_raw in ("3", 3):
            status = "숨김"
        else:
            status = str(status_raw) if status_raw else "판매중"

        # 시간
        update_time = item.get("update_time", item.get("updated_at", ""))
        if isinstance(update_time, (int, float)) and update_time > 0:
            try:
                from datetime import datetime
                update_time = datetime.fromtimestamp(update_time).strftime("%Y-%m-%d %H:%M")
            except (OSError, ValueError):
                update_time = str(update_time)

        return {
            "id": pid,
            "title": item.get("name", item.get("title", "")),
            "price": price,
            "price_str": f"{price:,}원" if price > 0 else "가격미정",
            "image_url": image_url,
            "status": status,
            "location": item.get("location", item.get("area", "")),
            "time": update_time,
            "url": f"{self.BASE_URL}/product/{pid}",
            "seller": item.get("seller_name", item.get("store_name", "")),
            "likes": item.get("wish_cnt", item.get("like_count", 0)),
            "views": item.get("view_cnt", item.get("view_count", 0)),
            "safe_payment": item.get("safe_payment", item.get("bunpay", False)),
            "category": item.get("category_name", ""),
            "free_shipping": item.get("free_shipping", False),
        }

    def search(
        self,
        keyword: str,
        page: int = 1,
        count: int = 20,
        sort: str = "recommend",
        category: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        exclude_sold: bool = True,
    ) -> list[dict]:
        """
        번개장터 매물 검색

        Args:
            keyword: 검색어
            page: 페이지 번호 (1부터 시작)
            count: 한 페이지당 결과 수 (최대 100)
            sort: 정렬 기준 (recommend, recent, price_asc, price_desc)
            category: 카테고리 코드 (None이면 전체)
            min_price: 최소 가격
            max_price: 최대 가격
            exclude_sold: 판매완료 제외 여부

        Returns:
            검색 결과 리스트
        """
        self._throttle()

        sort_value = self.SORT_MAP.get(sort, "score")
        api_page = page - 1  # 번개장터 API는 0-based

        params = {
            "q": keyword,
            "order": sort_value,
            "page": api_page,
            "n": min(count, 100),
            "stat": "v2",
        }

        if category:
            params["category"] = category
        if min_price is not None and min_price > 0:
            params["price_min"] = min_price
        if max_price is not None:
            params["price_max"] = max_price
        if exclude_sold:
            params["req_ref"] = "search"
            params["stat_status"] = "s"

        try:
            response = self.session.get(
                self.SEARCH_API_URL, params=params, timeout=15
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            print(f"[오류] API 요청 실패: {e}")
            # 폴백: 웹 페이지 스크래핑
            return self._search_fallback(keyword, page, count, sort)
        except json.JSONDecodeError:
            print("[오류] JSON 파싱 실패. 웹 페이지 방식으로 재시도합니다.")
            return self._search_fallback(keyword, page, count, sort)

        items_raw = data.get("list", data.get("items", []))
        total = data.get("num_found", data.get("total", 0))

        results = []
        for item in items_raw:
            parsed = self._parse_item(item)
            if parsed["title"]:
                # 판매완료 필터 (API에서 안 걸러진 경우 대비)
                if exclude_sold and parsed["status"] == "판매완료":
                    continue
                results.append(parsed)

        if results:
            print(f"[검색완료] '{keyword}' - 총 {total}개 중 {len(results)}개 조회")
        else:
            print(f"[검색완료] '{keyword}' - 검색 결과 없음 (total={total})")

        return results

    def _search_fallback(
        self, keyword: str, page: int, count: int, sort: str
    ) -> list[dict]:
        """
        API 실패 시 웹 페이지에서 __NEXT_DATA__ 파싱으로 폴백
        """
        self._throttle()
        encoded = quote(keyword)
        url = f"{self.BASE_URL}/search/products?q={encoded}&page={page}"
        if sort != "recommend":
            sort_value = self.SORT_MAP.get(sort, "score")
            url += f"&order={sort_value}"

        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"[오류] 웹 페이지 요청 실패: {e}")
            return []

        # __NEXT_DATA__ 추출
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            response.text, re.DOTALL
        )
        if not match:
            print("[오류] 페이지 데이터를 찾을 수 없습니다.")
            return []

        try:
            next_data = json.loads(match.group(1))
        except json.JSONDecodeError:
            print("[오류] JSON 파싱 실패")
            return []

        # dehydratedState에서 검색 결과 추출
        queries = (
            next_data.get("props", {})
            .get("pageProps", {})
            .get("dehydratedState", {})
            .get("queries", [])
        )

        items_raw = []
        for q in queries:
            state_data = q.get("state", {}).get("data", {})
            if isinstance(state_data, dict):
                # pages 구조 (infinite query)
                pages = state_data.get("pages", [])
                for p in pages:
                    items_raw.extend(p.get("list", p.get("items", [])))
                # flat 구조
                if not items_raw:
                    items_raw = state_data.get("list", state_data.get("items", []))

        results = []
        for item in items_raw[:count]:
            parsed = self._parse_item(item)
            if parsed["title"]:
                results.append(parsed)

        print(f"[검색완료-폴백] '{keyword}' - {len(results)}개 조회")
        return results

    # ──────────────────────────────────────────────────────────────────
    # 카테고리별 최근 매물 수집
    # ──────────────────────────────────────────────────────────────────

    # ──────────────────────────────────────────────────────────────────
    # 번개장터 공식 카테고리 API 연동
    # ──────────────────────────────────────────────────────────────────

    def fetch_categories(self, use_cache: bool = True) -> dict:
        """
        번개장터 공식 카테고리 API에서 전체 카테고리 트리를 가져옵니다.

        Returns:
            {
              "top_categories": [{id, title, count, icon_url, children: [...]}, ...],
              "flat": {id: {id, title, count, parent_id, depth, icon_url}, ...}
            }
        """
        if use_cache and BunjangScraper._api_categories_cache is not None:
            return {
                "top_categories": BunjangScraper._api_top_categories_cache,
                "flat": BunjangScraper._api_categories_cache,
            }

        self._throttle()
        try:
            response = self.session.get(self.CATEGORIES_API_URL, timeout=15)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, json.JSONDecodeError) as e:
            print(f"[카테고리 API 오류] {e}")
            return {"top_categories": [], "flat": {}}

        if data.get("result") != "success":
            print(f"[카테고리 API 오류] result={data.get('result')}")
            return {"top_categories": [], "flat": {}}

        flat: dict = {}
        top_categories = []

        def _parse_node(node: dict, parent_id: Optional[str], depth: int) -> dict:
            cat_id = str(node["id"])
            children_raw = node.get("categories", [])
            children_parsed = [_parse_node(c, cat_id, depth + 1) for c in children_raw]

            entry = {
                "id": cat_id,
                "title": node.get("title", ""),
                "count": node.get("count", 0),
                "parent_id": parent_id,
                "depth": depth,
                "icon_url": node.get("icon_url", ""),
                "children": children_parsed,
            }
            flat[cat_id] = {
                k: v for k, v in entry.items() if k != "children"
            }
            flat[cat_id]["children"] = [c["id"] for c in children_parsed]
            return entry

        for top in data.get("categories", []):
            top_categories.append(_parse_node(top, None, 0))

        BunjangScraper._api_categories_cache = flat
        BunjangScraper._api_top_categories_cache = top_categories

        print(f"[카테고리 로드] 최상단 {len(top_categories)}개, 전체 {len(flat)}개")
        return {"top_categories": top_categories, "flat": flat}

    def get_top_categories(self, use_cache: bool = True) -> list[dict]:
        """
        번개장터 최상단(depth=0) 카테고리 목록을 반환합니다.

        Returns:
            [{id, title, count, icon_url, children: [하위카테고리...]}, ...]
        """
        result = self.fetch_categories(use_cache=use_cache)
        return result["top_categories"]

    def get_recent_by_top_categories(
        self,
        count: int = 20,
        top_category_ids: Optional[list] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        exclude_sold: bool = True,
        max_workers: int = 5,
        within_minutes: Optional[int] = None,
        use_cache: bool = True,
    ) -> dict:
        """
        번개장터 최상단 카테고리별 최근 매물 리스트를 반환합니다.

        최상단 카테고리 → 2단계(중분류) 카테고리 코드로 API를 호출해
        카테고리별로 최근 매물을 병렬 수집합니다.

        Args:
            count              : 각 중분류 카테고리당 수집 개수 (기본 20, 최대 100)
            top_category_ids   : 조회할 최상단 카테고리 id 리스트 (str). None이면 전체.
            min_price          : 최소 가격
            max_price          : 최대 가격
            exclude_sold       : 판매완료 제외
            max_workers        : 병렬 스레드 수
            within_minutes     : N분 이내 매물만 반환
            use_cache          : 카테고리 API 캐시 사용 여부

        Returns:
            {
              "top_categories": [
                {
                  "id": "310",
                  "title": "여성의류",
                  "count": ...,       # 번개장터 총 매물 수
                  "icon_url": "...",
                  "listings": [{...}, ...],  # 최근 매물 리스트
                  "listings_count": 42,
                },
                ...
              ],
              "total_listings": 500,
              "elapsed_seconds": 3.2,
            }
        """
        import time as _time
        start = _time.time()

        cat_data = self.fetch_categories(use_cache=use_cache)
        top_cats = cat_data["top_categories"]
        flat = cat_data["flat"]

        # 최상단 카테고리 필터링
        if top_category_ids:
            top_cats = [c for c in top_cats if str(c["id"]) in [str(x) for x in top_category_ids]]

        per_cat = min(count, 100)
        print(
            f"[번개장터-카테고리별최근매물] 최상단 카테고리 {len(top_cats)}개 수집 시작 "
            f"(카테고리당 최대 {per_cat}개, workers={max_workers})"
        )

        # 최상단 카테고리 id를 직접 f_category_id로 사용
        from collections import defaultdict
        top_results: dict = defaultdict(list)
        seen_ids: set = set()

        def _fetch_top(top_node: dict) -> tuple[str, list[dict]]:
            top_id = str(top_node["id"])
            items = self._fetch_category_recent(
                int(top_id),
                page=0,
                count=per_cat,
                min_price=min_price,
                max_price=max_price,
                exclude_sold=exclude_sold,
                use_f_category=True,
            )
            return top_id, items

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_fetch_top, top): str(top["id"]) for top in top_cats}
            for future in as_completed(futures):
                try:
                    top_id, items = future.result()
                    for item in items:
                        item_id = item.get("id")
                        if item_id and item_id not in seen_ids:
                            seen_ids.add(item_id)
                            top_results[top_id].append(item)
                except Exception as e:
                    top_id = futures[future]
                    print(f"  [오류] top={top_id}: {e}")

        # 시간 필터
        if within_minutes is not None:
            cutoff = datetime.now() - timedelta(minutes=within_minutes)
            for top_id in top_results:
                before = len(top_results[top_id])
                top_results[top_id] = [
                    r for r in top_results[top_id] if self._parse_dt(r) >= cutoff
                ]
                after = len(top_results[top_id])
                if before != after:
                    print(f"  [시간필터] top={top_id}: {before}→{after}")

        # 각 카테고리 내에서 최신순 정렬
        for top_id in top_results:
            top_results[top_id].sort(key=self._parse_dt, reverse=True)

        # 결과 조립
        total = 0
        output_cats = []
        for top in top_cats:
            top_id = str(top["id"])
            listings = top_results.get(top_id, [])
            total += len(listings)
            output_cats.append({
                "id": top_id,
                "title": top["title"],
                "count": top.get("count", 0),
                "icon_url": top.get("icon_url", ""),
                "listings": listings,
                "listings_count": len(listings),
            })

        elapsed = round(_time.time() - start, 2)
        print(f"[번개장터-카테고리별최근매물] 완료 - 총 {total}개 ({elapsed}초)")

        return {
            "top_categories": output_cats,
            "total_listings": total,
            "elapsed_seconds": elapsed,
        }

    def _expand_to_subcategories(self, categories: list[int]) -> list[int]:
        """
        상위 카테고리 코드를 하위 카테고리 코드로 확장합니다.

        예: [160] → [160100, 160200, 160300]
        이미 하위 카테고리인 코드(예: 160100)는 그대로 유지합니다.
        상위도 하위도 아닌 알 수 없는 코드는 그대로 포함합니다(API에서 걸러짐).
        """
        expanded = []
        for cat in categories:
            if cat in self.SUBCATEGORY_MAP:
                # 이미 하위 카테고리 → 그대로 사용
                expanded.append(cat)
            elif cat in self.CATEGORY_MAP:
                # 상위 카테고리 → 하위 카테고리들로 확장
                cat_prefix = str(cat)
                children = [
                    sub_code for sub_code in self.SUBCATEGORY_MAP
                    if str(sub_code).startswith(cat_prefix) and sub_code != cat
                ]
                if children:
                    expanded.extend(children)
                    print(f"  [카테고리 확장] {self.CATEGORY_MAP[cat]}({cat}) → 하위 {len(children)}개")
                else:
                    # 하위 카테고리가 맵에 없으면 원본 코드 시도
                    expanded.append(cat)
            else:
                # 알 수 없는 코드 → 그대로 시도
                expanded.append(cat)
        return expanded

    def _fetch_category_recent(
        self,
        category: int,
        page: int = 0,
        count: int = 100,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        exclude_sold: bool = True,
        use_f_category: bool = False,
    ) -> list[dict]:
        """
        단일 카테고리의 최근 매물을 API로 조회합니다.

        use_f_category=True 이면 f_category_id 파라미터를 사용합니다.
        (popular_category 방식 - 최상단 카테고리 id 직접 조회에 사용)
        """
        self._throttle()

        import time as _t
        request_id = int(_t.time())

        if use_f_category:
            params = {
                "f_category_id": category,
                "page": page,
                "order": "date",
                "req_ref": "popular_category",
                "request_id": request_id,
                "stat_device": "w",
                "n": min(count, 100),
                "version": 4,
            }
        else:
            params = {
                "order": "date",
                "page": page,
                "n": min(count, 100),
                "stat": "v2",
                "category": category,
            }

        if min_price is not None and min_price > 0:
            params["price_min"] = min_price
        if max_price is not None:
            params["price_max"] = max_price
        if exclude_sold and not use_f_category:
            params["req_ref"] = "search"
            params["stat_status"] = "s"

        cat_name = (
            self.SUBCATEGORY_MAP.get(category)
            or self.CATEGORY_MAP.get(category)
            or str(category)
        )

        try:
            response = self.session.get(
                self.SEARCH_API_URL, params=params, timeout=15
            )
            # 400 에러: 상위 카테고리로 조회 시 ERR_INVALID_PARAMETER 발생
            if response.status_code == 400:
                try:
                    err = response.json()
                    reason = err.get("reason", "")
                except Exception:
                    reason = response.text[:200]
                print(f"  [카테고리:{cat_name}({category})] API 400 에러 - {reason} (skip)")
                return []
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, json.JSONDecodeError) as e:
            print(f"  [카테고리:{cat_name}({category})] API 요청 실패: {e}")
            return []

        items_raw = data.get("list", data.get("items", []))

        results = []
        for item in items_raw:
            parsed = self._parse_item(item)
            if parsed["title"]:
                if exclude_sold and parsed["status"] == "판매완료":
                    continue
                if not parsed["category"]:
                    parsed["category"] = cat_name
                results.append(parsed)

        print(f"  [카테고리:{cat_name}({category})] {len(results)}개 수집")
        return results

    @staticmethod
    def _parse_dt(item: dict) -> datetime:
        """매물의 등록/수정 시간을 datetime으로 파싱"""
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

    def get_recent_listings(
        self,
        count: int = 100,
        categories: Optional[list] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        exclude_sold: bool = True,
        max_workers: int = 5,
        within_minutes: Optional[int] = None,
    ) -> list[dict]:
        """
        전체 카테고리의 최신 매물을 병렬 수집합니다.

        번개장터 find_v2 API에 키워드 없이 category + order=date 로
        각 카테고리의 최신 매물을 가져온 뒤 통합·정렬합니다.

        상위 카테고리(310, 160 등)로는 키워드 없는 조회가 불가하므로,
        기본적으로 SUBCATEGORY_MAP(하위 카테고리)을 사용합니다.
        categories 파라미터로 직접 지정한 경우 해당 코드를 그대로 사용하며,
        API 400 에러가 발생하면 해당 카테고리를 건너뜁니다.

        Args:
            count         : 카테고리당 수집 개수 (기본 100, 최대 100)
            categories    : 조회할 카테고리 코드 리스트. None이면 전체 하위 카테고리.
            min_price     : 최소 가격
            max_price     : 최대 가격
            exclude_sold  : 판매완료 제외 (기본 True)
            max_workers   : 병렬 스레드 수 (기본 5)
            within_minutes: 지정 시, 현재 시각 기준 N분 이내 등록된 매물만 반환.

        Returns:
            수집된 매물 리스트 (등록 시간 최신순 정렬)
        """
        start = time.time()
        # categories 지정 시 해당 코드 사용, 아니면 전체 하위 카테고리 사용
        if categories:
            target_cats = self._expand_to_subcategories(categories)
        else:
            target_cats = list(self.SUBCATEGORY_MAP.keys())
        per_cat = min(count, 100)

        print(
            f"[번개장터-최근매물] 카테고리 {len(target_cats)}개 병렬 수집 시작 "
            f"(카테고리당 최대 {per_cat}개, workers={max_workers}"
            + (f", 최근 {within_minutes}분 이내" if within_minutes else "")
            + ")"
        )

        all_results: list[dict] = []
        seen_ids: set = set()

        def _fetch(cat: int) -> list[dict]:
            return self._fetch_category_recent(
                cat, page=0, count=per_cat,
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
            print(f"[번개장터-최근매물] 시간 필터({within_minutes}분): {before}개 → {len(all_results)}개")

        # 최신순 정렬
        all_results.sort(key=self._parse_dt, reverse=True)

        elapsed = round(time.time() - start, 2)
        print(f"[번개장터-최근매물] 최종 {len(all_results)}개 수집 완료 - 중복 제거 후 ({elapsed}초)")
        return all_results

    # ──────────────────────────────────────────────────────────────────
    # 다중 페이지 검색
    # ──────────────────────────────────────────────────────────────────

    def search_all(
        self,
        keyword: str,
        max_pages: int = 5,
        **kwargs,
    ) -> list[dict]:
        """
        여러 페이지에 걸쳐 검색

        Args:
            keyword: 검색어
            max_pages: 최대 페이지 수
            **kwargs: search()에 전달할 추가 인자

        Returns:
            모든 페이지의 검색 결과
        """
        all_results = []
        for page in range(1, max_pages + 1):
            results = self.search(keyword, page=page, **kwargs)
            if not results:
                break
            all_results.extend(results)
            print(f"  ... {page}페이지 완료 (누적 {len(all_results)}개)")
        return all_results

    @staticmethod
    def format_results(results: list[dict], show_url: bool = True) -> str:
        """검색 결과를 보기 좋게 포맷팅"""
        if not results:
            return "검색 결과가 없습니다."

        lines = []
        lines.append(f"{'='*60}")
        lines.append(f" 번개장터 검색 결과: {len(results)}개")
        lines.append(f"{'='*60}")

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
            if item.get("safe_payment"):
                lines.append(f"    🔒 안전결제: 지원")
            if show_url:
                lines.append(f"    🔗 링크: {item['url']}")
            lines.append(f"    {'─'*40}")

        return "\n".join(lines)
