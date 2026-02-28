# 스크래퍼 디버깅

`$ARGUMENTS` 스크래퍼에서 발생한 문제를 진단하고 수정하라.

## 플랫폼별 진단 체크리스트

### 번개장터 (bunjang)

```python
# 즉시 테스트
import requests

url = "https://api.bunjang.co.kr/api/1/find_it/search.json"
params = {"q": "테스트", "page": 0, "n": 10, "f": "all", "st": "updatedAt", "sd": "desc"}
headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

r = requests.get(url, params=params, headers=headers, timeout=15)
print(r.status_code)
print(r.json().keys())  # 응답 구조 확인
```

**자주 발생하는 문제:**
- `403 Forbidden`: User-Agent 확인 (Chrome 131 UA 필수)
- `빈 list 반환`: `page=0` 이 첫 페이지 (1-based 변환 오류 확인)
- `update_time` 파싱 오류: Unix timestamp → ISO 8601 변환 확인
  ```python
  from datetime import datetime, timezone
  dt = datetime.fromtimestamp(int(update_time), tz=timezone.utc)
  iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
  ```
- 상태 코드: `0→판매중`, `1→예약중`, `2→판매완료` (숫자 타입 주의)

---

### 당근 (daangn)

```python
# 즉시 테스트
import requests, re, json

url = "https://www.daangn.com/kr/buy-sell/?in=역삼동-360&search=테스트"
headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

r = requests.get(url, headers=headers, timeout=15)
print(r.status_code)

# window.__remixContext 블록 파싱 시도
match = re.search(r'window\.__remixContext\s*=\s*(\{.*?\});\s*</script>', r.text, re.DOTALL)
if match:
    data = json.loads(match.group(1))
    # 탐색 경로
    articles = data.get("state", {}).get("loaderData", {}) \
                   .get("routes/kr.buy-sell.s.allPage", {}) \
                   .get("fleamarketArticles", [])
    print(f"상품 수: {len(articles)}")
    if articles:
        print("첫 번째 상품:", articles[0].keys())
else:
    print("__remixContext 블록 없음 → BeautifulSoup fallback 필요")
```

**자주 발생하는 문제:**
- `__remixContext` 없음: Daangn이 렌더링 방식을 변경했을 수 있음 → BeautifulSoup fallback 확인
- 정규식 매칭 실패: HTML 구조가 변경됐을 때 → `re.DOTALL` 플래그 확인, 블록 경계 재확인
- 탐색 경로 변경: `routes/kr.buy-sell.s.allPage` 키가 달라질 수 있음 → `loaderData` 전체 키 출력으로 확인
- 지역코드 형식: `역삼동-360` (이름-코드) 형식 확인, `daangn_regions.py`에서 올바른 코드 조회
- 상태 코드: `Ongoing→판매중`, `Reserved→예약중`, `Completed→거래완료` (대소문자 주의)

---

### 중고나라 (joongna)

```python
# 즉시 테스트
import requests, json
from bs4 import BeautifulSoup

url = "https://web.joongna.com/search/테스트"
headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}

r = requests.get(url, headers=headers, timeout=15)
print(r.status_code)

# __NEXT_DATA__ 파싱
soup = BeautifulSoup(r.text, "html.parser")
tag = soup.find("script", {"id": "__NEXT_DATA__"})
if tag:
    data = json.loads(tag.string)
    # 검색 결과 탐색
    queries = data.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])
    print(f"쿼리 수: {len(queries)}")
    for q in queries:
        key = q.get("queryKey", [])
        if key and key[0] == "get-search-products":
            products = q.get("state", {}).get("data", {}).get("data", {}).get("items", [])
            print(f"상품 수: {len(products)}")
            if products:
                print("첫 번째 상품:", products[0].keys())
            break
else:
    print("__NEXT_DATA__ 블록 없음")
```

**자주 발생하는 문제:**
- `403 Forbidden`: User-Agent 확인 (Chrome 131 UA 필수, 절대 변경 금지)
- `search-api.joongna.com` 직접 호출: ⚠️ **차단됨** — 반드시 HTML 우회 (`web.joongna.com`)
- `__NEXT_DATA__` 없음: 중고나라가 렌더링 방식 변경 → `script` 태그 전체 목록 확인
- 쿼리 탐색 실패: `queryKey[0]` 값이 변경됐을 수 있음 → 전체 `queryKey` 목록 출력으로 확인
- 상태 코드: `SALE→판매중`, `RSRV→예약중`, `SOLD/CMPT→판매완료`

---

## 공통 디버깅 패턴

### 응답 구조 변경 감지

```python
# HTML 원본 덤프 (구조 변경 확인용)
with open("debug_response.html", "w", encoding="utf-8") as f:
    f.write(r.text)
# → debug_response.html 파일을 열어 구조 직접 확인
```

### 타임스탬프 파싱 검증

```python
from datetime import datetime, timezone

# Unix timestamp → ISO 8601
ts = 1705292400  # 예시
dt = datetime.fromtimestamp(ts, tz=timezone.utc)
print(dt.strftime("%Y-%m-%dT%H:%M:%S"))  # "2024-01-15T03:00:00"

# ISO 8601 문자열 그대로 사용 가능한지 확인
import dateutil.parser
dt = dateutil.parser.isoparse("2024-01-15T10:30:00+09:00")
print(dt.isoformat())
```

### Flask 엔드포인트 직접 테스트

```bash
# 크롤러 서버가 실행 중인 상태에서
curl "http://localhost:5000/api/bunjang/search?keyword=아이폰&count=5"
curl "http://localhost:5000/api/daangn/search?keyword=아이폰&region=역삼동-360"
curl "http://localhost:5000/api/daangn/district-search?keyword=아이폰&district=강남구-10"
curl "http://localhost:5000/api/joongna/search?keyword=아이폰&count=5"
```

### 표준 스키마 검증

```python
REQUIRED_FIELDS = {"id", "title", "price", "price_str", "image_url", "status", "location", "time", "url", "source"}

def validate_item(item: dict):
    missing = REQUIRED_FIELDS - set(item.keys())
    if missing:
        print(f"❌ 누락 필드: {missing}")
    if not isinstance(item.get("price"), int):
        print(f"❌ price가 int가 아님: {type(item.get('price'))}")
    if item.get("status") not in ("판매중", "예약중", "판매완료"):
        print(f"❌ status 값 오류: {item.get('status')}")
    print("✅ 스키마 검증 통과")

# 사용법
items = scraper.search("테스트")
for item in items[:3]:
    validate_item(item)
    print(item)
```

## 디버깅 우선순위

1. **HTTP 상태코드 확인** → 403/429면 UA 또는 딜레이 문제
2. **응답 본문 구조 확인** → JSON 파싱 경로 문제
3. **개별 필드 파싱 확인** → 정규식/타입 변환 문제
4. **표준 스키마 검증** → 누락 필드 또는 타입 오류
5. **Flask 엔드포인트 직접 curl** → 서버 레벨 문제
