# 당근마켓 (Daangn) 스크래핑 문서

## 개요

| 항목 | 내용 |
|---|---|
| 사이트명 | 당근마켓 (당근) |
| 사이트 URL | https://www.daangn.com |
| 스크래핑 방식 | **SSR(서버사이드 렌더링) HTML 파싱** — REST API 직접 호출 |
| 데이터 추출 방법 | HTML 내 `window.__remixContext` JSON 파싱 (primary) / BeautifulSoup HTML 파싱 (fallback) |
| 프레임워크 | Next.js + Remix |
| 관련 모듈 | `scrapers/daangn_scraper.py` |
| 지역 선택 방식 | **당근 Location API**로 클라이언트(Flutter)가 직접 검색 → `location_id`를 크롤러에 전달 |

---

## 목차

- [검색 스크래핑](#검색-스크래핑)
- [당근 Location API](#당근-location-api)
- [HTTP 헤더](#http-헤더)
- [데이터 파싱 구조](#데이터-파싱-구조)
- [카테고리 목록](#카테고리-목록)
- [응답 아이템 구조](#응답-아이템-구조)
- [캐시 정책](#캐시-정책)

---

## 검색 스크래핑

당근마켓 웹 검색 페이지(`/kr/buy-sell/s/`)의 HTML을 요청하여 내장된 JSON 데이터를 파싱합니다.

### 요청 정보

| 항목 | 내용 |
|---|---|
| HTTP 메서드 | `GET` |
| 요청 URL | `https://www.daangn.com/kr/buy-sell/s/` |

### Query String 파라미터

| 파라미터 | 예시 값 | 설명 | 조건 |
|---|---|---|---|
| `search` | `아이폰` | 검색어 | 항상 포함 |
| `in` | `1540` | 당근 내부 location id (name3Id 또는 name2Id) | 지역 지정 시 포함 |
| `category_id` | `1` | 카테고리 코드 | 카테고리 지정 시 포함 |
| `price` | `100000__500000` | 가격 범위 (`{min}__{max}`) | 가격 필터 지정 시 포함 |
| `only_on_sale` | `true` | 판매중인 항목만 조회 | `exclude_sold=true` 시 포함 |
| `page` | `2` | 페이지 번호 | 2페이지 이상일 때만 포함 |

> **`in` 파라미터**: 과거에는 `강남구-10` 형식의 문자열 코드를 사용했으나,
> 현재는 당근 Location API 응답의 **정수 id** (`name3Id` 또는 `name2Id`)를 직접 사용합니다.

**요청 URL 예시 (동 레벨):**

```
GET https://www.daangn.com/kr/buy-sell/s/?search=%EC%95%84%EC%9D%B4%ED%8F%B0&in=1540&only_on_sale=true
```

---

## 당근 Location API

당근마켓 공식 내부 API로, 지역명 키워드로 행정구역을 검색합니다.
**클라이언트(Flutter 앱)가 직접 호출**하여 사용자에게 지역을 선택하게 한 뒤,
선택된 `id` 값을 크롤러 서버로 전달합니다.

### 요청 정보

| 항목 | 내용 |
|---|---|
| HTTP 메서드 | `GET` |
| 기본 URL | `https://www.daangn.com/v1/api/search/kr/location` |
| 인증 | 불필요 (공개 API) |
| Content-Type | `application/json` |

### Query String 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `keyword` | string | ✅ | 검색할 지역명 (한글). 시/도, 구/군, 동/읍/면 모두 지원 |

### 요청 헤더

```http
Accept: application/json, text/plain, */*
Referer: https://www.daangn.com/
```

### 요청 예시

```
GET https://www.daangn.com/v1/api/search/kr/location?keyword=능곡
```

### 응답 구조

```json
{
  "locations": [
    {
      "id": 1630,
      "name1": "경기도",
      "name2": "시흥시",
      "name3": "능곡동",
      "name": "능곡동",
      "name1Id": 1256,
      "name2Id": 1613,
      "name3Id": 1630,
      "depth": 3
    },
    {
      "id": 1540,
      "name1": "경기도",
      "name2": "고양시 덕양구",
      "name3": "능곡동",
      "name": "능곡동",
      "name1Id": 1256,
      "name2Id": 1529,
      "name3Id": 1540,
      "depth": 3
    }
  ]
}
```

### 응답 필드 상세

| 필드 | 타입 | 설명 |
|---|---|---|
| `locations` | array | 검색 결과 지역 목록 (0개 이상) |
| `locations[].id` | int | 해당 depth 기준 고유 id. **depth=3이면 name3Id와 동일** |
| `locations[].name` | string | 해당 depth 지역의 표시명 |
| `locations[].name1` | string | 시/도명 (예: `경기도`, `서울특별시`) |
| `locations[].name2` | string | 구/군명 (예: `고양시 덕양구`, `강남구`) |
| `locations[].name3` | string | 동/읍/면명 (예: `능곡동`, `역삼동`). depth=3일 때만 존재 |
| `locations[].name1Id` | int | 시/도 고유 id |
| `locations[].name2Id` | int | 구/군 고유 id |
| `locations[].name3Id` | int | 동/읍/면 고유 id. depth=3일 때만 유효 |
| `locations[].depth` | int | 행정구역 단계 (2 또는 3) |

### depth 레벨 정의

| depth 값 | 행정구역 단위 | 예시 | 검색 `in` 파라미터 |
|---|---|---|---|
| 2 | 구/군 | 강남구, 고양시 덕양구 | `name2Id` 사용 |
| 3 | 동/읍/면 | 역삼동, 능곡동 | `name3Id` 사용 (= `id`) |

> **주의**: depth=1(시/도)은 Location API 응답에 등장하지 않습니다.
> 당근 검색은 최소 구/군(depth=2) 이상의 지역을 요구합니다.

### 다양한 검색 예시

| 검색어 | 반환 depth | 결과 예시 |
|---|---|---|
| `능곡` | 3 | 경기도 시흥시 능곡동, 경기도 고양시 덕양구 능곡동 |
| `역삼동` | 3 | 서울특별시 강남구 역삼동 |
| `강남구` | 2, 3 혼합 | 강남구(depth=2) + 강남구 하위 동들(depth=3) |
| `서울` | 2, 3 혼합 | 서울 각 구/군(depth=2) 및 동(depth=3) |

### 지역 선택 UX 플로우 (Flutter 앱 기준)

```
1. 사용자가 지역 검색창에 키워드 입력 (예: "강남구")
2. Flutter → GET /v1/api/search/kr/location?keyword=강남구 직접 호출
3. 응답 locations 목록을 리스트로 표시
   예) "서울특별시 강남구" (depth=2, id=name2Id)
       "서울특별시 강남구 역삼동" (depth=3, id=name3Id)
4. 사용자가 원하는 지역 선택
5. 선택된 location의 id 저장

[단일 동 검색 시]
   → 크롤러 GET /api/daangn/search?keyword=아이폰&location_id={id}

[구/군 레벨 선택 시 — depth=2]
   → 해당 구/군 keyword로 재검색하여 depth=3 항목만 추출 → name3Id 목록 수집
   → 크롤러 GET /api/daangn/multi-search?keyword=아이폰&location_ids={id1,id2,...}
```

---

## HTTP 헤더

웹 페이지 스크래핑에 사용하는 공통 HTTP 헤더입니다.

```http
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
Accept-Language: ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7
Accept-Encoding: gzip, deflate, br
Referer: https://www.daangn.com/
```

- **Request timeout:** 3초

---

## 데이터 파싱 구조

### Primary 방법: `window.__remixContext` JSON 파싱

당근마켓은 Remix 프레임워크를 사용하며, 렌더링 데이터를 HTML 내 JavaScript 변수에 삽입합니다.

**정규식으로 추출:**

```python
re.search(r'window\.__remixContext\s*=\s*({.*?});', html_text, re.DOTALL)
```

**JSON 탐색 경로:**

```
window.__remixContext
  └── state
        └── loaderData
              └── "routes/kr.buy-sell.s"
                    └── allPage
                          └── fleamarketArticles  ← 상품 목록 배열
```

**상품 원본 JSON 필드:**

```json
{
  "id": "/kr/buy-sell/abc123def",
  "title": "상품 제목",
  "price": "50000",
  "thumbnail": "https://img...",
  "status": "Ongoing",
  "region": {
    "name": "능곡동"
  },
  "createdAt": "2024-01-15T10:30:00",
  "boostedAt": "2024-01-15T14:00:00"
}
```

**상품 상태 코드:**

| 원본 값 | 변환 값 |
|---|---|
| `Ongoing` | `판매중` |
| `Reserved` | `예약중` |
| `Completed` | `거래완료` |

### Fallback 방법: BeautifulSoup HTML 파싱

`__remixContext` 파싱 실패 시 HTML 직접 파싱으로 전환합니다.

**추출 요소:**

| 추출 항목 | HTML 선택자 / 정규식 |
|---|---|
| 상품 링크 | `<a href="/kr/buy-sell/[^?s]">` |
| 이미지 URL | `<img>` 태그의 `src` 속성 |
| 상품 제목 | 링크 내 텍스트 |

---

## 카테고리 목록

| 코드 | 카테고리명 |
|---|---|
| 1 | 디지털기기 |
| 172 | 생활가전 |
| 8 | 가구/인테리어 |
| 7 | 생활/주방 |
| 4 | 유아동 |
| 173 | 유아도서 |
| 5 | 여성의류 |
| 31 | 여성잡화 |
| 14 | 남성패션/잡화 |
| 6 | 뷰티/미용 |
| 3 | 스포츠/레저 |
| 2 | 취미/게임/음반 |
| 9 | 도서 |
| 304 | 티켓/교환권 |
| 517 | e쿠폰 |
| 305 | 가공식품 |
| 483 | 건강기능식품 |
| 16 | 반려동물용품 |
| 139 | 식물 |
| 13 | 기타 중고물품 |
| 32 | 삽니다 |

---

## 응답 아이템 구조

```json
{
  "id": "abc123def",
  "title": "맥북 프로 14인치 M3",
  "price": 2500000,
  "price_str": "2,500,000원",
  "image_url": "https://dnvefa72aowie.cloudfront.net/...",
  "status": "판매중",
  "location": "능곡동",
  "time": "2024-01-15T10:30:00",
  "url": "https://www.daangn.com/kr/buy-sell/abc123def",
  "source": "daangn"
}
```

> **참고:** 당근마켓은 판매자 닉네임(`seller`), 조회 수(`views`), 찜 수(`likes`) 정보가 목록 페이지에서 제공되지 않습니다.

---

## 캐시 정책

| 캐시 대상 | TTL | 방식 | 캐시 키 |
|---|---|---|---|
| 당근 Location API 응답 | 24시간 | **Redis** (`redis://localhost:6379/0`) | `daangn:location:{keyword}` |
| Flutter 앱 자체 캐시 | 앱 실행 중 | Flutter StateNotifier / Provider | - |

> 크롤러 서버에서 Location API 응답을 Redis에 24시간 캐싱합니다.
> 동일 구/군 재검색 시 Location API 호출 없이 캐시에서 바로 응답합니다.
> Redis 연결 실패 시에도 캐시 없이 정상 동작합니다 (graceful degradation).

---

## 기술적 특이사항

- **Remix 프레임워크:** `window.__remixContext`에 전체 페이지 로더 데이터가 직렬화되어 포함됨. JavaScript 실행 없이도 JSON 추출 가능
- **지역 id 기반 검색:** 문자열 코드(`강남구-10`) 방식은 더 이상 사용하지 않으며, 당근 Location API의 정수 `id`를 직접 사용
- **구/군 레벨 검색:** depth=2 지역(구/군) 선택 시 Flutter에서 해당 구/군 keyword로 Location API 재호출 → depth=3 항목의 `name3Id` 목록 수집 → 크롤러에 `location_ids`로 전달 → 병렬 검색
- **판매자 정보 미제공:** 당근마켓 목록 페이지는 판매자 닉네임을 노출하지 않음
- **시간 표현:** `createdAt` ISO 형식 기준
- **당근은 폴링 없음:** 스케줄러 대상 아님. 앱 탭에서 사용자가 직접 검색할 때만 호출

---

## 성능 최적화

### asyncio + aiohttp 비동기 병렬 검색

구/군 단위 검색(`multi-search`) 시 하위 동(최대 46개+)에 대한 병렬 검색을 **asyncio + aiohttp**로 처리합니다.

| 항목 | 내용 |
|---|---|
| HTTP 클라이언트 | `aiohttp.ClientSession` (asyncio 네이티브) |
| 커넥션 풀 | `aiohttp.TCPConnector(limit=100)` — 100개 동시 연결 |
| 병렬 방식 | `asyncio.gather()` — 스레드 없이 코루틴으로 처리 |
| 타임아웃 | `aiohttp.ClientTimeout(total=3)` |
| 캐싱 | Redis — Location API 응답 24시간 캐시 |

### 성능 개선 히스토리

| 단계 | 응답 시간 | 기술 |
|---|---|---|
| 최초 (ThreadPoolExecutor + requests) | ~15초 | 매 요청 새 TCP/TLS 연결 |
| requests.Session 재사용 | ~6초 | TCP/TLS 연결 재사용 |
| 커넥션 풀 확대 + Redis 캐시 | ~1.7초 | pool_maxsize=50, Location 캐시 |
| **asyncio + aiohttp** | **~0.7초** | 코루틴 기반 비동기 I/O, 100개 커넥션 풀 |

> 덕양구 기준 46개 동 병렬 검색: **15초 → 0.7초 (95% 단축)**
