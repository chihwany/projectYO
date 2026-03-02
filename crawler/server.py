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
from flask import Flask, jsonify

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
        # ── Phase 1-3: 번개장터 (Step 1-3에서 추가) ──
        # "GET /api/bunjang/search":  "번개장터 키워드 검색 (page, count, min_price, max_price, sort)",
        # ── Phase 1-4: 중고나라 (Step 1-4에서 추가) ──
        # "GET /api/joongna/search":  "중고나라 키워드 검색 (page, count, min_price, max_price, sort)",
        # ── Phase 1-5: 당근 (Step 1-5에서 추가) ──
        # "GET /api/daangn/search":          "당근 동 레벨 단건 검색 (keyword, region_code, page, count)",
        # "GET /api/daangn/district-search": "당근 구/군 레벨 병렬 검색 (keyword, district, count)",
        # "GET /api/daangn/districts":       "시/도별 구/군 목록 반환 (city)",
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

if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    logger.info("크롤러 서버 시작: http://%s:%s (debug=%s)", host, port, debug)
    app.run(host=host, port=port, debug=debug)
