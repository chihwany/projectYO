# Flask 크롤러 서버 엔드포인트 추가

`$ARGUMENTS` 기능의 엔드포인트를 `crawler/server.py`에 추가하라.

## ⚠️ 응답 형식 (반드시 기존 유틸 함수 사용)

```python
# 성공 응답
return _success(data)
return _success(data, count=len(data), source="bunjang")
return _success(data, keyword=keyword, elapsed_seconds=elapsed)

# 실패 응답
return _error("에러 메시지", 400)   # 400: 잘못된 요청
return _error("찾을 수 없음", 404)  # 404: 리소스 없음
return _error("서버 오류", 500)     # 500: 서버 에러
```

## 공통 파라미터 파싱

```python
@app.route("/api/{name}")
def {name}():
    params = _parse_common_params()
    # params: keyword, page, count, sort, category,
    #         min_price, max_price, exclude_sold, region
    if not params["keyword"]:
        return _error("keyword 파라미터가 필요합니다.")
    ...
```

## 시간 측정 패턴

```python
import time

start_time = time.time()
# ... 작업 실행 ...
elapsed = round(time.time() - start_time, 2)

return _success(results, elapsed_seconds=elapsed)
```

## 당근 구/군 → 하위 동 비동기 병렬 검색 패턴 (multi-search)

```python
@app.get("/api/daangn/multi-search")
def daangn_multi_search():
    """구/군 단위 비동기 병렬 매물 검색 (asyncio + aiohttp)"""
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
        return _error("당근 지역 조회 시간이 초과되었습니다.", 504)
    except _req.exceptions.RequestException as e:
        return _error("당근 지역 조회에 실패했습니다.", 502)

    return jsonify({
        "ok": True,
        "data": result["items"],
        "count": result["total"],
        "source": "daangn",
        "district": result["district"],
        "dong_count": result["dong_count"],
    }), 200
```

> **내부 동작:** `search_by_district()` → Location API (Redis 24시간 캐시)
> → `asyncio.gather()` + `aiohttp`로 하위 동 전체 비동기 병렬 검색
> → 중복 제거 + 최신순 정렬

## 완료 후 처리

`index()` 엔드포인트의 endpoints 딕셔너리에도 새 경로 추가:
```python
"GET /api/{name}": "설명",
```

## 참고할 기존 엔드포인트

- `@app.route("/api/bunjang/recent")` — `within_minutes` 파라미터 + 병렬 수집 패턴
- `@app.route("/api/daangn/search")` — 지역 파라미터 처리 패턴
- `@app.route("/api/search")` — 다중 플랫폼 병렬 호출 패턴
