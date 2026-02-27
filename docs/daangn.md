# 당근마켓 (Daangn) 스크래핑 문서

## 개요

| 항목 | 내용 |
|---|---|
| 사이트명 | 당근마켓 (당근) |
| 사이트 URL | https://www.daangn.com |
| 스크래핑 방식 | **SSR(서버사이드 렌더링) HTML 파싱** + **REST API 직접 호출** |
| 데이터 추출 방법 | HTML 내 `window.__remixContext` JSON 파싱 (primary) / BeautifulSoup HTML 파싱 (fallback) |
| 프레임워크 | Next.js + Remix |
| 관련 모듈 | `scrapers/daangn_scraper.py`, `data/daangn_regions.py` |

---

## 목차

- [검색 스크래핑](#검색-스크래핑)
- [지역 정보 수집](#지역-정보-수집)
- [당근 지역 검색 API](#당근-지역-검색-api)
- [HTTP 헤더](#http-헤더)
- [데이터 파싱 구조](#데이터-파싱-구조)
- [카테고리 목록](#카테고리-목록)
- [지역 코드 형식](#지역-코드-형식)
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
| `in` | `강남구-10` | 지역 코드 | 지역 지정 시 포함 |
| `category_id` | `1` | 카테고리 코드 | 카테고리 지정 시 포함 |
| `price` | `100000__500000` | 가격 범위 (`{min}__{max}`) | 가격 필터 지정 시 포함 |
| `only_on_sale` | `true` | 판매중인 항목만 조회 | `exclude_sold=true` 시 포함 |
| `page` | `2` | 페이지 번호 | 2페이지 이상일 때만 포함 |

**요청 URL 예시:**

```
GET https://www.daangn.com/kr/buy-sell/s/?search=%EC%95%84%EC%9D%B4%ED%8F%B0&in=%EA%B0%95%EB%82%A8%EA%B5%AC-10&only_on_sale=true
```

---

## 지역 정보 수집

### 지역 목록 페이지 스크래핑

지역 코드를 얻기 위해 당근마켓의 지역 목록 페이지를 스크래핑합니다.

| 항목 | 내용 |
|---|---|
| HTTP 메서드 | `GET` |
| 요청 URL | `https://www.daangn.com/kr/regions/` |

**HTML 파싱 방법:**

1. `<h2>` 태그 → 시/도명 (예: `서울특별시`)
2. `<a href="?in=...">` 태그 → 구/군/동 및 코드
3. 정규식으로 코드 추출: `[?&]in=([^&]+)` → `강남구-10`, `역삼동-360` 형식

**파싱 결과 예시:**

```python
{
    "name": "역삼동",
    "code": "역삼동-360",
    "city": "서울특별시",
    "district": "강남구",
    "full": "서울특별시 강남구 역삼동"
}
```

---

## 당근 지역 검색 API

당근마켓 내부 API를 직접 호출하여 지역 정보를 검색합니다.

### 요청 정보

| 항목 | 내용 |
|---|---|
| HTTP 메서드 | `GET` |
| 요청 URL | `https://www.daangn.com/v1/api/search/kr/location` |

### Query String 파라미터

| 파라미터 | 예시 값 | 설명 |
|---|---|---|
| `keyword` | `강남구` | 지역 검색어 (시/도, 구/군, 동/읍/면 모두 지원) |

**요청 URL 예시:**

```
GET https://www.daangn.com/v1/api/search/kr/location?keyword=강남구
```

**HTTP 헤더 (지역 API 전용):**

```http
Accept: application/json, text/plain, */*
Referer: https://www.daangn.com/
```

**응답 JSON 구조:**

```json
{
  "locations": [
    {
      "id": 1590,
      "name1": "경기도",
      "name2": "남양주시",
      "name3": "화도읍",
      "name": "화도읍",
      "name1Id": 1256,
      "name2Id": 1587,
      "name3Id": 1590,
      "depth": 3
    }
  ]
}
```

**depth 레벨:**

| depth 값 | 행정구역 단위 | 예시 |
|---|---|---|
| 1 | 시/도 | 서울특별시, 경기도 |
| 2 | 구/군 | 강남구, 수원시 |
| 3 | 동/읍/면 | 역삼동, 화도읍 |

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

- **Request timeout:** 15초

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
              └── "routes/kr.buy-sell.s.allPage"
                    └── fleamarketArticles  ← 상품 목록 배열
```

**상품 원본 JSON 필드:**

```json
{
  "id": "/kr/buy-sell/...",
  "title": "상품 제목",
  "price": "50000",
  "thumbnail": "https://img...",
  "status": "Ongoing",
  "region": {
    "name": "강남구"
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
| 상품 링크 | `<a href="/kr/buy-sell/[^?]">` |
| 이미지 URL | `<img>` 태그의 `src` 속성 |
| 상품 제목 | 링크 내 텍스트 |
| 가격 | 가격 텍스트 요소 |
| 위치 | 지역 텍스트 요소 |
| 등록 시간 | 정규식: `(\d+)(분\|시간\|일\|주\|개월) 전` |

---

## 지역 코드 형식

당근마켓에서 사용하는 지역 코드는 `{지역명}-{숫자}` 형식입니다.

| 예시 코드 | 설명 |
|---|---|
| `
` | 서울특별시 강남구 |
| `역삼동-360` | 서울특별시 강남구 역삼동 |
| `수원시-100` | 경기도 수원시 |

### 지역 입력 형식 (API 사용 시)

| 입력 형식 | 예시 | 처리 방법 |
|---|---|---|
| 지역명만 | `강남구` | 캐시에서 코드 자동 매핑 |
| 전체 지역명 | `서초4동` | 캐시에서 코드 자동 매핑 |
| 코드 직접 입력 | `역삼동-360` | 그대로 사용 |

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
  "location": "강남구",
  "time": "2024-01-15T10:30:00",
  "time_ago": "2시간 전",
  "url": "https://www.daangn.com/kr/buy-sell/abc123def",
  "source": "daangn"
}
```

> **참고:** 당근마켓은 판매자 닉네임(`seller`), 조회 수(`views`), 찜 수(`likes`) 정보가 목록 페이지에서 제공되지 않아 해당 필드가 없거나 기본값입니다.

---

## 캐시 정책

| 캐시 대상 | TTL | 방식 |
|---|---|---|
| 지역 목록 (`/kr/regions/` 파싱 결과) | 1시간 | 메모리 내 전역 변수 (`_regions_cache`, `_regions_cache_time`) |
| 지역 API 검색 결과 (`/v1/api/search/kr/location`) | 1시간 | 딕셔너리 (`_location_cache[keyword]`) |

---

## 기술적 특이사항

- **Remix 프레임워크:** `window.__remixContext`에 전체 페이지 로더 데이터가 직렬화되어 포함됨. JavaScript 실행 없이도 JSON 추출 가능
- **지역 코드 필수:** 당근마켓 검색은 기본적으로 지역 기반. 지역을 지정하지 않으면 전국 검색이 되며 결과가 제한될 수 있음
- **지역명 자동 변환:** `강남구` 같은 이름을 입력하면 내부적으로 `강남구-10` 코드로 자동 변환
- **판매자 정보 미제공:** 당근마켓 목록 페이지는 판매자 닉네임을 노출하지 않음
- **시간 표현:** `createdAt` ISO 형식 + `time_ago` 상대 시간 표현 (`2시간 전`) 함께 제공
