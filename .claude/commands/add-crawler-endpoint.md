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

## 당근 구/군 → 하위 동 병렬 검색 패턴 (district-search)

```python
@app.route("/api/daangn/district-search")
def daangn_district_search():
    """구/군 레벨 선택 시 하위 동 전체에서 병렬 검색"""
    keyword = request.args.get("keyword", "").strip()
    district = request.args.get("district", "").strip()  # 예: "강남구-10"

    if not keyword:
        return _error("keyword 파라미터가 필요합니다.")
    if not district:
        return _error("district 파라미터가 필요합니다.")

    # daangn_regions.py에서 하위 동(depth=3) 목록 조회
    from data.daangn_regions import get_sub_regions
    sub_regions = get_sub_regions(district)  # ["역삼동-360", "논현동-123", ...]

    if not sub_regions:
        return _error(f"'{district}' 지역의 하위 동을 찾을 수 없습니다.", 404)

    # 각 동마다 병렬 검색
    all_items = []
    seen_ids = set()
    start_time = time.time()

    def search_region(region_code):
        try:
            return daangn.search(keyword=keyword, region=region_code)
        except Exception as e:
            print(f"[당근 {region_code} 오류] {e}")
            return []

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(search_region, r): r for r in sub_regions}
        for future in as_completed(futures):
            for item in future.result():
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    all_items.append(item)

    # 최신순 정렬
    all_items.sort(key=lambda x: x.get("time", ""), reverse=True)

    return _success(
        all_items,
        keyword=keyword,
        district=district,
        regions_searched=len(sub_regions),
        count=len(all_items),
        elapsed_seconds=round(time.time() - start_time, 2),
        source="daangn",
    )
```

## 완료 후 처리

`index()` 엔드포인트의 endpoints 딕셔너리에도 새 경로 추가:
```python
"GET /api/{name}": "설명",
```

## 참고할 기존 엔드포인트

- `@app.route("/api/bunjang/recent")` — `within_minutes` 파라미터 + 병렬 수집 패턴
- `@app.route("/api/daangn/search")` — 지역 파라미터 처리 패턴
- `@app.route("/api/search")` — 다중 플랫폼 병렬 호출 패턴
