"""
ProjectYO Crawler - Flask REST API 서버

엔드포인트 추가 시 반드시:
  1. 라우트 함수 작성
  2. index() 함수의 endpoints 딕셔너리에 등록

응답 헬퍼:
  성공: _success(data)  또는  _success(data, count=N, source="bunjang")
  실패: _error("메시지", 상태코드)
  직접 jsonify() 사용 금지
"""

import logging
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# ── 공통 응답 헬퍼 ──────────────────────────────────────────────────────────────


def _success(data, *, count: int | None = None, source: str | None = None):
    """표준 성공 응답 — 직접 jsonify() 사용 금지, 반드시 이 함수 경유"""
    payload: dict = {"ok": True, "data": data}
    if count is not None:
        payload["count"] = count
    if source is not None:
        payload["source"] = source
    return jsonify(payload), 200


def _error(message: str, status: int = 400):
    """표준 에러 응답 — 직접 jsonify() 사용 금지, 반드시 이 함수 경유"""
    return jsonify({"ok": False, "error": message}), status


# ── 엔드포인트 ──────────────────────────────────────────────────────────────────


@app.get("/")
def index():
    """사용 가능한 엔드포인트 목록 반환"""
    endpoints = {
        # ── 기본 ──
        "GET /health": "서버 상태 확인",
        # ── 번개장터 ──
        "GET /api/bunjang/search": "번개장터 키워드 검색 (keyword, page, count, min_price, max_price, sort)",
        # ── 중고나라 ──
        "GET /api/joongna/search": "중고나라 키워드 검색 (keyword, page, count, min_price, max_price, sort)",
        # ── 당근 ──
        "GET /api/daangn/location": "당근 지역 검색 (keyword) — daangn_scraper.search_location() 경유",
        "GET /api/daangn/search": "당근 단건 검색 (keyword, location_id, page, count)",
        "GET /api/daangn/multi-search": "당근 구/군 단위 병렬 검색 (keyword, district, count) — 구/군명으로 하위 동 자동 조회 후 병렬 검색",
        # ── Phase 2-2: 번개장터 최신 수집 (Step 2-2에서 추가) ──
        # "GET /api/bunjang/recent": "번개장터 최신 매물 수집 (within_minutes)",
        # ── Phase 2-3: 중고나라 최신 수집 (Step 2-3에서 추가) ──
        # "GET /api/joongna/recent": "중고나라 최신 매물 수집 (within_minutes)",
    }
    return _success({"message": "ProjectYO Crawler API", "endpoints": endpoints})


@app.get("/health")
def health():
    """서버 및 의존성 상태 확인"""
    return _success({"status": "ok", "service": "crawler"})


# ── 번개장터 ────────────────────────────────────────────────────────────────────


@app.get("/api/bunjang/search")
def bunjang_search():
    """번개장터 키워드 검색"""
    from scrapers.bunjang_scraper import search

    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return _error("keyword 파라미터가 필요합니다.", 400)

    page = int(request.args.get("page", 1))
    count = int(request.args.get("count", 20))
    min_price = request.args.get("min_price", type=int)
    max_price = request.args.get("max_price", type=int)
    sort = request.args.get("sort", "recent")

    result = search(
        keyword=keyword,
        page=page,
        count=count,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
    )

    return _success(
        result["items"], count=result["total"], source="bunjang"
    )


# ── 중고나라 ──────────────────────────────────────────────────────────────────


@app.get("/api/joongna/search")
def joongna_search():
    """중고나라 키워드 검색"""
    from scrapers.joongna_scraper import search

    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return _error("keyword 파라미터가 필요합니다.", 400)

    page = int(request.args.get("page", 1))
    count = int(request.args.get("count", 20))
    min_price = request.args.get("min_price", type=int)
    max_price = request.args.get("max_price", type=int)
    sort = request.args.get("sort", "recent")

    result = search(
        keyword=keyword,
        page=page,
        count=count,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
    )

    return _success(
        result["items"], count=result["total"], source="joongna"
    )


# ── 당근 ──────────────────────────────────────────────────────────────────────


@app.get("/api/daangn/location")
def daangn_location():
    """
    당근 지역 검색.

    실제 API 호출은 daangn_scraper.search_location()에서 담당합니다.
    server.py는 keyword 유효성 검사 및 에러 처리만 수행합니다.

    Query Parameters:
        keyword (str, 필수): 지역 검색어. 시/도, 구/군, 동/읍/면 모두 지원.
                             예) 강남구, 역삼동, 능곡

    Response:
        {
          "ok": true,
          "data": {
            "locations": [
              {
                "id": 1540,
                "name": "능곡동",
                "name1": "경기도",        # 시/도
                "name2": "고양시 덕양구",  # 구/군
                "name3": "능곡동",        # 동/읍/면 (depth=3일 때)
                "name1Id": 1256,
                "name2Id": 1529,
                "name3Id": 1540,          # 이 값을 location_id로 사용
                "depth": 3                # 2=구/군, 3=동/읍/면
              }
            ]
          },
          "count": 1,
          "keyword": "능곡"
        }
    """
    import requests as _req
    from scrapers.daangn_scraper import search_location

    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return _error("keyword 파라미터가 필요합니다. (예: ?keyword=강남구)", 400)

    try:
        result = search_location(keyword)
    except _req.exceptions.Timeout:
        logger.error("당근 Location API 타임아웃 (keyword=%s)", keyword)
        return _error("당근 지역 검색 시간이 초과되었습니다. 다시 시도해 주세요.", 504)
    except _req.exceptions.RequestException as e:
        logger.error("당근 Location API 오류 (keyword=%s): %s", keyword, e)
        return _error("당근 지역 검색에 실패했습니다.", 502)

    locations = result["locations"]
    return jsonify({
        "ok": True,
        "data": {"locations": locations},
        "count": len(locations),
        "keyword": keyword,
    }), 200


@app.get("/api/daangn/search")
def daangn_search():
    """
    당근 단건 검색.

    location_id: 당근 Location API 응답의 name3Id(동) 또는 name2Id(구/군) 값.
                 Flutter 앱에서 지역 검색 후 선택된 id를 그대로 전달.
    """
    from scrapers.daangn_scraper import search

    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return _error("keyword 파라미터가 필요합니다.", 400)

    location_id = request.args.get("location_id", type=int)  # 선택: 없으면 전국
    page = int(request.args.get("page", 1))
    count = int(request.args.get("count", 20))

    result = search(
        keyword=keyword,
        location_id=location_id,
        page=page,
        count=count,
    )

    return _success(
        result["items"], count=result["total"], source="daangn"
    )


@app.get("/api/daangn/multi-search")
def daangn_multi_search():
    """
    당근 구/군 단위 병렬 매물 검색.

    구/군명(district)을 받아 당근 Location API로 하위 동 목록을 자동 조회한 뒤
    모든 동을 기준으로 keyword 매물을 병렬 검색하여 통합 반환합니다.

    Query Parameters:
        keyword  (str, 필수): 검색어 (예: '닌텐도', '아이폰')
        district (str, 필수): 구/군명 (예: '덕양구', '종로구')
        count    (int, 선택): 최대 결과 수 (기본 20)

    동작 흐름:
        1. daangn_scraper.search_by_district(keyword, district) 호출
        2. 내부에서 search_location(district)로 하위 동 location_id 수집
        3. 수집된 동 전체를 ThreadPoolExecutor로 병렬 검색
        4. 중복 제거 + 최신순 정렬 후 반환

    Response:
        {
          "ok": true,
          "data": [...],
          "count": 15,
          "source": "daangn",
          "district": "덕양구",
          "dong_count": 18
        }
    """
    import requests as _req
    from scrapers.daangn_scraper import search_by_district

    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return _error("keyword 파라미터가 필요합니다. (예: ?keyword=닌텐도)", 400)

    district = request.args.get("district", "").strip()
    if not district:
        return _error("district 파라미터가 필요합니다. (예: ?district=덕양구)", 400)

    count = int(request.args.get("count", 20))

    try:
        result = search_by_district(keyword=keyword, district=district, count=count)
    except ValueError as e:
        return _error(str(e), 404)
    except _req.exceptions.Timeout:
        logger.error("당근 multi-search Location API 타임아웃 (district=%s)", district)
        return _error("당근 지역 조회 시간이 초과되었습니다. 다시 시도해 주세요.", 504)
    except _req.exceptions.RequestException as e:
        logger.error("당근 multi-search Location API 오류 (district=%s): %s", district, e)
        return _error("당근 지역 조회에 실패했습니다.", 502)

    return jsonify({
        "ok": True,
        "data": result["items"],
        "count": result["total"],
        "source": "daangn",
        "district": result["district"],
        "dong_count": result["dong_count"],
    }), 200


# ── 전역 에러 핸들러 ────────────────────────────────────────────────────────────


@app.errorhandler(404)
def not_found(e):
    return _error(f"엔드포인트를 찾을 수 없습니다. {e}", 404)


@app.errorhandler(405)
def method_not_allowed(e):
    return _error(f"허용되지 않는 HTTP 메서드입니다. {e}", 405)


@app.errorhandler(500)
def internal_error(e):
    logger.exception("내부 서버 오류: %s", e)
    return _error("내부 서버 오류가 발생했습니다.", 500)


# ── 서버 시작 ───────────────────────────────────────────────────────────────────

def _log_endpoints():
    """등록된 엔드포인트 목록을 로그로 출력"""
    rules = sorted(
        (rule for rule in app.url_map.iter_rules() if rule.endpoint != "static"),
        key=lambda r: r.rule,
    )
    logger.info("─── 사용 가능한 API 목록 ───")
    for rule in rules:
        methods = ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
        logger.info("  %-6s %s", methods, rule.rule)
    logger.info("────────────────────────────")


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    logger.info("크롤러 서버 시작: http://%s:%s (debug=%s)", host, port, debug)
    _log_endpoints()
    app.run(host=host, port=port, debug=debug)
