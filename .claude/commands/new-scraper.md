# 새 플랫폼 스크래퍼 작성

`$ARGUMENTS` 플랫폼용 스크래퍼를 `crawler/scrapers/{name}_scraper.py`에 작성하라.

## ⚠️ 필수 준수 사항

| 항목 | 값 |
|---|---|
| User-Agent | `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36` |
| 요청 딜레이 | `time.sleep(self.delay)` — 기본 0.5초 이상 |
| 요청 타임아웃 | `requests.get(..., timeout=15)` |
| 병렬 처리 | 알림 폴링 시에만 `ThreadPoolExecutor(max_workers=5)` |
| 앱 검색 | 카테고리 병렬 처리 없음 — 단순 키워드 검색 |

## 표준 출력 스키마 (10개 필드 필수)

모든 스크래퍼의 `search()`, `get_recent_listings()` 반환값은 반드시 이 형식:
```python
{
    "id":        str,   # 플랫폼 고유 상품 ID (문자열)
    "title":     str,   # 상품명
    "price":     int,   # 원 단위 정수 (파싱 실패 시 0)
    "price_str": str,   # "1,200,000원" 형식
    "image_url": str,   # 썸네일 URL (없으면 "")
    "status":    str,   # "판매중" | "예약중" | "판매완료"
    "location":  str,   # 지역명
    "time":      str,   # ISO 8601: "2024-01-15T10:30:00"
    "url":       str,   # 모바일 웹 전체 URL
    "source":    str,   # 플랫폼 식별자 ("bunjang" | "daangn" | "joongna")
}
```

## 클래스 기본 구조

```python
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

class {Name}Scraper:
    BASE_URL = "https://..."
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def search(self, keyword: str, page: int = 1, count: int = 20, **kwargs) -> list[dict]:
        """키워드 검색 — 앱 탭2에서 사용 (카테고리 병렬 처리 없음)"""
        ...

    def get_recent_listings(self, within_minutes: int = 1, max_workers: int = 5, **kwargs) -> list[dict]:
        """최신 매물 수집 — 알림 폴링 전용 (최상위 카테고리 병렬 처리)"""
        ...

    def _normalize(self, raw: dict) -> dict:
        """플랫폼별 원본 데이터를 표준 스키마로 변환"""
        ...
```

## 플랫폼별 수집 방식

### 번개장터 (REST API)
- `api.bunjang.co.kr` 직접 호출 — HTML 파싱 불필요
- `update_time` 필드: Unix timestamp → ISO 8601 변환 필요
- 상태 코드: `0→판매중`, `1→예약중`, `2→판매완료`
- 상품 URL: `https://m.bunjang.co.kr/products/{id}`
- 앱 딥링크: `bunjang://products/{id}`

### 당근 (Remix SSR)
- `window.__remixContext` JSON 블록 정규식 파싱
- 탐색 경로: `state.loaderData["routes/kr.buy-sell.s.allPage"].fleamarketArticles`
- Fallback: BeautifulSoup HTML 파싱
- 상태 코드: `Ongoing→판매중`, `Reserved→예약중`, `Completed→거래완료`
- 상품 URL: `https://www.daangn.com/kr/buy-sell/{id}`
- 앱 딥링크: `karrot://articles/{id}`

### 중고나라 (Next.js SSR)
- `<script id="__NEXT_DATA__">` JSON 블록 파싱
- `search-api.joongna.com` 직접 호출 금지 (차단됨)
- `queryKey[0] == "get-search-products"` 항목 탐색
- 상태 코드: `SALE→판매중`, `RSRV→예약중`, `SOLD/CMPT→판매완료`
- 상품 URL: `https://web.joongna.com/product/{id}`
- 앱 딥링크: `joonggonara://product/{id}`

## 기존 스크래퍼 참고

- `crawler/scrapers/bunjang_scraper.py` — REST API 방식 패턴
- `crawler/scrapers/daangn_scraper.py` — SSR 파싱 + 지역 검색 패턴
- `crawler/scrapers/joongna_scraper.py` — Next.js SSR + 카테고리 병렬 패턴

## 완료 후 처리

`crawler/server.py`에 스크래퍼 인스턴스 추가:
```python
{name} = {Name}Scraper(delay=0.5)
```
그리고 새 검색 엔드포인트 추가 (`/add-crawler-endpoint` 스킬 참고).
