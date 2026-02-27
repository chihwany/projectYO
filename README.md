# 중고 매물 스크래퍼 (Secondhand Market Scraper)

중고나라(web.joongna.com), 번개장터(m.bunjang.co.kr), 당근(www.daangn.com) 매물을 검색/조회하는 Python 스크래핑 프로젝트입니다.

## 설치

```bash
pip install -r requirements.txt
```

## 프로젝트 구조

```
scrapy/
├── server.py              # REST API 서버 (v3.0)
├── joongna_scraper.py     # 중고나라 스크래퍼
├── bunjang_scraper.py     # 번개장터 스크래퍼
├── daangn_scraper.py      # 당근 스크래퍼
├── daangn_regions.py      # 당근 지역 데이터 수집기
├── daangn_regions.json    # 지역 캐시 (크롤링 후 생성)
├── main.py                # 중고나라 CLI
├── bunjang_main.py        # 번개장터 CLI
├── example.py             # 중고나라 예제
├── bunjang_example.py     # 번개장터 예제
├── requirements.txt
└── README.md
```

---

## REST API 서버

### 서버 실행

```bash
python server.py
```

서버: `http://localhost:5000`

### 최초 실행 시: 지역 데이터 수집

당근 지역 검색을 사용하려면 최초 1회 전국 지역 데이터를 크롤링해야 합니다.

```bash
# 방법 1: API로 크롤링 (서버 실행 중)
curl -X POST "http://localhost:5000/api/daangn/regions/crawl"

# 방법 2: CLI로 크롤링 (서버 없이)
python daangn_regions.py
```

수집 완료 후 `daangn_regions.json` 파일이 생성되며, 이후 서버 시작 시 자동 로드됩니다.

### API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/search` | 통합 검색 (3사이트 동시) |
| GET | `/api/joongna/search` | 중고나라 검색 |
| GET | `/api/bunjang/search` | 번개장터 검색 |
| GET | `/api/daangn/search` | 당근 검색 |
| GET | `/api/joongna/product/<id>` | 중고나라 상품 상세 |
| GET | `/api/joongna/categories` | 중고나라 카테고리 |
| GET | `/api/bunjang/categories` | 번개장터 카테고리 |
| GET | `/api/daangn/categories` | 당근 카테고리 |
| **GET** | **`/api/daangn/regions`** | **전체 지역 (계층 구조)** |
| **GET** | **`/api/daangn/regions/search?q=`** | **지역 검색** |
| **GET** | **`/api/daangn/regions/list`** | **지역 목록 (필터)** |
| **POST** | **`/api/daangn/regions/crawl`** | **지역 크롤링 (최초 1회)** |
| GET | `/api/daangn/regions/stats` | 지역 통계 |

### 공통 검색 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `keyword` | string | (필수) | 검색어 |
| `page` | int | 1 | 페이지 번호 |
| `count` | int | 20 | 결과 수 (최대 100) |
| `sort` | string | recommend | recommend, recent, price_asc, price_desc |
| `category` | int | - | 카테고리 코드 |
| `min_price` | int | - | 최소 가격 |
| `max_price` | int | - | 최대 가격 |
| `exclude_sold` | bool | true | 판매완료 제외 |
| `region` | string | - | 당근 지역명 또는 코드 |

### 호출 예시

```bash
# ── 통합 검색 ──
curl "http://localhost:5000/api/search?keyword=아이폰 16"

# ── 당근 지역 검색 ──
curl "http://localhost:5000/api/daangn/search?keyword=맥북&region=강남구"
curl "http://localhost:5000/api/daangn/search?keyword=에어팟&region=역삼동"
curl "http://localhost:5000/api/daangn/search?keyword=자전거&region=판교동-5765"

# ── 지역 검색/자동완성 ──
curl "http://localhost:5000/api/daangn/regions/search?q=판교"
curl "http://localhost:5000/api/daangn/regions/search?q=강남&limit=5"

# ── 지역 목록 (계층 탐색) ──
# 시/도 목록
curl "http://localhost:5000/api/daangn/regions/list"

# 서울특별시 → 구/군 목록
curl "http://localhost:5000/api/daangn/regions/list?city=서울특별시"

# 서울특별시 강남구 → 동 목록
curl "http://localhost:5000/api/daangn/regions/list?city=서울특별시&district=강남구"

# ── 지역 크롤링 (최초 1회) ──
curl -X POST "http://localhost:5000/api/daangn/regions/crawl"

# 강제 갱신
curl -X POST "http://localhost:5000/api/daangn/regions/crawl?force=true"

# ── 지역 통계 ──
curl "http://localhost:5000/api/daangn/regions/stats"
```

### 지역 검색 응답 예시

```bash
GET /api/daangn/regions/search?q=판교
```

```json
{
  "success": true,
  "data": [
    {
      "name": "판교동",
      "code": "판교동-5765",
      "district": "분당구",
      "city": "경기도 성남시",
      "full": "경기도 성남시 분당구 판교동"
    }
  ],
  "query": "판교",
  "count": 1
}
```

### 지역 목록 응답 예시

```bash
GET /api/daangn/regions/list?city=서울특별시&district=강남구
```

```json
{
  "success": true,
  "data": [
    {"name": "역삼동", "code": "역삼동-360"},
    {"name": "개포동", "code": "개포동-361"},
    {"name": "청담동", "code": "청담동-362"},
    ...
  ],
  "level": "neighborhood",
  "city": "서울특별시",
  "district": "강남구",
  "count": 22
}
```

---

## 중고나라 (Joongna)

### Python 코드

```python
from joongna_scraper import JoongnaScraper

scraper = JoongnaScraper()
results = scraper.search("아이폰 15")
results = scraper.search("맥북", category=8, sort="RECENT_SORT")
results = scraper.search("갤럭시", min_price=100000, max_price=500000)
```

### CLI

```bash
python main.py "아이폰 15"
python main.py "맥북" --category 8
python main.py "에어팟" --sort recent --json
```

---

## 번개장터 (Bunjang)

### Python 코드

```python
from bunjang_scraper import BunjangScraper

scraper = BunjangScraper()
results = scraper.search("아이폰 16")
results = scraper.search("맥북", sort="recent", min_price=500000)
results = scraper.search_all("에어팟", max_pages=3)
```

### CLI

```bash
python bunjang_main.py "아이폰 16"
python bunjang_main.py "맥북" --sort recent --count 10
```

---

## 당근 (Daangn)

### Python 코드

```python
from daangn_scraper import DaangnScraper

scraper = DaangnScraper()

# 기본 검색
results = scraper.search("아이폰 16")

# 지역 지정 (이름만으로 자동 매칭)
results = scraper.search("맥북", region="강남구")
results = scraper.search("자전거", region="판교동")

# 코드 직접 지정
results = scraper.search("에어팟", region="역삼동-360")

# 가격 필터
results = scraper.search("갤럭시", region="서초4동", min_price=200000, max_price=800000)
```

### 지역 데이터 수집 (CLI)

```bash
# 전국 지역 크롤링
python daangn_regions.py

# 캐시 무시하고 다시 크롤링
python daangn_regions.py --force

# 지역 검색
python daangn_regions.py --search 판교

# 통계
python daangn_regions.py --stats
```

---

## 카테고리 코드

### 중고나라

| 코드 | 카테고리 |
|------|----------|
| 1 | 수입명품 |
| 2 | 패션의류 |
| 6 | 모바일/태블릿 |
| 7 | 가전제품 |
| 8 | 노트북/PC |
| 12 | 게임 |
| ... | [전체 목록: /api/joongna/categories] |

### 번개장터

| 코드 | 카테고리 |
|------|----------|
| 600 | 모바일/태블릿 |
| 601 | 스마트폰 |
| 800 | 노트북/PC |
| 310 | 여성의류 |
| ... | [전체 목록: /api/bunjang/categories] |

### 당근

| 코드 | 카테고리 |
|------|----------|
| 1 | 디지털기기 |
| 172 | 생활가전 |
| 5 | 여성의류 |
| 14 | 남성패션/잡화 |
| ... | [전체 목록: /api/daangn/categories] |

---

## 정렬 옵션

| 값 | 설명 |
|------|------|
| `recommend` | 추천순 (기본값) |
| `recent` | 최신순 |
| `price_asc` | 낮은가격순 |
| `price_desc` | 높은가격순 |

---

## 주의사항

- 과도한 요청은 IP 차단을 유발할 수 있으니 적절한 간격을 두고 사용하세요.
- 당근 지역 크롤링은 전국 기준 수 분 소요됩니다 (1회만 실행하면 캐싱됨).
- 본 프로젝트는 학습/개인 목적으로만 사용하세요.
- 각 사이트의 이용약관을 준수하세요.
