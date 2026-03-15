# 당근 전국 매물 수집 스케줄러 설계

## 목적

전국 279개 구/군의 최신 매물을 주기적으로 수집하여 새 매물을 감지하고, 사용자가 등록한 키워드와 매칭되는 매물이 발견되면 알림을 발송한다.

---

## 두 가지 수집 방식

| | 구 레벨 (_data API) | 동 레벨 (HTML 파싱) |
|---|---|---|
| **파일** | `listing_scheduler.py` | `listing_scheduler_dong.py` |
| **방식** | Remix `_data` loader JSON | HTML `__remixContext` 파싱 |
| **요청 단위** | 구/군(279번) | 동(8,208번) |
| **수집 시간** | ~25초 | ~4분 30초 |
| **실행 주기** | 매분 정각 | 매 5분 정각 |
| **안정성** | 불안정 (일부 구 0건 반환 가능) | 안정적 |
| **Redis 키 접두사** | `daangn:listing:` | `daangn:listing_dong:` |
| **상태** | _data API 정상 시 사용 | _data API 불안정 시 대체 사용 |

---

## 1. 구 레벨 스케줄러 (listing_scheduler.py)

### 데이터 소스

**URL**: `https://www.daangn.com/kr/buy-sell/s/?in={regionId}&_data=routes/kr.buy-sell.s`

Remix `_data` loader를 사용하여 JSON 응답을 직접 수신한다. `only_on_sale` 파라미터는 사용하지 않는다 (사용 시 일부 구/군에서 매물이 반환되지 않음).

### 수집 흐름

```
매분 정각:
  [1단계] 구/군 목록 로드 — Redis daangn:districts:all (279개)
  [2단계] 전국 매물 병렬 수집 (20개씩 배치, rate limit 적응형)
  [3단계] 새 매물 감지 — Redis seen_ids 비교
  [4단계] 1분 이내 매물 필터 — createdAt 기준
  [5단계] 키워드 매칭 및 알림 (TODO)
```

### 성능

| 항목 | 수치 |
|---|---|
| 요청 수 | 279번 (구 1번씩) |
| 배치 크기 | 20개 (rate limit 시 자동 축소) |
| 수집 소요 시간 | ~25초 |
| 실행 주기 | 매분 정각 (CronTrigger) |

### 알려진 이슈

- _data API가 일부 구에서 0건 반환 가능 (서버 캐시/차단)
- createdAt 기준 1분 필터: 인기 지역에서도 최신 매물이 ~8분 이상 전이라 매칭 건수 적음

---

## 2. 동 레벨 스케줄러 (listing_scheduler_dong.py)

### 데이터 소스

**URL**: `https://www.daangn.com/kr/buy-sell/s/?in={dongId}`

기존 `_async_search_one`과 동일한 HTML 파싱 방식. `window.__remixContext`에서 `fleamarketArticles`를 추출한다.

### 수집 흐름

```
매 5분 정각:
  [1단계] 구/군 목록 로드 — Redis daangn:districts:all (279개)
  [2단계] 구별 순차 처리 (구 내 동은 병렬, 구 사이 0.3초 딜레이)
    └─ 구당 평균 29.4개 동 → 병렬 요청 (커넥션 풀 50)
    └─ 429 시 최대 3회 재시도 (딜레이 증가)
  [3단계] 새 매물 감지 — Redis seen_ids 비교
  [4단계] 키워드 매칭 및 알림 (TODO)
```

### 라운드 로빈

당근 서버의 rate limit(429)으로 전국 8,208개 동을 한 번에 수집하면 차단됨.
50개 구씩 라운드 로빈으로 나누어 수집하며, 6회(30분)에 걸쳐 전국 완료.

```
1회차: 구 0~49   (offset=0)
2회차: 구 50~99  (offset=50)
...
6회차: 구 250~278 (offset=250, 다음 0으로 리셋)
```

Redis 키 `daangn:listing_dong:round_offset`으로 현재 offset 관리.

### 성능

| 항목 | 수치 |
|---|---|
| 1회 요청 수 | ~1,500번 (50개 구 × 평균 30동) |
| 구 내 동시 요청 | 30개 |
| 구 사이 딜레이 | 0.2초 |
| 1회 수집 소요 시간 | **~1.6분** (50개 구) |
| 전국 완료 | ~30분 (6회차) |
| 1회 성공률 | ~94% (50개 중 47개) |
| 실행 주기 | 매 5분 정각 (CronTrigger) |

---

## 새 매물 감지 방식

### seen_ids 비교 (공통)

1. Redis에 저장된 이전 매물 ID와 비교하여 "이전에 없던 매물"을 감지
2. seen_ids 갱신 (TTL 24시간)
3. 새 매물을 키워드 매칭 대상으로 사용

### createdAt 필터 (구 레벨만)

- 구 레벨 스케줄러는 추가로 `createdAt` 기준 1분 이내 필터 적용
- 동 레벨 스케줄러는 seen_ids 기반 새 매물 전체를 매칭 대상으로 사용

---

## Redis 키 설계

### 구 레벨 스케줄러

```
daangn:listing:seen:{regionId}    — 구/군별 매물 ID (TTL 24h)
daangn:listing:last_run           — 최근 수집 상태
```

### 동 레벨 스케줄러

```
daangn:listing_dong:seen:{regionId}  — 구/군별 매물 ID (TTL 24h)
daangn:listing_dong:last_run         — 최근 수집 상태
```

---

## 키워드 매칭 로직

### 매칭 조건

```
새 매물의 (title + content)에 사용자 등록 키워드가 포함되어 있으면 매칭
- 대소문자 구분 없음 (case-insensitive)
- 부분 일치 (contains)
```

---

## API 엔드포인트

### 구 레벨

```
POST /api/daangn/listings/collect
  - 구 레벨 매물 수집 수동 실행 (test_keyword로 키워드 매칭 테스트 가능)

GET /api/daangn/listings/status
  - 구 레벨 최근 수집 상태 반환
```

### 동 레벨

```
POST /api/daangn/listings/collect-dong
  - 동 레벨 매물 수집 수동 실행 (test_keyword로 키워드 매칭 테스트 가능)
  - ~4분 30초 소요

GET /api/daangn/listings/status-dong
  - 동 레벨 최근 수집 상태 반환
```

---

## 직접 실행

```bash
# 구 레벨 스케줄러
cd crawler
python listing_scheduler.py
TEST_KEYWORD=닌텐도 python listing_scheduler.py

# 동 레벨 스케줄러
cd crawler
python listing_scheduler_dong.py
TEST_KEYWORD=닌텐도 python listing_scheduler_dong.py
```

---

## 알림 발송 (TODO)

### FCM 알림 형식

```json
{
  "title": "[당근] 닌텐도 스위치 OLED",
  "body": "280000원 · 행신동",
  "data": {
    "url": "https://www.daangn.com/kr/buy-sell/닌텐도-스위치-oled-xxx/",
    "platform": "daangn",
    "keyword": "닌텐도",
    "price": 280000
  }
}
```

### 중복 알림 방지

- 같은 매물에 대해 같은 사용자에게 1회만 알림
- Redis seen_ids로 매물 중복 필터 + DB 알림 이력으로 이중 체크

---

## 에러 처리

| 상황 | 처리 |
|---|---|
| Rate Limit (429) | 자동 재시도, 딜레이 증가 |
| 매물 0건 응답 (HTTP 200) | 정상 처리 (매물이 없는 지역) |
| Redis 연결 실패 | 수집 중단, 다음 주기 대기 |
| 이전 수집 미완료 | max_instances=1로 중복 실행 방지 |

---

## 파일 구조

| 파일 | 역할 |
|---|---|
| `crawler/listing_scheduler.py` | 구 레벨 _data API 매물 수집 스케줄러 (1분 주기) |
| `crawler/listing_scheduler_dong.py` | 동 레벨 HTML 파싱 매물 수집 스케줄러 (5분 주기) |
| `crawler/server.py` | 수동 실행 + 상태 조회 API 엔드포인트 |
