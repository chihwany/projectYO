# 당근 지역 데이터 스케줄러 설계

## 목적

당근 홈페이지(`https://www.daangn.com/kr/regions/`)에서 전국 모든 지역 정보를 하루 1회 크롤링하여 Redis에 저장한다. 이를 통해 사용자가 지역 검색 시 당근 Location API를 매번 호출하지 않고 Redis 캐시에서 즉시 응답할 수 있도록 한다.

---

## 현재 구조의 문제점

- `daangn_scraper.py`의 `search_location(keyword)` 함수는 사용자가 검색할 때마다 당근 Location API를 실시간 호출
- Location API 결과를 24시간 TTL로 Redis에 캐싱하지만, 검색어 기반이므로 검색하지 않은 지역은 캐시 없음
- 전국 지역 데이터를 미리 확보해두면 Location API 의존도를 줄이고 응답 속도를 개선할 수 있음

## 변경 방향

- **사용자가 지역을 검색할 때 당근 Location API를 호출하지 않는다**
- 스케줄러가 하루 1회 수집한 Redis 데이터만으로 지역 검색을 처리한다
- `search_location()` 함수는 Redis에서만 조회하고, Redis에 데이터가 없는 경우에만 fallback으로 Location API를 호출한다

---

## 데이터 소스

### 당근 지역 페이지 구조

**URL**: `https://www.daangn.com/kr/regions/`

페이지의 `window.__remixContext` JSON에 전국 지역 데이터가 포함되어 있다.

```
계층 구조:
  depth=1: 시/도 (17개) — 서울특별시, 경기도, 부산광역시 등
  depth=2: 구/군/시 — 강남구(381), 덕양구(1529), 해운대구 등
  depth=3: 동/읍/면 — 능곡동(1540), 행신동 등 (하위 페이지에서 수집)
```

### 지역 데이터 JSON 구조

```json
{
  "regionName": "경기도",
  "depth": 1,
  "childrenRegion": [
    {
      "regionId": 1529,
      "regionName": "고양시 덕양구",
      "depth": 2
    }
  ]
}
```

### 링크 패턴에서 regionId 추출

```
URL: ?in=%EA%B0%95%EB%82%A8%EA%B5%AC-381
패턴: ?in={URL인코딩된_지역명}-{regionId}
추출: URL 디코딩 후 마지막 '-' 뒤의 숫자 = regionId
```

---

## 스케줄러 설계

### 실행 주기

- **매일 1회**, 새벽 4시 (트래픽 최소 시간대)
- APScheduler `CronTrigger` 사용

### 수집 흐름

```
[1단계] 시/도 + 구/군 수집 (regions 페이지)
  └─ GET https://www.daangn.com/kr/regions/
  └─ window.__remixContext JSON 파싱
  └─ depth=1(시/도) + depth=2(구/군) 데이터 추출
  └─ Redis에 저장

[2단계] 동/읍/면 수집 (구/군별 Location API 병렬 호출)
  └─ 1단계에서 수집한 구/군 목록을 50개씩 배치 분할
  └─ 각 배치 내 50개 구/군을 aiohttp로 동시 요청
  └─ depth=3(동/읍/면) 결과를 Redis에 저장
  └─ 배치 간 0.3초 delay (Rate Limit 방지)
```

### 상세 로직 (의사 코드)

```python
# crawler/region_scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
import aiohttp
import requests
import json
import re

def collect_all_regions():
    """전국 지역 데이터 수집 → Redis 저장"""

    # ── 1단계: regions 페이지에서 시/도 + 구/군 수집 ──
    resp = requests.get(
        "https://www.daangn.com/kr/regions/",
        headers={"User-Agent": CHROME_UA},
        timeout=15
    )
    resp.encoding = "utf-8"

    # __remixContext JSON 추출
    match = re.search(r'window\.__remixContext\s*=\s*({.+?});', resp.text)
    remix_data = json.loads(match.group(1))

    # 시/도 → 구/군 계층 구조 파싱
    provinces = []  # depth=1
    districts = []  # depth=2

    for province in remix_data["state"]["loaderData"]["routes/kr.regions"]["regions"]:
        province_info = {
            "name": province["regionName"],
            "depth": 1,
            "districts": []
        }
        for district in province.get("childrenRegion", []):
            district_info = {
                "regionId": district["regionId"],
                "name": district["regionName"],
                "province": province["regionName"],
                "depth": 2
            }
            province_info["districts"].append(district_info)
            districts.append(district_info)
        provinces.append(province_info)

    # Redis에 시/도 + 구/군 전체 목록 저장
    redis.set(
        "daangn:regions:all",
        json.dumps(provinces, ensure_ascii=False),
        ex=86400 * 2  # TTL 48시간 (여유분)
    )
    redis.set(
        "daangn:districts:all",
        json.dumps(districts, ensure_ascii=False),
        ex=86400 * 2
    )

    # ── 2단계: 각 구/군의 동 레벨 정보 수집 (50개씩 병렬) ──
    BATCH_SIZE = 50

    async def _fetch_dongs_for_district(session, district):
        """단일 구/군의 동 목록을 비동기로 수집"""
        try:
            params = {"keyword": district["name"]}
            async with session.get(LOCATION_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                body = await resp.json()
            locations = body.get("locations", [])
            dong_list = [loc for loc in locations if loc.get("depth") == 3]

            # Redis에 구/군별 동 목록 저장
            cache_key = f"daangn:dongs:{district['regionId']}"
            redis.set(cache_key, json.dumps(dong_list, ensure_ascii=False), ex=86400 * 2)

            # 기존 location 캐시도 갱신
            location_cache_key = f"daangn:location:{district['name']}"
            redis.setex(location_cache_key, 86400, json.dumps(locations, ensure_ascii=False))

            return district["name"], len(dong_list)
        except Exception as e:
            logger.error("동 수집 실패 [%s]: %s", district["name"], e)
            return district["name"], -1

    async def _collect_dongs_in_batches(districts):
        """구/군 목록을 BATCH_SIZE(50)개씩 나누어 병렬 수집"""
        connector = aiohttp.TCPConnector(limit=BATCH_SIZE)
        async with aiohttp.ClientSession(connector=connector, headers=LOCATION_API_HEADERS) as session:
            for i in range(0, len(districts), BATCH_SIZE):
                batch = districts[i:i + BATCH_SIZE]
                tasks = [_fetch_dongs_for_district(session, d) for d in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                success = sum(1 for r in results if isinstance(r, tuple) and r[1] >= 0)
                logger.info("배치 %d/%d 완료 (%d/%d 성공)",
                            i // BATCH_SIZE + 1,
                            (len(districts) + BATCH_SIZE - 1) // BATCH_SIZE,
                            success, len(batch))

                await asyncio.sleep(0.3)  # 배치 간 Rate Limit 방지

    asyncio.run(_collect_dongs_in_batches(districts))

    logger.info("지역 데이터 수집 완료: %d개 시/도, %d개 구/군", len(provinces), len(districts))


# APScheduler 등록
scheduler = BackgroundScheduler()
scheduler.add_job(
    collect_all_regions,
    trigger=CronTrigger(hour=4, minute=0),  # 매일 새벽 4시
    id="daangn_region_collector",
    name="당근 전국 지역 데이터 수집",
    replace_existing=True,
    misfire_grace_time=3600,  # 1시간 이내 실행 보장
)
```

---

## Redis 키 설계

### 전국 시/도 + 구/군 전체 목록

```
Key:    daangn:regions:all
Type:   String (JSON)
TTL:    172800초 (48시간)
Value:  [
          {
            "name": "서울특별시",
            "depth": 1,
            "districts": [
              {"regionId": 381, "name": "강남구", "province": "서울특별시", "depth": 2},
              {"regionId": 432, "name": "강동구", "province": "서울특별시", "depth": 2},
              ...
            ]
          },
          ...
        ]
```

### 구/군 목록 (플랫 리스트)

```
Key:    daangn:districts:all
Type:   String (JSON)
TTL:    172800초 (48시간)
Value:  [
          {"regionId": 381, "name": "강남구", "province": "서울특별시", "depth": 2},
          {"regionId": 1529, "name": "고양시 덕양구", "province": "경기도", "depth": 2},
          ...
        ]
```

### 구/군별 동/읍/면 목록

```
Key:    daangn:dongs:{regionId}
Type:   String (JSON)
TTL:    172800초 (48시간)
예:     daangn:dongs:1529
Value:  [
          {
            "id": 1540, "name": "능곡동",
            "name1": "경기도", "name2": "고양시 덕양구", "name3": "능곡동",
            "name1Id": 1256, "name2Id": 1529, "name3Id": 1540,
            "depth": 3
          },
          ...
        ]
```

### 기존 Location 캐시 갱신

```
Key:    daangn:location:{district_name}
Type:   String (JSON)
TTL:    86400초 (24시간)
예:     daangn:location:덕양구
설명:   기존 search_location() 캐시와 동일 포맷으로 갱신하여
        사용자 검색 시 API 호출 없이 즉시 응답
```

---

## 기존 코드 수정 사항

### 1. `daangn_scraper.py` - search_location() Redis 전용 조회로 변경

사용자 요청 시 당근 Location API를 호출하지 않고 Redis 데이터만으로 응답한다.

```python
def search_location(keyword: str) -> dict:
    # 1순위: Redis에서 구/군 목록 검색 (daangn:districts:all)
    #   → keyword가 포함된 구/군 필터링하여 반환
    # 2순위: Redis에서 기존 location 캐시 확인 (daangn:location:{keyword})
    # 3순위 (fallback): Redis에 데이터가 전혀 없는 경우에만 Location API 호출
    #   → 스케줄러 최초 실행 전 또는 Redis 장애 복구 직후 등 예외 상황

    # Redis 조회 로직
    districts_json = redis.get("daangn:districts:all")
    if districts_json:
        all_districts = json.loads(districts_json)
        matched = [d for d in all_districts if keyword in d["name"]]
        if matched:
            return {"locations": matched}

    # fallback: Redis에 데이터 없을 때만 API 호출
    return _fetch_from_location_api(keyword)
```

### 2. `crawler/server.py` - 지역 목록 엔드포인트 추가

```
GET /api/daangn/regions
  - Redis에서 전국 시/도 + 구/군 계층 목록 반환
  - 캐시 없으면 collect_all_regions() 즉시 실행 후 반환

GET /api/daangn/regions/{regionId}/dongs
  - 특정 구/군의 동/읍/면 목록 반환
  - Redis에서 daangn:dongs:{regionId} 조회
```

### 3. `crawler/server.py` - 스케줄러 통합

```python
# server.py Flask 앱 시작 시 스케줄러 등록
from region_scheduler import scheduler

if __name__ == "__main__":
    scheduler.start()
    # 최초 실행: Redis에 지역 데이터가 없으면 즉시 수집
    if not redis.exists("daangn:regions:all"):
        collect_all_regions()
    app.run(host="0.0.0.0", port=5000)
```

---

## 에러 처리

| 상황 | 처리 |
|---|---|
| regions 페이지 요청 실패 | 재시도 1회 후 skip, 기존 Redis 캐시 유지 (TTL 48시간) |
| remixContext 파싱 실패 | BeautifulSoup로 링크에서 regionId 추출 (fallback) |
| 특정 구/군 동 수집 실패 | 해당 구/군 skip, 나머지 계속 수집 |
| Redis 연결 실패 | 수집 중단, 다음 스케줄 실행 대기 |
| Location API Rate Limit | 요청 간 0.3초 delay, 연속 실패 시 delay를 2초로 증가 |

---

## 예상 데이터 규모

| 항목 | 수량 | 비고 |
|---|---|---|
| 시/도 | 17개 | depth=1 |
| 구/군/시 | 279개 | depth=2 |
| 동/읍/면 | ~3,500개 | depth=3 |
| Redis 메모리 | ~2MB | JSON 직렬화 기준 |
| 2단계 수집 소요 시간 | ~11초 | 279개 구/군 ÷ 50개 배치 = 6배치 × 0.3초 delay |

---

## 생성 파일

| 파일 | 역할 |
|---|---|
| `crawler/region_scheduler.py` | 당근 지역 데이터 수집 스케줄러 |

## 수정 파일

| 파일 | 변경 내용 |
|---|---|
| `crawler/scrapers/daangn_scraper.py` | search_location()에 스케줄러 캐시 조회 로직 추가 |
| `crawler/server.py` | 지역 목록 엔드포인트 추가 + 스케줄러 시작 로직 통합 |
