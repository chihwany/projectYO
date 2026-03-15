# 당근 전국 매물 수집 스케줄러 설계

## 목적

전국 279개 구/군의 최신 매물을 1분 주기로 수집하여 새 매물을 감지하고, 1분 이내 등록된 새 매물 중 사용자가 등록한 키워드와 매칭되는 매물이 발견되면 알림을 발송한다.

---

## 데이터 소스

### 당근 매물 페이지

**URL**: `https://www.daangn.com/kr/buy-sell/s/?in={regionId}&_data=routes/kr.buy-sell.s`

Remix `_data` loader를 사용하여 JSON 응답을 직접 수신한다. `only_on_sale` 파라미터는 사용하지 않는다 (사용 시 일부 구/군에서 매물이 반환되지 않음).

### 응답 구조

```
Remix _data loader JSON 응답:
  allPage > fleamarketArticles (최대 300개)
```

### 매물 데이터 구조

```json
{
  "id": "/kr/buy-sell/남아-한복-세트-3호-4kx3ya293i1z/",
  "href": "https://www.daangn.com/kr/buy-sell/남아-한복-세트-3호-4kx3ya293i1z/",
  "title": "남아 한복 세트 3호",
  "price": 10000.0,
  "thumbnail": "https://...",
  "status": "ON_SALE",
  "content": "상품 설명...",
  "createdAt": "2026-03-14T14:25:55.241+09:00",
  "boostedAt": null,
  "user": {
    "region": {
      "name": "진영읍"
    }
  }
}
```

---

## 새 매물 감지 방식

### seen_ids + createdAt 1분 필터

1. **seen_ids 비교**: Redis에 저장된 이전 매물 ID와 비교하여 "이전에 없던 매물"을 감지
2. **createdAt 1분 필터**: seen_ids로 감지된 새 매물 중 `createdAt` 기준 1분 이내 등록된 매물만 알림 대상으로 필터

참고: 당근 API는 구/군별 최신 매물 ~300건을 반환하며, 이 목록은 캐시 기반 로테이션 방식으로 갱신된다. 인기 지역(강남구)에서도 가장 최근 매물의 `createdAt`이 ~8분 이상 전인 경우가 많아, 1분 필터를 통과하는 매물은 드물다.

---

## 스케줄러 설계

### 실행 주기

- **매분 정각(00초)** 실행
- APScheduler `CronTrigger(second=0)` 사용
- 전체 수집 소요 시간: ~25초 (1분 주기 내 충분)

### 수집 흐름

```
매분 정각:
  [1단계] 구/군 목록 로드
    └─ Redis에서 daangn:districts:all 조회 (279개 구/군)

  [2단계] 전국 매물 병렬 수집 (20개씩 배치, rate limit 적응형)
    └─ 각 구/군 regionId로 Remix _data loader JSON 요청
    └─ allPage > fleamarketArticles 추출
    └─ 20개씩 배치 분할, 배치 간 0.5초 delay (rate limit 시 자동 증가)
    └─ 429 응답 시 최대 5회 재시도 (delay 증가 + 배치 축소)
    └─ ~25초 소요, 279/279 100% 성공

  [3단계] 새 매물 감지 (seen_ids 기반)
    └─ Redis seen_ids(daangn:listing:seen:{regionId})와 비교
    └─ 이전에 없던 매물 ID → 새 매물로 판정
    └─ seen_ids 갱신 (TTL 24시간)

  [4단계] 1분 이내 매물 필터
    └─ createdAt 기준 최근 1분 이내 등록된 새 매물만 필터

  [5단계] 키워드 매칭 및 알림 (TODO)
    └─ DB에서 사용자 등록 키워드 목록 조회
    └─ 1분 이내 새 매물의 title + content에 키워드 포함 여부 확인
    └─ 매칭된 사용자에게 FCM 알림 발송
    └─ 알림 이력 DB 저장
```

### 직접 실행

```bash
cd crawler
python listing_scheduler.py
# 또는 키워드 지정
TEST_KEYWORD=닌텐도 python listing_scheduler.py
```

- 최초 1회 즉시 수집 (seen_ids 초기화)
- 이후 매분 정각 자동 반복 실행
- Ctrl+C로 종료

---

## Redis 키 설계

### 구/군별 매물 seen_ids

```
Key:    daangn:listing:seen:{regionId}
Type:   String (JSON array)
TTL:    86400초 (24시간)
예:     daangn:listing:seen:3600
Value:  ["/kr/buy-sell/남아-한복-세트-3호-4kx3ya293i1z/", ...]
설명:   이미 확인한 매물 ID 목록. 이 목록에 없는 매물이 새 매물.
```

### 최근 수집 상태

```
Key:    daangn:listing:last_run
Type:   String (JSON)
TTL:    없음 (매 실행마다 덮어씀)
Value:  {
          "timestamp": "2026-03-14T15:45:00",
          "districts_checked": 279,
          "districts_success": 279,
          "total_articles": 79040,
          "new_listings": 2,
          "recent_listings": 0,
          "duration_seconds": 25.0
        }
설명:   최근 수집 결과 요약. 모니터링 및 디버깅용.
```

---

## 키워드 매칭 로직

### 매칭 조건

```
seen_ids 기반 새 매물 중 createdAt 1분 이내 매물의 (title + content)에
사용자 등록 키워드가 포함되어 있으면 매칭
- 대소문자 구분 없음 (case-insensitive)
- 부분 일치 (contains)
```

### 매칭 대상

```
DB에서 조회:
  - 해당 구/군(regionId)을 지역으로 등록한 사용자
  - 해당 사용자의 활성 키워드 목록
  - 플랫폼 = 'daangn' 또는 'all'인 키워드
```

### 실측 결과 (닌텐도, 매분 정각 3회)

```
1차 (15:45:00): 새 매물 2건, 1분 이내 0건, 닌텐도 매칭 0건
2차 (15:46:00): 새 매물 1건, 1분 이내 0건, 닌텐도 매칭 0건
3차 (15:47:00): 새 매물 0건, 1분 이내 0건, 닌텐도 매칭 0건
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
    "price": 280000,
    "region": "행신동"
  }
}
```

### 중복 알림 방지

- 같은 매물에 대해 같은 사용자에게 1회만 알림
- Redis seen_ids로 매물 중복 필터 + DB 알림 이력으로 이중 체크

---

## 성능 (실측)

| 항목 | 수치 |
|---|---|
| 구/군 수 | 279개 |
| 배치 크기 | 20개 (rate limit 시 자동 축소) |
| 배치 간 delay | 0.5초 (rate limit 시 자동 증가, 최대 3초) |
| 최대 재시도 | 5회 |
| 수집 성공률 | **100% (279/279)** |
| 전체 매물 수 | ~79,000건 |
| 수집 소요 시간 | **~25초** |
| 실행 주기 | 매분 정각 (CronTrigger) |
| 여유 시간 | ~35초 |
| Redis seen_ids 메모리 | ~10MB (279개 키 × 300개 ID) |

---

## 에러 처리

| 상황 | 처리 |
|---|---|
| 특정 구/군 요청 실패 | 최대 5회 재시도, 배치 크기 축소 |
| Rate Limit (429) | delay 자동 증가 (0.5초 → 최대 3초), 재시도 시 배치 축소 |
| 매물 0건 응답 (HTTP 200) | 정상 처리 (매물이 없는 지역) |
| Redis 연결 실패 | 수집 중단, 다음 주기 대기 |
| 이전 수집 미완료 | max_instances=1로 중복 실행 방지 |
| FCM 발송 실패 | 재시도 큐에 추가, 다음 주기에 재발송 |

---

## 기존 코드 수정 사항

### 1. `crawler/server.py` - 스케줄러 통합

```python
# 매물 수집 스케줄러 시작
from listing_scheduler import create_listing_scheduler

listing_scheduler = create_listing_scheduler()
listing_scheduler.start()
```

### 2. `crawler/server.py` - 모니터링 엔드포인트 추가

```
POST /api/daangn/listings/collect
  - 매물 수집 수동 실행 (test_keyword 파라미터로 키워드 매칭 테스트 가능)

GET /api/daangn/listings/status
  - 최근 수집 상태 반환 (daangn:listing:last_run)
  - 수집 시각, 새 매물 수, 소요 시간 등
```

---

## 생성 파일

| 파일 | 역할 |
|---|---|
| `crawler/listing_scheduler.py` | 당근 전국 매물 수집 + 키워드 매칭 + 알림 스케줄러 |

## 수정 파일

| 파일 | 변경 내용 |
|---|---|
| `crawler/server.py` | 매물 스케줄러 시작 + 모니터링 엔드포인트 추가 |
