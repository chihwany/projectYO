"""
중고 매물 검색 REST API 서버
중고나라 + 번개장터 + 당근 통합 검색 API

실행: python server.py
기본 주소: http://localhost:5000
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from scrapers.joongna_scraper import JoongnaScraper
from scrapers.bunjang_scraper import BunjangScraper
from scrapers.daangn_scraper import DaangnScraper
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

app = Flask(__name__)
app.json.ensure_ascii = False
CORS(app)

# 스크래퍼 인스턴스
joongna = JoongnaScraper(delay=0.5)
bunjang = BunjangScraper(delay=0.5)
daangn = DaangnScraper(delay=0.5)

# 동시 검색용 스레드풀
executor = ThreadPoolExecutor(max_workers=6)


# ─────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────

def _parse_common_params():
    """공통 쿼리 파라미터 파싱"""
    keyword = request.args.get("keyword", "").strip()
    page = request.args.get("page", 1, type=int)
    count = request.args.get("count", 20, type=int)
    sort = request.args.get("sort", "recommend")
    category = request.args.get("category", None, type=int)
    min_price = request.args.get("min_price", None, type=int)
    max_price = request.args.get("max_price", None, type=int)
    exclude_sold = request.args.get("exclude_sold", "true").lower() != "false"
    region = request.args.get("region", "").strip()

    return {
        "keyword": keyword,
        "page": max(1, page),
        "count": min(max(1, count), 100),
        "sort": sort,
        "category": category,
        "min_price": min_price,
        "max_price": max_price,
        "exclude_sold": exclude_sold,
        "region": region or None,
    }


def _error(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status


def _success(data, **extra):
    result = {"success": True, "data": data}
    result.update(extra)
    return jsonify(result)


# ─────────────────────────────────────────────
# API 엔드포인트
# ─────────────────────────────────────────────

@app.route("/")
def index():
    """API 안내"""
    return jsonify({
        "name": "중고 매물 검색 API",
        "version": "4.0.0",
        "endpoints": {
            "GET /api/search": "통합 검색 (중고나라 + 번개장터 + 당근)",
            "GET /api/joongna/search": "중고나라 검색",
            "GET /api/joongna/recent": "중고나라 전체 최근 매물 목록 (전체 카테고리 병렬 수집)",
            "GET /api/bunjang/search": "번개장터 검색",
            "GET /api/bunjang/recent": "번개장터 전체 최근 매물 목록 (전체 카테고리 병렬 수집)",
            "GET /api/daangn/search": "당근 검색",
            "GET /api/joongna/product/<id>": "중고나라 상품 상세",
            "GET /api/joongna/categories": "중고나라 카테고리 목록",
            "GET /api/bunjang/categories": "번개장터 카테고리 목록 (공식 API 트리 또는 static)",
            "GET /api/bunjang/categories/top": "번개장터 최상단 카테고리 목록 (id, title, count, icon)",
            "GET /api/bunjang/recent-by-category": "번개장터 최상단 카테고리별 최근 매물 리스트",
            "GET /api/daangn/categories": "당근 카테고리 목록",
            "GET /api/daangn/regions/search?q=": "당근 지역 검색 (웹 스크래핑 기반)",
            "GET /api/daangn/regions/locations?keyword=": "당근 지역 검색 (당근 API 기반, 동/읍/면 레벨 포함)",
            "GET /api/daangn/regions/cities": "당근 시/도 목록",
            "GET /api/daangn/regions/districts?city=": "당근 특정 시/도의 구/군 목록",
        },
        "common_params": {
            "keyword": "(필수) 검색어",
            "page": "(선택) 페이지 번호, 기본 1",
            "count": "(선택) 결과 수, 기본 20, 최대 100",
            "sort": "(선택) recommend | recent | price_asc | price_desc",
            "category": "(선택) 카테고리 코드",
            "min_price": "(선택) 최소 가격",
            "max_price": "(선택) 최대 가격",
            "exclude_sold": "(선택) 판매완료 제외, 기본 true",
            "region": "(선택, 당근) 지역명 또는 코드 (예: 서초4동, 강남구, 역삼동-360)",
        },
        "examples": [
            "/api/search?keyword=아이폰 16",
            "/api/joongna/recent",
            "/api/joongna/recent?within_minutes=2",
            "/api/joongna/recent?categories=6,7,8&count=30",
            "/api/joongna/recent?within_minutes=10&min_price=10000&max_price=500000",
            "/api/bunjang/recent",
            "/api/bunjang/recent?within_minutes=5",
            "/api/bunjang/recent?categories=600,601,800&count=50",
            "/api/bunjang/recent?within_minutes=10&min_price=10000&max_price=500000",
            "/api/bunjang/categories/top",
            "/api/bunjang/recent-by-category",
            "/api/bunjang/recent-by-category?count=30&within_minutes=10",
            "/api/bunjang/recent-by-category?top_categories=310,320&count=20",
            "/api/bunjang/recent-by-category?top_categories=600&min_price=50000",
            "/api/daangn/search?keyword=맥북&region=강남구",
            "/api/daangn/regions/search?q=강남",
            "/api/daangn/regions/search?q=판교&limit=5",
            "/api/daangn/regions/locations?keyword=경기도",
            "/api/daangn/regions/locations?keyword=덕양구",
            "/api/daangn/regions/locations?keyword=행신동",
            "/api/daangn/regions/cities",
            "/api/daangn/regions/districts?city=경기도",
        ],
    })


# ─── 통합 검색 ───

@app.route("/api/search")
def search_all():
    """중고나라 + 번개장터 + 당근 통합 검색"""
    params = _parse_common_params()
    if not params["keyword"]:
        return _error("keyword 파라미터가 필요합니다.")

    start_time = time.time()

    futures = {
        executor.submit(_search_joongna, params): "joongna",
        executor.submit(_search_bunjang, params): "bunjang",
        executor.submit(_search_daangn, params): "daangn",
    }

    joongna_results, bunjang_results, daangn_results = [], [], []

    for future in as_completed(futures.keys(), timeout=30):
        name = futures[future]
        try:
            result = future.result()
            if name == "joongna":
                joongna_results = result
            elif name == "bunjang":
                bunjang_results = result
            elif name == "daangn":
                daangn_results = result
        except Exception as e:
            print(f"[{name} 오류] {e}")

    elapsed = round(time.time() - start_time, 2)

    def _tag_source(items: list, source: str) -> list:
        for item in items:
            item["source"] = source
        return items

    combined = (
        _tag_source(joongna_results, "joongna")
        + _tag_source(bunjang_results, "bunjang")
        + _tag_source(daangn_results, "daangn")
    )

    def _parse_time_for_sort(item: dict):
        from datetime import datetime
        raw = str(item.get("time") or "").strip().rstrip("Z")
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        from datetime import datetime as dt
        return dt.min

    combined.sort(key=_parse_time_for_sort, reverse=True)

    return _success(
        combined,
        keyword=params["keyword"],
        region=params["region"],
        total_count=len(combined),
        joongna_count=len(joongna_results),
        bunjang_count=len(bunjang_results),
        daangn_count=len(daangn_results),
        elapsed_seconds=elapsed,
    )


# ─── 중고나라 ───

@app.route("/api/joongna/search")
def search_joongna():
    params = _parse_common_params()
    if not params["keyword"]:
        return _error("keyword 파라미터가 필요합니다.")
    start_time = time.time()
    results = _search_joongna(params)
    return _success(results, keyword=params["keyword"], count=len(results),
                    page=params["page"], elapsed_seconds=round(time.time() - start_time, 2),
                    source="joongna")


@app.route("/api/joongna/recent")
def joongna_recent():
    """
    중고나라 전체 최근 등록 매물 목록

    전체 카테고리(20개)를 병렬로 조회하여 최신순으로 통합합니다.
    (중고나라 SSR은 키워드/카테고리 없이 sort만 보내면 500 에러를 반환하므로,
    반드시 카테고리를 함께 지정해야 합니다.)

    Query params:
      count          (int)   카테고리당 수집 개수, 기본 50 / 최대 50
      categories     (str)   콤마 구분 카테고리 코드 (예: 6,7,8) | 없으면 전체 20개
      min_price      (int)   최소 가격
      max_price      (int)   최대 가격
      exclude_sold   (bool)  판매완료 제외, 기본 true
      within_minutes (int)   N분 이내 등록된 매물만 반환 (기본: 필터 없음)
      workers        (int)   병렬 스레드 수, 기본 5
    """
    count = min(max(request.args.get("count", 50, type=int), 1), 50)
    categories_raw = request.args.get("categories", "").strip()
    categories = (
        [int(c) for c in categories_raw.split(",") if c.strip().isdigit()]
        if categories_raw else None
    )
    min_price = request.args.get("min_price", None, type=int)
    max_price = request.args.get("max_price", None, type=int)
    exclude_sold = request.args.get("exclude_sold", "true").lower() != "false"
    within_minutes = request.args.get("within_minutes", None, type=int)
    workers = min(max(request.args.get("workers", 5, type=int), 1), 10)

    start_time = time.time()
    try:
        kwargs = {
            "count": count,
            "exclude_sold": exclude_sold,
            "max_workers": workers,
        }
        if categories:
            kwargs["categories"] = categories
        if min_price is not None:
            kwargs["min_price"] = min_price
        if max_price is not None:
            kwargs["max_price"] = max_price
        if within_minutes is not None:
            kwargs["within_minutes"] = within_minutes

        results = joongna.get_recent_listings(**kwargs)
    except Exception as e:
        return _error(f"최근 매물 조회 실패: {e}", 500)

    return _success(
        results,
        count=len(results),
        categories_scanned=len(categories) if categories else len(JoongnaScraper.CATEGORY_MAP),
        within_minutes=within_minutes,
        elapsed_seconds=round(time.time() - start_time, 2),
        source="joongna",
    )


@app.route("/api/joongna/product/<int:product_id>")
def joongna_product_detail(product_id):
    detail = joongna.get_product_detail(product_id)
    if not detail:
        return _error("상품을 찾을 수 없습니다.", 404)
    return _success(detail, source="joongna")


@app.route("/api/joongna/categories")
def joongna_categories():
    categories = [{"code": c, "name": n} for c, n in JoongnaScraper.CATEGORY_MAP.items()]
    return _success(categories, source="joongna")


# ─── 번개장터 ───

@app.route("/api/bunjang/search")
def search_bunjang():
    params = _parse_common_params()
    if not params["keyword"]:
        return _error("keyword 파라미터가 필요합니다.")
    start_time = time.time()
    results = _search_bunjang(params)
    return _success(results, keyword=params["keyword"], count=len(results),
                    page=params["page"], elapsed_seconds=round(time.time() - start_time, 2),
                    source="bunjang")


@app.route("/api/bunjang/recent")
def bunjang_recent():
    """
    번개장터 전체 최근 등록 매물 목록

    전체 카테고리를 병렬로 조회하여 최신순으로 통합합니다.

    Query params:
      count          (int)   카테고리당 수집 개수, 기본 100 / 최대 100
      categories     (str)   콤마 구분 카테고리 코드 (예: 600,601,800) | 없으면 전체
      min_price      (int)   최소 가격
      max_price      (int)   최대 가격
      exclude_sold   (bool)  판매완료 제외, 기본 true
      within_minutes (int)   N분 이내 등록된 매물만 반환 (기본: 필터 없음)
      workers        (int)   병렬 스레드 수, 기본 5
    """
    count = min(max(request.args.get("count", 100, type=int), 1), 100)
    categories_raw = request.args.get("categories", "").strip()
    categories = (
        [int(c) for c in categories_raw.split(",") if c.strip().isdigit()]
        if categories_raw else None
    )
    min_price = request.args.get("min_price", None, type=int)
    max_price = request.args.get("max_price", None, type=int)
    exclude_sold = request.args.get("exclude_sold", "true").lower() != "false"
    within_minutes = request.args.get("within_minutes", None, type=int)
    workers = min(max(request.args.get("workers", 5, type=int), 1), 10)

    start_time = time.time()
    try:
        kwargs = {
            "count": count,
            "exclude_sold": exclude_sold,
            "max_workers": workers,
        }
        if categories:
            kwargs["categories"] = categories
        if min_price is not None:
            kwargs["min_price"] = min_price
        if max_price is not None:
            kwargs["max_price"] = max_price
        if within_minutes is not None:
            kwargs["within_minutes"] = within_minutes

        results = bunjang.get_recent_listings(**kwargs)
    except Exception as e:
        return _error(f"최근 매물 조회 실패: {e}", 500)

    return _success(
        results,
        count=len(results),
        categories_scanned=len(categories) if categories else len(BunjangScraper.SUBCATEGORY_MAP),
        within_minutes=within_minutes,
        elapsed_seconds=round(time.time() - start_time, 2),
        source="bunjang",
    )


@app.route("/api/bunjang/categories")
def bunjang_categories():
    """
    번개장터 구분별 카테고리 목록

    Query params:
      source  (str)  "api"(default) | "static"
                     api    : 번개장터 공식 API에서 실시간 트리 구조로 반환
                     static : 코드에 하드코딩된 CATEGORY_MAP + SUBCATEGORY_MAP 반환
      refresh (bool) 캐시 무시하고 API를 새로 호출 (source=api 시만 유효)
    """
    src = request.args.get("source", "api").lower()
    refresh = request.args.get("refresh", "false").lower() == "true"

    if src == "static":
        top = [{"code": c, "name": n, "level": "top"} for c, n in BunjangScraper.CATEGORY_MAP.items()]
        sub = [{"code": c, "name": n, "level": "sub"} for c, n in BunjangScraper.SUBCATEGORY_MAP.items()]
        return _success(top + sub, source="bunjang", data_source="static",
                        top_count=len(top), sub_count=len(sub))

    # source=api : 실시간 API 호출
    try:
        cat_data = bunjang.fetch_categories(use_cache=not refresh)
    except Exception as e:
        return _error(f"카테고리 API 오류: {e}", 500)

    top_cats = cat_data["top_categories"]
    return _success(
        top_cats,
        source="bunjang",
        data_source="api",
        top_count=len(top_cats),
        total_count=len(cat_data["flat"]),
    )


@app.route("/api/bunjang/categories/top")
def bunjang_top_categories():
    """
    번개장터 최상단(depth=0) + 중분류(depth=1) 2단계 카테고리 목록

    예: 310(여성의류) → children: [310300(아우터), 310260(상의), ...]
    중분류(depth=1)의 하위(소분류, depth=2+)는 포함하지 않습니다.

    Query params:
      refresh (bool) 캐시 무시하고 재호출
    """
    refresh = request.args.get("refresh", "false").lower() == "true"
    try:
        top_cats = bunjang.get_top_categories(use_cache=not refresh)
    except Exception as e:
        return _error(f"카테고리 API 오류: {e}", 500)

    # 최상단 카테고리만, children 제외
    summary = [
        {
            "id": c["id"],
            "title": c["title"],
            "count": c["count"],
            "icon_url": c["icon_url"],
        }
        for c in top_cats
    ]
    return _success(summary, source="bunjang", count=len(summary))


@app.route("/api/bunjang/recent-by-category")
def bunjang_recent_by_category():
    """
    번개장터 최상단 카테고리별 최근 매물 리스트

    번개장터 공식 카테고리 API에서 최상단 카테고리를 가져온 뒤,
    각 최상단 카테고리의 중분류를 병렬 조회하여 카테고리별로 최근 매물을 반환합니다.

    Query params:
      count          (int)   중분류당 수집 개수, 기본 20 / 최대 100
      top_categories (str)   콤마 구분 최상단 카테고리 id ("310,320") | 없으면 전체
      min_price      (int)   최소 가격
      max_price      (int)   최대 가격
      exclude_sold   (bool)  판매완료 제외, 기본 true
      within_minutes (int)   N분 이내 매물만 반환
      workers        (int)   병렬 스레드 수, 기본 5
      refresh        (bool)  카테고리 캐시 무시하고 재호출

    Response 예시:
      {
        "success": true,
        "top_categories": [
          {
            "id": "310",
            "title": "여성의류",
            "count": 2484247,
            "icon_url": "https://...",
            "listings": [{...}, ...],
            "listings_count": 42
          },
          ...
        ],
        "total_listings": 820,
        "elapsed_seconds": 4.1,
        "source": "bunjang"
      }
    """
    count = min(max(request.args.get("count", 20, type=int), 1), 100)
    top_cats_raw = request.args.get("top_categories", "").strip()
    top_category_ids = (
        [c.strip() for c in top_cats_raw.split(",") if c.strip()]
        if top_cats_raw else None
    )
    min_price = request.args.get("min_price", None, type=int)
    max_price = request.args.get("max_price", None, type=int)
    exclude_sold = request.args.get("exclude_sold", "true").lower() != "false"
    within_minutes = request.args.get("within_minutes", None, type=int)
    workers = min(max(request.args.get("workers", 5, type=int), 1), 10)
    refresh = request.args.get("refresh", "false").lower() == "true"

    start_time = time.time()
    try:
        result = bunjang.get_recent_by_top_categories(
            count=count,
            top_category_ids=top_category_ids,
            min_price=min_price,
            max_price=max_price,
            exclude_sold=exclude_sold,
            max_workers=workers,
            within_minutes=within_minutes,
            use_cache=not refresh,
        )
    except Exception as e:
        return _error(f"최근 매물 조회 실패: {e}", 500)

    return jsonify({
        "success": True,
        "top_categories": result["top_categories"],
        "total_listings": result["total_listings"],
        "elapsed_seconds": round(time.time() - start_time, 2),
        "within_minutes": within_minutes,
        "source": "bunjang",
    })


# ─── 당근 ───

@app.route("/api/daangn/search")
def search_daangn():
    params = _parse_common_params()
    if not params["keyword"]:
        return _error("keyword 파라미터가 필요합니다.")
    start_time = time.time()
    results = _search_daangn(params)
    return _success(results, keyword=params["keyword"], region=params["region"],
                    count=len(results), page=params["page"],
                    elapsed_seconds=round(time.time() - start_time, 2), source="daangn")


@app.route("/api/daangn/categories")
def daangn_categories():
    categories = [{"code": c, "name": n} for c, n in DaangnScraper.CATEGORY_MAP.items()]
    return _success(categories, source="daangn")


# ─── 당근 지역 API ───

@app.route("/api/daangn/regions/search")
def daangn_regions_search():
    """
    지역명 검색 (자동완성용)
    daangn.com/kr/regions/ 스크래핑 기반, TTL 1시간 메모리 캐시.

    GET /api/daangn/regions/search?q=강남
    GET /api/daangn/regions/search?q=판교&limit=10
    """
    query = request.args.get("q", "").strip()
    limit = request.args.get("limit", 20, type=int)

    if not query:
        return _error("q 파라미터가 필요합니다. (예: ?q=강남)")

    try:
        from data.daangn_regions import search_region_live
        results = search_region_live(query, limit=min(max(1, limit), 100))
        return _success(results, query=query, count=len(results), source="daangn")
    except RuntimeError as e:
        return _error(f"당근 지역 페이지 요청 실패: {e}", 502)
    except Exception as e:
        return _error(f"서버 오류: {e}", 500)


@app.route("/api/daangn/regions/cities")
def daangn_regions_cities():
    """
    시/도 목록 반환.
    daangn.com/kr/regions/ 스크래핑 기반, TTL 1시간 메모리 캐시.

    GET /api/daangn/regions/cities
    """
    try:
        from data.daangn_regions import get_cities
        cities = get_cities()
        return _success(cities, count=len(cities), source="daangn")
    except RuntimeError as e:
        return _error(f"당근 지역 페이지 요청 실패: {e}", 502)
    except Exception as e:
        return _error(f"서버 오류: {e}", 500)


@app.route("/api/daangn/regions/locations")
def daangn_regions_locations():
    """
    당근 내부 location API 프록시.
    당근의 /v1/api/search/kr/location?keyword= 와 동일한 결과를 반환합니다.
    시/도, 구/군, 동/읍/면 등 모든 레벨의 지역을 keyword로 검색할 수 있습니다.

    GET /api/daangn/regions/locations?keyword=경기도
    GET /api/daangn/regions/locations?keyword=덕양구
    GET /api/daangn/regions/locations?keyword=행신동
    """
    keyword = request.args.get("keyword", "").strip()

    if not keyword:
        return _error("keyword 파라미터가 필요합니다. (예: ?keyword=경기도)")

    try:
        from data.daangn_regions import search_location
        locations = search_location(keyword)
        return _success(locations, keyword=keyword, count=len(locations), source="daangn")
    except RuntimeError as e:
        return _error(f"당근 location API 요청 실패: {e}", 502)
    except Exception as e:
        return _error(f"서버 오류: {e}", 500)


@app.route("/api/daangn/regions/districts")
def daangn_regions_districts():
    """
    특정 시/도의 구/군 목록 반환.
    daangn.com/kr/regions/ 스크래핑 기반, TTL 1시간 메모리 캐시.

    GET /api/daangn/regions/districts?city=서울특별시
    """
    city = request.args.get("city", "").strip()
    if not city:
        return _error("city 파라미터가 필요합니다. (예: ?city=서울특별시)")

    try:
        from data.daangn_regions import get_districts
        districts = get_districts(city)
        if not districts:
            return _error(f"'{city}' 시/도를 찾을 수 없습니다.", 404)
        return _success(districts, city=city, count=len(districts), source="daangn")
    except RuntimeError as e:
        return _error(f"당근 지역 페이지 요청 실패: {e}", 502)
    except Exception as e:
        return _error(f"서버 오류: {e}", 500)


# ─────────────────────────────────────────────
# 내부 검색 함수
# ─────────────────────────────────────────────

def _search_joongna(params: dict) -> list[dict]:
    try:
        kwargs = {
            "keyword": params["keyword"],
            "page": params["page"],
            "count": params["count"],
            "sort": params["sort"],
            "exclude_sold": params["exclude_sold"],
        }
        if params["category"]:
            kwargs["category"] = params["category"]
        if params["min_price"] is not None:
            kwargs["min_price"] = params["min_price"]
        if params["max_price"] is not None:
            kwargs["max_price"] = params["max_price"]
        return joongna.search(**kwargs)
    except Exception as e:
        print(f"[중고나라 오류] {e}")
        return []


def _search_bunjang(params: dict) -> list[dict]:
    try:
        kwargs = {
            "keyword": params["keyword"],
            "page": params["page"],
            "count": params["count"],
            "sort": params["sort"],
            "exclude_sold": params["exclude_sold"],
        }
        if params["category"]:
            kwargs["category"] = params["category"]
        if params["min_price"] is not None:
            kwargs["min_price"] = params["min_price"]
        if params["max_price"] is not None:
            kwargs["max_price"] = params["max_price"]
        return bunjang.search(**kwargs)
    except Exception as e:
        print(f"[번개장터 오류] {e}")
        return []


def _search_daangn(params: dict) -> list[dict]:
    try:
        kwargs = {
            "keyword": params["keyword"],
            "page": params["page"],
        }
        if params["region"]:
            kwargs["region"] = params["region"]
        if params["category"]:
            kwargs["category"] = params["category"]
        if params["min_price"] is not None:
            kwargs["min_price"] = params["min_price"]
        if params["max_price"] is not None:
            kwargs["max_price"] = params["max_price"]
        if params["exclude_sold"]:
            kwargs["only_on_sale"] = True
        return daangn.search(**kwargs)
    except Exception as e:
        print(f"[당근 오류] {e}")
        return []


# ─────────────────────────────────────────────
# 에러 핸들러
# ─────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return _error("엔드포인트를 찾을 수 없습니다.", 404)


@app.errorhandler(500)
def server_error(e):
    return _error("서버 내부 오류가 발생했습니다.", 500)


# ─────────────────────────────────────────────
# 서버 시작
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  중고 매물 검색 API 서버 v4.0")
    print("  http://localhost:5000")
    print("=" * 60)
    print()
    print("  엔드포인트:")
    print("   GET  /api/search                       - 통합 검색")
    print("   GET  /api/joongna/search               - 중고나라")
    print("   GET  /api/bunjang/search               - 번개장터")
    print("   GET  /api/bunjang/recent               - 번개장터 최근 매물")
    print("   GET  /api/bunjang/categories/top       - 번개장터 최상단 카테고리")
    print("   GET  /api/bunjang/recent-by-category   - 번개장터 카테고리별 최근 매물")
    print("   GET  /api/daangn/search                - 당근")
    print("   GET  /api/daangn/regions/search?q=     - 지역 검색 (웹 스크래핑)")
    print("   GET  /api/daangn/regions/locations?keyword= - 지역 검색 (당근 API, 동 레벨)")
    print("   GET  /api/daangn/regions/cities        - 시/도 목록")
    print("   GET  /api/daangn/regions/districts?city= - 구/군 목록")
    print()
    print("=" * 60)

    app.run(host="0.0.0.0", port=5000, debug=True)
