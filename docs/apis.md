# API 문서 (전체)

이 프로젝트는 Python + Flask 기반의 REST API 서버로, 국내 중고 거래 플랫폼(중고나라, 당근마켓, 번개장터)의 상품 정보를 스크래핑/크롤링하여 통합 API로 제공합니다.

- **Base URL:** `http://localhost:5000`
- **프레임워크:** Flask + flask-cors
- **스크래핑 대상 사이트별 상세 문서:**
  - [중고나라 (Joonggonara)](./joongna.md)
  - [당근마켓 (Daangn)](./daangn.md)
  - [번개장터 (Bunjang)](./bunjang.md)

---

## 목차

- [통합 검색](#통합-검색)
- [중고나라 API](#중고나라-api)
- [번개장터 API](#번개장터-api)
- [당근마켓 API](#당근마켓-api)
- [공통 응답 형식](#공통-응답-형식)

---

## 통합 검색

### `GET /api/search`

세 플랫폼(중고나라, 번개장터, 당근마켓)에서 동시에(병렬) 검색하여 결과를 통합해서 반환합니다. 결과는 등록 시간 기준 최신순으로 정렬됩니다.

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 필수 | 설명 |
|---|---|---|---|---|
| `keyword` | string | - | ✅ | 검색어 |
| `page` | int | 1 | | 페이지 번호 |
| `count` | int | 20 | | 페이지당 결과 수 (최대 100) |
| `sort` | string | `recommend` | | 정렬 방식: `recommend` \| `recent` \| `price_asc` \| `price_desc` |
| `category` | int | - | | 카테고리 코드 |
| `min_price` | int | - | | 최소 가격 (원) |
| `max_price` | int | - | | 최대 가격 (원) |
| `exclude_sold` | bool | true | | 판매완료 항목 제외 여부 |
| `region` | string | - | | 지역 필터 (당근마켓 전용) |

**응답 예시**

```json
{
  "success": true,
  "data": [
    {
      "id": "12345",
      "title": "아이폰 15 Pro 256GB",
      "price": 1200000,
      "price_str": "1,200,000원",
      "image_url": "https://...",
      "status": "판매중",
      "location": "강남구",
      "time": "2024-01-15T10:30:00",
      "url": "https://...",
      "seller": "사용자닉네임",
      "likes": 15,
      "views": 120,
      "source": "joongna"
    }
  ],
  "keyword": "아이폰",
  "region": null,
  "total_count": 60,
  "joongna_count": 20,
  "bunjang_count": 20,
  "daangn_count": 20,
  "elapsed_seconds": 2.3
}
```

---

## 중고나라 API

| 엔드포인트 | 메서드 | 설명 |
|---|---|---|
| `/api/joongna/search` | GET | 키워드 검색 |
| `/api/joongna/recent` | GET | 카테고리별 최신 목록 |
| `/api/joongna/product/<id>` | GET | 상품 상세 정보 |
| `/api/joongna/categories` | GET | 카테고리 목록 |

### `GET /api/joongna/search`

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 필수 | 설명 |
|---|---|---|---|---|
| `keyword` | string | - | ✅ | 검색어 |
| `page` | int | 1 | | 페이지 번호 |
| `count` | int | 20 | | 페이지당 결과 수 (최대 50) |
| `sort` | string | `recommend` | | `recommend` \| `recent` \| `price_asc` \| `price_desc` |
| `category` | int | - | | 카테고리 코드 |
| `min_price` | int | - | | 최소 가격 (원) |
| `max_price` | int | - | | 최대 가격 (원) |
| `exclude_sold` | bool | true | | 판매완료 제외 여부 |

### `GET /api/joongna/recent`

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `count` | int | 50 | 카테고리당 결과 수 (최대 50) |
| `categories` | string | - | 쉼표 구분 카테고리 코드 (예: `6,7,8`) |
| `min_price` | int | - | 최소 가격 |
| `max_price` | int | - | 최대 가격 |
| `exclude_sold` | bool | true | 판매완료 제외 여부 |
| `within_minutes` | int | - | N분 이내 등록된 상품만 반환 |
| `workers` | int | 5 | 병렬 처리 스레드 수 (최대 10) |

### `GET /api/joongna/product/<id>`

경로 파라미터 `id`에 상품 고유번호를 입력합니다.

### `GET /api/joongna/categories`

**응답 예시**

```json
{
  "success": true,
  "data": [
    {"code": 6, "name": "모바일/태블릿"},
    {"code": 7, "name": "가전제품"},
    {"code": 8, "name": "노트북/PC"}
  ]
}
```

---

## 번개장터 API

| 엔드포인트 | 메서드 | 설명 |
|---|---|---|
| `/api/bunjang/search` | GET | 키워드 검색 |
| `/api/bunjang/recent` | GET | 서브카테고리별 최신 목록 |
| `/api/bunjang/recent-by-category` | GET | 상위 카테고리별 최신 목록 |
| `/api/bunjang/categories` | GET | 전체 카테고리 트리 |
| `/api/bunjang/categories/top` | GET | 상위 카테고리 목록 |

### `GET /api/bunjang/search`

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 필수 | 설명 |
|---|---|---|---|---|
| `keyword` | string | - | ✅ | 검색어 |
| `page` | int | 1 | | 페이지 번호 |
| `count` | int | 20 | | 페이지당 결과 수 (최대 100) |
| `sort` | string | `recommend` | | `recommend` \| `recent` \| `price_asc` \| `price_desc` |
| `category` | int | - | | 카테고리 코드 |
| `min_price` | int | - | | 최소 가격 (원) |
| `max_price` | int | - | | 최대 가격 (원) |
| `exclude_sold` | bool | true | | 판매완료 제외 여부 |

### `GET /api/bunjang/recent`

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `count` | int | 100 | 서브카테고리당 결과 수 (최대 100) |
| `categories` | string | - | 쉼표 구분 서브카테고리 코드 |
| `min_price` | int | - | 최소 가격 |
| `max_price` | int | - | 최대 가격 |
| `exclude_sold` | bool | true | 판매완료 제외 여부 |
| `within_minutes` | int | - | N분 이내 등록된 상품만 반환 |
| `workers` | int | 5 | 병렬 처리 스레드 수 (최대 10) |

### `GET /api/bunjang/recent-by-category`

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `count` | int | 20 | 서브카테고리당 결과 수 (최대 100) |
| `top_categories` | string | - | 쉼표 구분 상위 카테고리 ID (예: `310,600`) |
| `min_price` | int | - | 최소 가격 |
| `max_price` | int | - | 최대 가격 |
| `exclude_sold` | bool | true | 판매완료 제외 여부 |
| `within_minutes` | int | - | N분 이내 등록된 상품만 반환 |
| `workers` | int | 5 | 병렬 처리 스레드 수 (최대 10) |
| `refresh` | bool | false | 카테고리 캐시 갱신 여부 |

**응답 예시**

```json
{
  "success": true,
  "top_categories": [
    {
      "id": "310",
      "title": "여성의류",
      "count": 2484247,
      "icon_url": "https://...",
      "listings": [...],
      "listings_count": 42
    }
  ],
  "total_listings": 820,
  "elapsed_seconds": 4.1,
  "source": "bunjang"
}
```

### `GET /api/bunjang/categories`

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `source` | string | `api` | `api` (번개장터 API 실시간 조회) \| `static` (코드 내 정적 맵 사용) |
| `refresh` | bool | false | 캐시 무시하고 새로 조회 (`source=api` 시에만 유효) |

---

## 당근마켓 API

| 엔드포인트 | 메서드 | 설명 |
|---|---|---|
| `/api/daangn/search` | GET | 키워드 검색 |
| `/api/daangn/categories` | GET | 카테고리 목록 |
| `/api/daangn/regions/search` | GET | 지역 검색 |
| `/api/daangn/regions/cities` | GET | 시/도 목록 |
| `/api/daangn/regions/districts` | GET | 시/도 내 구/군 목록 |
| `/api/daangn/regions/locations` | GET | 당근 지역 API 프록시 |

### `GET /api/daangn/search`

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 필수 | 설명 |
|---|---|---|---|---|
| `keyword` | string | - | ✅ | 검색어 |
| `region` | string | - | | 지역 이름 또는 코드 (예: `강남구`, `역삼동-360`) |
| `page` | int | 1 | | 페이지 번호 |
| `category` | int | - | | 카테고리 코드 |
| `min_price` | int | - | | 최소 가격 (원) |
| `max_price` | int | - | | 최대 가격 (원) |
| `exclude_sold` | bool | true | | 판매중인 항목만 반환 여부 |

### `GET /api/daangn/regions/search`

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `q` | string | - | 검색어 (지역명) |
| `limit` | int | 20 | 최대 반환 결과 수 |

**응답 예시**

```json
{
  "success": true,
  "data": [
    {
      "name": "역삼동",
      "code": "역삼동-360",
      "city": "서울특별시",
      "district": "강남구",
      "full": "서울특별시 강남구 역삼동"
    }
  ],
  "query": "역삼",
  "count": 1
}
```

### `GET /api/daangn/regions/cities`

시/도 목록을 반환합니다.

**응답 예시**

```json
{
  "success": true,
  "data": ["서울특별시", "부산광역시", "경기도"],
  "count": 17
}
```

### `GET /api/daangn/regions/districts`

**Query Parameters**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `city` | string | ✅ | 시/도 이름 (예: `서울특별시`) |

### `GET /api/daangn/regions/locations`

**Query Parameters**

| 파라미터 | 타입 | 설명 |
|---|---|---|
| `keyword` | string | 지역 검색어 (시/도, 구/군, 동/읍/면 모두 지원) |

---

## 공통 응답 형식

### 상품 아이템 객체

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | string | 상품 고유 ID |
| `title` | string | 상품 제목 |
| `price` | int | 가격 (원, 정수) |
| `price_str` | string | 가격 문자열 (예: `50,000원`) |
| `image_url` | string | 대표 이미지 URL |
| `status` | string | `판매중` \| `예약중` \| `판매완료` |
| `location` | string | 거래 지역 |
| `time` | string | 등록 시각 (ISO 8601 또는 플랫폼 형식) |
| `url` | string | 상품 상세 페이지 URL |
| `seller` | string | 판매자 닉네임 |
| `likes` | int | 찜/관심 수 |
| `views` | int | 조회 수 |
| `source` | string | `joongna` \| `bunjang` \| `daangn` |

### 오류 응답

```json
{
  "success": false,
  "error": "오류 메시지"
}
```

---

## 사용 예시

```bash
# 통합 검색
curl "http://localhost:5000/api/search?keyword=아이폰&count=30&sort=recent"

# 중고나라 - 최근 등록 (전자기기 카테고리)
curl "http://localhost:5000/api/joongna/recent?categories=6,8&count=30&within_minutes=30"

# 번개장터 - 카테고리별 최신 목록
curl "http://localhost:5000/api/bunjang/recent-by-category?top_categories=310,600&count=20"

# 당근마켓 - 지역 + 키워드 검색
curl "http://localhost:5000/api/daangn/search?keyword=맥북&region=강남구&exclude_sold=true"

# 당근마켓 - 지역 코드 조회
curl "http://localhost:5000/api/daangn/regions/search?q=판교&limit=5"
```
