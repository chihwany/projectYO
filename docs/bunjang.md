# 번개장터 (Bunjang) 스크래핑 문서

## 개요

| 항목 | 내용 |
|---|---|
| 사이트명 | 번개장터 |
| 사이트 URL | https://m.bunjang.co.kr |
| 스크래핑 방식 | **REST API 직접 호출** |
| Primary API | `https://api.bunjang.co.kr/api/1/find_v2.json` |
| 관련 모듈 | `scrapers/bunjang_scraper.py` |

> 번개장터는 세 플랫폼 중 유일하게 공개 JSON REST API(`api.bunjang.co.kr`)를 직접 호출합니다. HTML 파싱 없이 구조화된 JSON 데이터를 수신합니다.

---

## 목차

- [검색 API](#검색-api)
- [카테고리 API](#카테고리-api)
- [최신 목록 (상위 카테고리별)](#최신-목록-상위-카테고리별)
- [HTTP 헤더](#http-헤더)
- [카테고리 목록](#카테고리-목록)
- [정렬 파라미터 매핑](#정렬-파라미터-매핑)
- [상품 상태 코드](#상품-상태-코드)
- [응답 아이템 구조](#응답-아이템-구조)
- [캐시 정책](#캐시-정책)

---

## 검색 API

### 요청 정보

| 항목 | 내용 |
|---|---|
| HTTP 메서드 | `GET` |
| 요청 URL | `https://api.bunjang.co.kr/api/1/find_v2.json` |
| 응답 형식 | JSON |

### Query String 파라미터

| 파라미터 | 예시 값 | 설명 | 조건 |
|---|---|---|---|
| `q` | `아이폰` | 검색어 | 항상 포함 |
| `order` | `date` | 정렬 방식 | 항상 포함 |
| `page` | `0` | 페이지 번호 (0-based) | 항상 포함 |
| `n` | `20` | 결과 수 (최소 1, 최대 100) | 항상 포함 |
| `stat` | `v2` | API 버전 (고정값) | 항상 포함 |
| `category` | `600` | 카테고리 코드 | 카테고리 지정 시 포함 |
| `price_min` | `10000` | 최소 가격 | 0 초과 시 포함 |
| `price_max` | `500000` | 최대 가격 | 지정 시 포함 |
| `req_ref` | `search` | 요청 출처 | `exclude_sold=true` 시 포함 |
| `stat_status` | `s` | 판매중 필터 (`s` = on sale) | `exclude_sold=true` 시 포함 |

> **참고:** 번개장터 API의 `page`는 0부터 시작합니다. 외부 API에서 `page=1`로 요청하면 내부적으로 `page=0`으로 변환됩니다.

**요청 URL 예시:**

```
GET https://api.bunjang.co.kr/api/1/find_v2.json?q=%EC%95%84%EC%9D%B4%ED%8F%B0&order=date&page=0&n=20&stat=v2&stat_status=s&req_ref=search
```

### 응답 JSON 구조

```json
{
  "list": [
    {
      "pid": "123456789",
      "product_id": "123456789",
      "name": "아이폰 15 Pro",
      "title": "아이폰 15 Pro",
      "price": "1200000",
      "product_image": "https://media.bunjang.co.kr/...",
      "image": "https://media.bunjang.co.kr/...",
      "status": 0,
      "location": "강남구",
      "update_time": 1705294200,
      "seller_name": "판매자닉네임",
      "wish_cnt": 15,
      "view_cnt": 120,
      "safe_payment": true,
      "category_name": "스마트폰"
    }
  ],
  "num_found": 3842
}
```

---

## 카테고리 API

### 요청 정보

| 항목 | 내용 |
|---|---|
| HTTP 메서드 | `GET` |
| 요청 URL | `https://api.bunjang.co.kr/api/1/categories/list.json` |
| 응답 형식 | JSON |

**요청 URL 예시:**

```
GET https://api.bunjang.co.kr/api/1/categories/list.json
```

### 응답 JSON 구조

```json
{
  "result": "success",
  "categories": [
    {
      "id": 310,
      "title": "여성의류",
      "count": 2484247,
      "icon_url": "https://...",
      "categories": [
        {
          "id": 310100,
          "title": "여성 상의",
          "count": 500000,
          "categories": [
            {
              "id": 310101,
              "title": "니트/스웨터",
              "count": 12000
            }
          ]
        }
      ]
    }
  ]
}
```

3단계 계층 구조: **상위 카테고리** → **중간 카테고리** → **하위 카테고리**

---

## 최신 목록 (상위 카테고리별)

상위 카테고리 ID를 기준으로 최신 상품을 검색합니다.

### 요청 정보

| 항목 | 내용 |
|---|---|
| HTTP 메서드 | `GET` |
| 요청 URL | `https://api.bunjang.co.kr/api/1/find_v2.json` |

### Query String 파라미터

| 파라미터 | 예시 값 | 설명 |
|---|---|---|
| `f_category_id` | `600` | 상위 카테고리 ID |
| `page` | `0` | 첫 페이지 (0-based 고정) |
| `order` | `date` | 최신순 고정 |
| `req_ref` | `popular_category` | 요청 출처 (고정값) |
| `request_id` | `1705294200` | 요청 타임스탬프 |
| `stat_device` | `w` | 디바이스 타입 (web 고정) |
| `n` | `20` | 결과 수 |
| `version` | `4` | API 버전 (고정값) |
| `price_min` | `10000` | 최소 가격 (지정 시) |
| `price_max` | `500000` | 최대 가격 (지정 시) |
| `stat_status` | `s` | 판매중 필터 (`exclude_sold=true` 시) |

**요청 URL 예시:**

```
GET https://api.bunjang.co.kr/api/1/find_v2.json?f_category_id=600&page=0&order=date&req_ref=popular_category&request_id=1705294200&stat_device=w&n=20&version=4
```

---

## HTTP 헤더

모든 번개장터 API 요청에 공통으로 사용하는 HTTP 헤더입니다.

```http
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36
Accept: application/json, text/plain, */*
Accept-Language: ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7
Referer: https://m.bunjang.co.kr/
Origin: https://m.bunjang.co.kr
```

- **Request timeout:** 15초
- **Origin 헤더:** CORS 우회를 위해 모바일 사이트 도메인으로 설정

---

## 카테고리 목록

### 상위 카테고리 (CATEGORY_MAP)

| 코드 | 카테고리명 |
|---|---|
| 310 | 여성의류 |
| 320 | 남성의류 |
| 300 | 패션잡화 |
| 400 | 뷰티 |
| 500 | 출산/유아동 |
| 600 | 모바일/태블릿 |
| 601 | 스마트폰 |
| 602 | 태블릿 |
| 700 | 가전제품 |
| 800 | 노트북/PC |
| 900 | 카메라 |
| 110 | 가구/인테리어 |
| 120 | 리빙/생활 |
| 130 | 게임 |
| 140 | 반려동물/취미 |
| 150 | 도서/음반/문구 |
| 160 | 티켓/쿠폰 |
| 170 | 스포츠/레저 |
| 180 | 자동차/오토바이 |

### 주요 서브카테고리 (SUBCATEGORY_MAP, 일부)

| 코드 | 카테고리명 |
|---|---|
| 310100 | 여성 상의 |
| 310200 | 여성 하의 |
| 310300 | 여성 아우터 |
| 320100 | 남성 상의 |
| 320200 | 남성 하의 |
| 601 | 스마트폰 |
| 602 | 태블릿 |
| 800100 | 노트북 |
| 800200 | 데스크탑 |
| 900100 | 디지털카메라 |

> 전체 서브카테고리는 `GET /api/bunjang/categories` API로 조회 가능합니다.

---

## 정렬 파라미터 매핑

| API sort 값 | 번개장터 order 값 | 설명 |
|---|---|---|
| `recommend` | `score` | 관련도순 |
| `recent` | `date` | 최신순 |
| `price_asc` | `price` | 가격 낮은순 |
| `price_desc` | `price_desc` | 가격 높은순 |

---

## 상품 상태 코드

번개장터 API는 `status` 필드를 정수값으로 반환합니다.

| 원본 값 | 변환 값 | 설명 |
|---|---|---|
| `0` | `판매중` | 판매 중 |
| `1` | `예약중` | 예약 중 |
| `2` | `판매완료` | 판매 완료 |

---

## 상품 필드 매핑

| 반환 필드 | 원본 필드 (우선순위 순) | 설명 |
|---|---|---|
| `id` | `pid` → `product_id` | 상품 고유 ID |
| `title` | `name` → `title` | 상품 제목 |
| `price` | `price` | 가격 (정수 변환) |
| `image_url` | `product_image` → `image` | 대표 이미지 URL |
| `status` | `status` | 판매 상태 (정수 → 한글 변환) |
| `location` | `location` | 거래 지역 |
| `time` | `update_time` | 최근 수정 시각 (Unix timestamp) |
| `seller` | `seller_name` | 판매자 닉네임 |
| `likes` | `wish_cnt` | 찜 수 |
| `views` | `view_cnt` | 조회 수 |
| `safe_payment` | `safe_payment` | 안전결제 여부 |
| `category` | `category_name` | 카테고리명 |
| `url` | - | `https://m.bunjang.co.kr/products/{id}` 조합 |

---

## 응답 아이템 구조

```json
{
  "id": "123456789",
  "title": "아이폰 15 Pro 256GB 내추럴티타늄",
  "price": 1200000,
  "price_str": "1,200,000원",
  "image_url": "https://media.bunjang.co.kr/product/...",
  "status": "판매중",
  "location": "강남구",
  "time": "2024-01-15T10:30:00",
  "url": "https://m.bunjang.co.kr/products/123456789",
  "seller": "판매자닉네임",
  "likes": 15,
  "views": 120,
  "safe_payment": true,
  "category": "스마트폰",
  "source": "bunjang"
}
```

---

## 캐시 정책

| 캐시 대상 | TTL | 방식 |
|---|---|---|
| 카테고리 목록 (`/api/1/categories/list.json`) | 영구 (세션 내) | 클래스 레벨 정적 변수 (`_categories_cache`) |

`refresh=true` 파라미터로 캐시를 무시하고 새로 조회할 수 있습니다.

---

## 기술적 특이사항

- **공개 JSON API 사용:** 세 플랫폼 중 유일하게 `api.bunjang.co.kr`의 공개 REST API를 직접 사용. HTML 파싱 없이 구조화된 JSON 데이터 수신 가능
- **0-based 페이지네이션:** 번개장터 API는 `page=0`이 첫 페이지. 외부 API는 1-based로 받아서 내부 변환 (`page - 1`)
- **병렬 카테고리 조회:** 서브카테고리 70개 이상을 `ThreadPoolExecutor`로 병렬 요청 (기본 5 workers)
- **중복 제거:** 여러 카테고리에 동일 상품이 중복 노출될 수 있어 상품 ID 기준 set으로 중복 제거
- **이미지 URL 변환:** 번개장터 이미지 URL에 리사이즈 파라미터(`?xxx=NxN`) 포함 시 원본 URL로 정규화
