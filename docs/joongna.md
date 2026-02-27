# 중고나라 (Joonggonara) 스크래핑 문서

## 개요

| 항목 | 내용 |
|---|---|
| 사이트명 | 중고나라 |
| 사이트 URL | https://web.joongna.com |
| 스크래핑 방식 | **SSR(서버사이드 렌더링) HTML 파싱** |
| 데이터 추출 방법 | HTML 내 `<script id="__NEXT_DATA__">` JSON 파싱 |
| 프레임워크 | Next.js (SSR) |
| 관련 모듈 | `scrapers/joongna_scraper.py` |

> **참고:** 중고나라는 Next.js 기반 SSR 사이트로, 검색 결과를 HTML 내 `__NEXT_DATA__` JSON 블록에 내장하여 제공합니다. 별도의 REST API를 직접 호출하지 않고 웹 페이지 HTML을 요청한 후 해당 JSON을 파싱합니다.

---

## 목차

- [검색 스크래핑](#검색-스크래핑)
- [최신 목록 스크래핑](#최신-목록-스크래핑)
- [상품 상세 스크래핑](#상품-상세-스크래핑)
- [HTTP 헤더](#http-헤더)
- [데이터 파싱 구조](#데이터-파싱-구조)
- [카테고리 목록](#카테고리-목록)
- [정렬 파라미터 매핑](#정렬-파라미터-매핑)
- [상품 상태 코드](#상품-상태-코드)
- [응답 아이템 구조](#응답-아이템-구조)

---

## 검색 스크래핑

### 요청 정보

| 항목 | 내용 |
|---|---|
| HTTP 메서드 | `GET` |
| 요청 URL | `https://web.joongna.com/search/{인코딩된_키워드}` |
| 인코딩 방식 | `urllib.parse.quote(keyword)` (URL 인코딩) |

### Query String 파라미터

| 파라미터 | 예시 값 | 설명 |
|---|---|---|
| `keywordSource` | `INPUT_KEYWORD` | 키워드 입력 소스 (고정값) |
| `page` | `1`, `2`, `3` | 페이지 번호 (1부터 시작) |
| `category` | `6` | 카테고리 코드 (지정 시에만 포함) |
| `minPrice` | `10000` | 최소 가격 (0 초과 시에만 포함) |
| `maxPrice` | `500000` | 최대 가격 (100,000,000 미만 시에만 포함) |
| `sort` | `RECENT_SORT` | 정렬 방식 (recommend가 아닐 때만 포함) |
| `saleYn` | `ALL` | 판매완료 포함 여부 (`exclude_sold=false` 시 포함) |

**요청 URL 예시:**

```
GET https://web.joongna.com/search/%EC%95%84%EC%9D%B4%ED%8F%B0?keywordSource=INPUT_KEYWORD&page=1&sort=RECENT_SORT&minPrice=100000
```

---

## 최신 목록 스크래핑

카테고리별로 최신 등록 상품을 가져옵니다. ThreadPoolExecutor를 사용하여 여러 카테고리를 병렬로 요청합니다.

### 요청 정보

| 항목 | 내용 |
|---|---|
| HTTP 메서드 | `GET` |
| 요청 URL | `https://web.joongna.com/search` |

### Query String 파라미터

| 파라미터 | 값 | 설명 |
|---|---|---|
| `category` | `{카테고리_코드}` | 대상 카테고리 |
| `sort` | `RECENT_SORT` | 최신순 고정 |
| `page` | `1` | 첫 페이지 |
| `minPrice` | `{min_price}` | 최소 가격 (지정 시) |
| `maxPrice` | `{max_price}` | 최대 가격 (지정 시) |
| `saleYn` | `ALL` | 판매완료 포함 시 |

**요청 URL 예시:**

```
GET https://web.joongna.com/search?category=6&sort=RECENT_SORT&page=1
```

---

## 상품 상세 스크래핑

### 요청 정보

| 항목 | 내용 |
|---|---|
| HTTP 메서드 | `GET` |
| 요청 URL | `https://web.joongna.com/product/{상품_ID}` |

**요청 URL 예시:**

```
GET https://web.joongna.com/product/12345678
```

---

## HTTP 헤더

모든 요청에 공통으로 사용하는 HTTP 헤더입니다.

```http
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
Accept-Language: ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7
Referer: https://web.joongna.com/
```

- **Request timeout:** 15초
- **User-Agent:** 고정 Chrome 브라우저 UA 사용 (봇 차단 우회)

---

## 데이터 파싱 구조

중고나라는 HTML 내에 Next.js 렌더링 데이터를 JSON 형태로 내장합니다.

### 1단계: `__NEXT_DATA__` 추출

```html
<script id="__NEXT_DATA__" type="application/json">
  { ... 상품 데이터 포함 ... }
</script>
```

BeautifulSoup으로 `<script id="__NEXT_DATA__">` 태그를 찾아 JSON으로 파싱합니다.

### 2단계: 상품 목록 경로

```
__NEXT_DATA__
  └── props
        └── pageProps
              └── dehydratedState
                    └── queries[]
                          └── (queryKey[0] == "get-search-products" 인 항목)
                                └── state
                                      └── data
                                            └── data  ← 상품 목록 배열
```

**탐색 로직:**
1. `queries` 배열에서 `queryKey[0]`이 `"get-search-products"`인 항목을 우선 탐색
2. 없을 경우 `items` 필드를 가진 첫 번째 query 항목을 fallback으로 사용

### 3단계: 상품 상세 페이지 경로

```
__NEXT_DATA__
  └── props
        └── pageProps
              └── dehydratedState
                    └── queries[]
                          └── (queryKey에 "product-detail" 또는 "product" 포함)
                                └── state
                                      └── data  ← 상품 상세 데이터
```

---

## 상품 필드 매핑

HTML에서 추출되는 원본 JSON 필드와 변환 후 반환 필드의 매핑입니다.

| 반환 필드 | 원본 필드 (우선순위 순) | 설명 |
|---|---|---|
| `id` | `seq` → `productSeq` | 상품 고유 ID |
| `title` | `title` → `productTitle` | 상품 제목 |
| `price` | `price` | 가격 (정수, 원) |
| `image_url` | `imageUrl` → `imageUrls[0]` | 대표 이미지 URL |
| `status` | `saleStatus` | 판매 상태 코드 |
| `location` | `locationName` → `area` | 거래 지역 |
| `time` | `sortDate` → `regDate` | 등록/갱신 시각 |
| `seller` | `storeName` → `sellerName` | 판매자 닉네임 |
| `likes` | `wishCount` → `likeCount` | 찜 수 |
| `views` | `viewCount` | 조회 수 |
| `safe_payment` | `jnPayYn` | 안전결제 가능 여부 |
| `category` | `categoryName` | 카테고리명 |
| `url` | - | `https://web.joongna.com/product/{id}` 조합 |

---

## 카테고리 목록

| 코드 | 카테고리명 |
|---|---|
| 1 | 수입명품 |
| 2 | 패션의류 |
| 3 | 패션잡화 |
| 4 | 뷰티 |
| 5 | 출산/유아동 |
| 6 | 모바일/태블릿 |
| 7 | 가전제품 |
| 8 | 노트북/PC |
| 9 | 카메라/캠코더 |
| 10 | 가구/인테리어 |
| 11 | 리빙/생활 |
| 12 | 게임 |
| 13 | 반려동물/취미 |
| 14 | 도서/음반/문구 |
| 15 | 티켓/쿠폰 |
| 16 | 스포츠 |
| 17 | 레저/여행 |
| 19 | 오토바이 |
| 20 | 공구/산업용품 |
| 21 | 무료나눔 |

---

## 정렬 파라미터 매핑

API에서 받는 `sort` 값과 실제 중고나라 쿼리 파라미터 값의 매핑입니다.

| API sort 값 | 중고나라 sort 값 | 설명 |
|---|---|---|
| `recommend` | *(파라미터 미포함)* | 추천순 (기본값) |
| `recent` | `RECENT_SORT` | 최신순 |
| `price_asc` | `PRICE_ASC_SORT` | 가격 낮은순 |
| `price_desc` | `PRICE_DESC_SORT` | 가격 높은순 |

---

## 상품 상태 코드

| 원본 코드 | 변환 값 | 설명 |
|---|---|---|
| `SALE` | `판매중` | 판매 중 |
| `RSRV` | `예약중` | 예약 중 |
| `SOLD` | `판매완료` | 판매 완료 |
| `CMPT` | `판매완료` | 거래 완료 |

---

## 응답 아이템 구조

```json
{
  "id": "12345678",
  "title": "아이폰 15 Pro 256GB 자급제",
  "price": 1200000,
  "price_str": "1,200,000원",
  "image_url": "https://img.joongna.com/product/...",
  "status": "판매중",
  "location": "서울 강남구",
  "time": "2024-01-15T10:30:00",
  "url": "https://web.joongna.com/product/12345678",
  "seller": "판매자닉네임",
  "likes": 15,
  "views": 120,
  "safe_payment": true,
  "category": "모바일/태블릿",
  "source": "joongna"
}
```

---

## 기술적 특이사항

- **직접 API 호출 불가:** `https://search-api.joongna.com/v25/search/product` 등의 내부 검색 API는 카테고리나 키워드 없이는 직접 호출 시 차단됨. 웹 페이지 HTML을 통해 우회
- **SSR 의존:** 데이터가 서버에서 렌더링되어 HTML에 포함되므로 JavaScript 실행 없이도 데이터 추출 가능
- **최신 목록 병렬 처리:** 20개 카테고리를 동시에 요청하기 위해 `ThreadPoolExecutor` 사용 (기본 5 workers)
- **중복 제거:** 병렬 요청 시 동일 상품 ID가 여러 카테고리에 등장할 수 있으므로 set으로 ID 추적하여 중복 제거
