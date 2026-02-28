# 통합 중고 거래 키워드 알림 앱 개발 플랜

이 문서는 번개장터·당근·중고나라 데이터를 통합하여 사용자 키워드 기반으로 신규 매물을 실시간 푸시 알림하는 서비스의 전체 설계 및 실행 계획입니다. Claude Code 바이브 코딩 기반 개발을 위한 지시서로 활용됩니다.

---

## 1. 플랫폼별 데이터 수집 전략

각 플랫폼의 기술적 특성과 제약에 맞춘 수집 방식을 채택합니다.

### A. 번개장터 (Bunjang)

- **수집 방식**: 공개 JSON REST API(`api.bunjang.co.kr`) 직접 호출 — HTML 파싱 불필요
- **알림 폴링 방식**: 1분마다 최신 매물 수집 → 신규 상품 ID 추출 → 키워드 매칭 후 FCM 발송
- **앱 검색**: 사용자가 탭에서 직접 키워드 검색 시 실시간 API 호출
- **카테고리 병렬 처리**: 알림 폴링 시에만 사용 — `ThreadPoolExecutor(max_workers=5)`로 19개 상위 카테고리 동시 요청
- **중복 제거**: 상품 ID 기준 `set` 자료구조로 카테고리 간 중복 제거
- **페이지네이션**: 0-based (`page=0`이 첫 페이지), 외부에서 1-based로 받아 내부 변환
- **상품 URL 조합**: `https://m.bunjang.co.kr/products/{id}` (모바일 웹)
- **앱 딥링크**: `bunjang://products/{id}` → 앱 미설치 시 모바일 웹으로 폴백
- **상태 코드**: `0→판매중`, `1→예약중`, `2→판매완료`

### B. 당근 (Daangn)

- **수집 방식**: Remix SSR의 `window.__remixContext` JSON 블록 HTML 파싱 (JS 실행 불필요)
- **알림 폴링**: ⚠️ **당근은 폴링 없음** — 스케줄러에서 완전 제외
- **앱 검색 방식**: 사용자가 구/군(강남구) 레벨 지역 선택 → 해당 구/군 하위의 모든 동(역삼동, 논현동 등) 자동 조회 → 각 동마다 병렬 검색 → 중복 제거 후 통합 리스트 반환
- **하위 동 확장 로직**: `daangn_regions.py`에서 선택된 구/군 코드의 depth=3 지역(동/읍/면) 전체 목록 조회 → `ThreadPoolExecutor`로 병렬 검색
- **지역 코드 형식**: `역삼동-360`, `강남구-10` (구/군 선택 시 내부적으로 하위 동 코드 목록으로 확장)
- **Fallback**: `__remixContext` 파싱 실패 시 BeautifulSoup HTML 파싱으로 전환
- **제한 사항**: 판매자 닉네임·조회수·찜수 정보가 목록 페이지에서 제공되지 않음
- **상품 URL 조합**: `https://www.daangn.com/kr/buy-sell/{id}` (모바일 웹)
- **앱 딥링크**: `karrot://articles/{id}` → 앱 미설치 시 모바일 웹으로 폴백
- **상태 코드**: `Ongoing→판매중`, `Reserved→예약중`, `Completed→거래완료`

### C. 중고나라 (Joonggonara)

- **수집 방식**: Next.js SSR의 `<script id="__NEXT_DATA__">` JSON 블록 HTML 파싱
- **알림 폴링 방식**: 1분마다 최신 매물 수집 → 신규 상품 ID 추출 → 키워드 매칭 후 FCM 발송
- **앱 검색**: 사용자가 탭에서 직접 키워드 입력 → 단순 키워드 검색 API 호출 (카테고리 병렬 처리 없음)
- **카테고리 병렬 처리**: 알림 폴링 시에만 사용 — `ThreadPoolExecutor(max_workers=5)`로 최상위 카테고리 동시 요청
- **직접 API 차단**: `search-api.joongna.com` 직접 호출 시 차단됨 → 반드시 웹 HTML 우회
- **User-Agent**: 고정 Chrome 131 UA 사용 (봇 감지 우회)
- **상품 URL 조합**: `https://web.joongna.com/product/{id}` (모바일 웹)
- **앱 딥링크**: 중고나라 앱 딥링크 스킴 → 앱 미설치 시 모바일 웹으로 폴백
- **상태 코드**: `SALE→판매중`, `RSRV→예약중`, `SOLD/CMPT→판매완료`

---

## 2. 플랫폼 앱 딥링크 명세

상품 카드를 탭하면 해당 플랫폼 앱으로 연결합니다. 앱이 설치되어 있지 않으면 모바일 웹 페이지로 폴백합니다.

| 플랫폼 | 앱 딥링크 URI | 폴백 모바일 웹 URL |
|---|---|---|
| 번개장터 | `bunjang://products/{product_id}` | `https://m.bunjang.co.kr/products/{product_id}` |
| 당근 | `karrot://articles/{product_id}` | `https://www.daangn.com/kr/buy-sell/{product_id}` |
| 중고나라 | `joonggonara://product/{product_id}` | `https://web.joongna.com/product/{product_id}` |

### Flutter 딥링크 처리 로직

```dart
// services/deep_link_service.dart
import 'package:url_launcher/url_launcher.dart';

Future<void> openProduct(String platform, String productId) async {
  final deepLinks = {
    'bunjang':  'bunjang://products/$productId',
    'daangn':   'karrot://articles/$productId',
    'joongna':  'joonggonara://product/$productId',
  };
  final webUrls = {
    'bunjang':  'https://m.bunjang.co.kr/products/$productId',
    'daangn':   'https://www.daangn.com/kr/buy-sell/$productId',
    'joongna':  'https://web.joongna.com/product/$productId',
  };

  final appUri = Uri.parse(deepLinks[platform]!);
  final webUri = Uri.parse(webUrls[platform]!);

  if (await canLaunchUrl(appUri)) {
    // 앱이 설치된 경우 → 앱으로 이동
    await launchUrl(appUri);
  } else {
    // 앱 미설치 → 모바일 웹으로 이동
    await launchUrl(webUri, mode: LaunchMode.externalApplication);
  }
}
```

> **Flutter 패키지**: `url_launcher: ^6.x` 사용. Android는 `AndroidManifest.xml`에 각 앱 패키지 쿼리 추가 필요, iOS는 `Info.plist`에 `LSApplicationQueriesSchemes` 등록 필요.

---

## 3. 전체 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Flutter Mobile App                           │
│  탭1: 당근 검색 / 탭2: 번개+중고나라 검색 / 탭3: 알림 이력 / 탭4: 설정   │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ REST API (HTTP)
                       │ 검색: 비로그인 허용 / 키워드·알림: 로그인 필요
┌──────────────────────▼──────────────────────────────────────────────┐
│                 Python + FastAPI Backend Server                      │
│  사용자 인증(자체/소셜) / 키워드 관리 / FCM 발송 / 알림 이력 관리         │
│  + 크롤러 API 프록시 (당근·번개·중고나라 검색 요청 중계)                  │
└───────┬──────────────────────────────┬───────────────────────────────┘
        │ PostgreSQL                   │ Redis
        │ (사용자/키워드/알림 이력)        │ (중복 방지 seen_ids / Stream 큐)
        │                              │
┌───────▼──────────────────────────────▼───────────────────────────────┐
│              Python Crawler + Scheduler (Flask + APScheduler)        │
│  번개장터·중고나라: 1분 폴링 (최상위 카테고리 병렬 수집)                  │
│  신규 매물 감지 → Redis Stream 적재 → FastAPI Consumer가 소비           │
│  (당근은 스케줄러 제외 — 앱 탭에서 직접 검색)                             │
└──────────────────────────────────────────────────────────────────────┘
```

### 데이터 흐름 상세

```
[Python Scheduler - 번개장터/중고나라만]
  └─ 1분마다 번개장터 최신매물 수집 (within_minutes=1, 최상위 카테고리 병렬)
  └─ 1분마다 중고나라 최신매물 수집 (within_minutes=1, 최상위 카테고리 병렬)
  └─ 신규 상품 감지 (Redis seen_ids로 중복 체크)
  └─ 신규 상품 → Redis Stream (product_alerts) 에 XADD

[FastAPI Alert Consumer (백그라운드 태스크)]
  └─ Redis Stream XREAD로 실시간 소비
  └─ PostgreSQL에서 활성 키워드 전체 조회
  └─ 키워드 부분 일치 + 가격 범위 필터
  └─ 매칭된 사용자별 읽지 않은 알림 건수 집계
  └─ FCM 발송: "신규 알림이 총 N건 있습니다."
  └─ 알림 이력 PostgreSQL 저장

[당근 탭 - 앱에서 직접 검색]
  └─ 사용자: 구/군 레벨 지역 선택 (예: 강남구) + 키워드 입력
  └─ FastAPI → Crawler Flask API (district-search 엔드포인트)
  └─ daangn_regions.py에서 강남구 하위 동 전체 목록 조회 (depth=3)
  └─ 각 동마다 ThreadPoolExecutor로 병렬 검색
  └─ 중복 상품 ID 제거 후 통합 결과 반환
  └─ (스케줄러와 무관, 폴링 없음)
```

---

## 4. 기술 스택

| 레이어 | 기술 | 버전 | 이유 |
|---|---|---|---|
| **Crawler** | Python + Flask | 3.11+ / 3.0+ | 스크래퍼 구현, requests/BeautifulSoup 파싱 |
| **Scheduler** | APScheduler | 3.x | 1분 주기 폴링, Flask 프로세스에 내장 |
| **Backend** | Python + FastAPI | 3.11+ / 0.100+ | Python 언어 통일, 비동기 I/O, 자동 API 문서 |
| **ORM** | SQLAlchemy + Alembic | 2.x | DB 모델 정의 및 마이그레이션 |
| **Validation** | Pydantic v2 | 2.x | 요청/응답 데이터 검증 |
| **Database** | PostgreSQL | 16 | 사용자/키워드/알림 이력 영구 저장 |
| **Cache/Queue** | Redis | 7.x | seen_ids 중복 방지, Stream 메시지 큐 |
| **Push Notification** | Firebase Admin SDK (Python) | 6.x | iOS/Android 크로스 플랫폼 무료 푸시 |
| **Auth** | python-jose (JWT) + passlib | - | 자체 로그인 토큰 발급, 비밀번호 해싱 |
| **Mobile** | Flutter | 3.x | 단일 코드베이스 iOS/Android |
| **딥링크** | url_launcher | 6.x | 앱 딥링크 + 모바일 웹 폴백 처리 |
| **상태관리** | Riverpod | 2.x | 선언적 상태관리, 테스트 용이 |
| **네비게이션** | GoRouter | - | 딥링크, 선언적 라우팅 |
| **인프라** | Docker Compose | - | 로컬 개발 환경 통합 구성 |
| **프로덕션** | Railway / GCP Cloud Run | - | 컨테이너 기반 무중단 배포 |

### API 인증 적용 범위

| 범위 | 인증 필요 여부 | 해당 API |
|---|---|---|
| 검색 | **불필요** (비로그인 가능) | `/search/*` 전체 |
| 키워드 관리 | **필요** (JWT Bearer) | `/keywords/*` 전체 |
| 알림 이력 | **필요** (JWT Bearer) | `/notifications/*` 전체 |
| FCM 토큰 등록 | **필요** (JWT Bearer) | `PATCH /auth/fcm-token` |
| 회원가입/로그인 | **불필요** | `POST /auth/register`, `POST /auth/login` |

---

## 5. 디렉토리 구조 (목표 구조)

> 모든 `.py` 파일은 새로 바이브 코딩으로 작성합니다.

```
projectYO/
├── crawler/                        # Python 크롤러 서버
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── bunjang_scraper.py      # 번개장터 REST API 스크래퍼
│   │   ├── daangn_scraper.py       # 당근 SSR HTML 스크래퍼
│   │   └── joongna_scraper.py      # 중고나라 SSR HTML 스크래퍼
│   ├── data/
│   │   └── daangn_regions.py       # 당근 지역명 → 지역코드 + 하위 동 목록
│   ├── server.py                   # Flask REST API (검색/수집 엔드포인트)
│   │                               #   포함: GET /api/daangn/district-search
│   │                               #   (구/군 → 하위 동 전체 병렬 검색)
│   ├── scheduler.py                # APScheduler: 번개장터·중고나라 1분 폴링
│   ├── redis_client.py             # Redis 연결 및 Stream XADD 발행
│   └── requirements.txt            # requests, bs4, flask, apscheduler, redis
│
├── backend/                        # Python + FastAPI 백엔드
│   ├── app/
│   │   ├── main.py                 # FastAPI 앱 진입점, lifespan 이벤트
│   │   ├── database.py             # SQLAlchemy 엔진 + 세션 팩토리
│   │   ├── models/                 # SQLAlchemy ORM 모델
│   │   │   ├── __init__.py
│   │   │   ├── user.py             # User 모델 (소셜 로그인 포함)
│   │   │   ├── keyword.py          # Keyword 모델
│   │   │   └── notification.py     # NotificationHistory 모델
│   │   ├── schemas/                # Pydantic 입출력 스키마
│   │   │   ├── auth.py
│   │   │   ├── keyword.py
│   │   │   └── notification.py
│   │   ├── routers/                # FastAPI 라우터
│   │   │   ├── auth.py             # 로그인/회원가입/소셜 OAuth
│   │   │   ├── keywords.py         # 키워드 CRUD (인증 필요)
│   │   │   ├── notifications.py    # 알림 이력 조회 (인증 필요)
│   │   │   └── search.py           # 크롤러 API 프록시 (인증 불필요)
│   │   ├── services/               # 비즈니스 로직
│   │   │   ├── auth_service.py     # JWT 발급, 소셜 토큰 교환
│   │   │   ├── fcm_service.py      # FCM 푸시 발송
│   │   │   └── alert_consumer.py   # Redis Stream Consumer (백그라운드)
│   │   └── core/
│   │       ├── config.py           # 환경변수 (pydantic-settings)
│   │       ├── security.py         # JWT 생성/검증, 비밀번호 해싱
│   │       └── redis.py            # Redis 클라이언트 싱글톤
│   ├── alembic/                    # DB 마이그레이션
│   │   └── versions/
│   └── requirements.txt            # fastapi, sqlalchemy, alembic, redis, firebase-admin 등
│
├── mobile/                         # Flutter 앱
│   ├── lib/
│   │   ├── main.dart               # 앱 진입점, GoRouter, Riverpod ProviderScope
│   │   ├── router.dart             # GoRouter 라우트 정의
│   │   ├── tabs/
│   │   │   ├── daangn_tab.dart     # 탭1: 당근 지역 선택 + 검색
│   │   │   ├── market_tab.dart     # 탭2: 번개장터·중고나라 통합 검색
│   │   │   ├── alerts_tab.dart     # 탭3: 알림 수신 이력
│   │   │   └── settings_tab.dart   # 탭4: 설정 (비로그인 → 로그인 화면)
│   │   ├── screens/
│   │   │   ├── auth/
│   │   │   │   ├── login_screen.dart       # 자체 + 소셜 로그인
│   │   │   │   └── register_screen.dart    # 자체 회원가입
│   │   │   └── keyword/
│   │   │       ├── keyword_list_screen.dart
│   │   │       └── keyword_form_screen.dart
│   │   ├── providers/              # Riverpod 상태 관리
│   │   │   ├── auth_provider.dart
│   │   │   ├── keyword_provider.dart
│   │   │   ├── search_provider.dart
│   │   │   └── notification_provider.dart
│   │   ├── services/
│   │   │   ├── api_service.dart        # Dio 기반 HTTP 클라이언트
│   │   │   ├── fcm_service.dart        # FCM 수신 + 로컬 알림
│   │   │   └── deep_link_service.dart  # 앱 딥링크 + 모바일 웹 폴백
│   │   ├── models/                 # 데이터 모델 (freezed)
│   │   │   ├── product.dart
│   │   │   ├── keyword.dart
│   │   │   └── notification.dart
│   │   └── widgets/
│   │       ├── product_card.dart   # 상품 카드 (탭 → 딥링크 처리)
│   │       └── platform_badge.dart
│   └── pubspec.yaml
│
├── docker-compose.yml              # PostgreSQL + Redis 로컬 환경
├── docs/
│   ├── plan.md
│   ├── bunjang.md
│   ├── daangn.md
│   └── joongna.md
└── .env.example
```

---

## 6. PostgreSQL 데이터베이스 스키마

### users 테이블

자체 로그인, 네이버, 카카오, 구글 소셜 로그인을 모두 지원하는 통합 구조입니다.

```sql
CREATE TABLE users (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email            VARCHAR(255),                -- 자체 로그인 필수 / 소셜 로그인 선택
  password_hash    VARCHAR(255),                -- 자체 로그인 시 bcrypt 해시 / 소셜은 NULL
  nickname         VARCHAR(100),
  auth_provider    VARCHAR(20) NOT NULL DEFAULT 'local',
                                               -- 'local' | 'naver' | 'kakao' | 'google'
  provider_id      VARCHAR(255),               -- 소셜 로그인 제공자의 고유 사용자 ID
  fcm_token        TEXT,                       -- Firebase FCM 디바이스 토큰
  device_platform  VARCHAR(10),               -- 'ios' | 'android'
  is_active        BOOLEAN DEFAULT true,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(auth_provider, provider_id),          -- 소셜 로그인 중복 방지
  UNIQUE(email)                                -- 이메일 중복 방지
);
```

### keywords 테이블

```sql
CREATE TABLE keywords (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  keyword         VARCHAR(100) NOT NULL,
  platforms       TEXT[] DEFAULT '{bunjang,joongna}',
                                               -- 알림 받을 플랫폼 (당근은 알림 없음)
  min_price       INTEGER,                     -- 최소 가격 필터 (NULL = 제한 없음)
  max_price       INTEGER,                     -- 최대 가격 필터 (NULL = 제한 없음)
  is_active       BOOLEAN DEFAULT true,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, keyword)
);
```

> **당근 제외 이유**: 당근은 지역 기반 검색 특성상 스케줄러 폴링이 불가능합니다. 사용자가 탭에서 직접 검색하는 방식으로만 사용합니다.

### notification_history 테이블

```sql
CREATE TABLE notification_history (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  keyword_id      UUID NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
  product_id      VARCHAR(100) NOT NULL,        -- 플랫폼 상품 ID
  platform        VARCHAR(20) NOT NULL,          -- 'bunjang' | 'joongna'
  title           TEXT NOT NULL,
  price           INTEGER,
  url             TEXT NOT NULL,
  image_url       TEXT,
  location        VARCHAR(100),
  sent_at         TIMESTAMPTZ DEFAULT NOW(),
  is_read         BOOLEAN DEFAULT false
);

CREATE INDEX idx_notification_user_sent ON notification_history(user_id, sent_at DESC);
CREATE INDEX idx_notification_keyword ON notification_history(keyword_id);
CREATE INDEX idx_notification_unread ON notification_history(user_id, is_read)
  WHERE is_read = false;
```

---

## 7. Redis 키 설계

### 중복 방지 (seen products)

```
Key:   seen:{platform}:{product_id}
Type:  String (존재 여부만 체크, 값 무의미)
TTL:   86400초 (24시간)
예:    seen:bunjang:123456789
예:    seen:joongna:87654321
```

### 사용자 키워드 캐시

```
Key:   active_keywords
Type:  String (JSON 직렬화된 전체 활성 키워드 배열)
TTL:   60초 (1분 주기 자동 갱신, DB 변경 시 즉시 invalidate)
```

### 신규 매물 메시지 큐 (Redis Stream)

```
Stream:  product_alerts
Fields:
  platform    = "bunjang" | "joongna"
  product_id  = "123456789"
  title       = "아이폰 15 Pro 256GB"
  price       = "1200000"
  url         = "https://m.bunjang.co.kr/products/123456789"
  image_url   = "https://media.bunjang.co.kr/..."
  location    = "강남구"
  time        = "2024-01-15T10:30:00"

Consumer Group: alert_consumer
Consumer Name:  fastapi-worker-1
```

---

## 8. 스케줄러 설계 (crawler/scheduler.py)

### 폴링 대상 및 주기

| 플랫폼 | 방식 | 주기 | 비고 |
|---|---|---|---|
| 번개장터 | 최신 매물 수집 (`within_minutes=1`) | **1분** | 19개 상위 카테고리 병렬 |
| 중고나라 | 최신 매물 수집 (`within_minutes=1`) | **1분** | 최상위 카테고리 병렬 |
| ~~당근~~ | ~~키워드 검색~~ | **제외** | 앱 탭에서 직접 검색 |

### 스케줄러 로직 (의사 코드)

```python
# scheduler.py (APScheduler)

@scheduler.scheduled_job('interval', minutes=1)
def poll_bunjang_and_joongna():
    # 1. Flask 크롤러 API 내부 호출
    bunjang_items = requests.get("http://localhost:5000/api/bunjang/recent",
                                 params={"within_minutes": 1}).json()["data"]
    joongna_items = requests.get("http://localhost:5000/api/joongna/recent",
                                 params={"within_minutes": 1}).json()["data"]

    # 2. Redis seen_ids로 중복 체크 후 신규만 추출
    new_items = []
    for item in bunjang_items + joongna_items:
        key = f"seen:{item['source']}:{item['id']}"
        if redis_client.set(key, 1, nx=True, ex=86400):  # NX: 없을 때만 SET
            new_items.append(item)

    # 3. Redis Stream에 신규 매물 발행
    for item in new_items:
        redis_client.xadd("product_alerts", {
            "platform":   item["source"],
            "product_id": item["id"],
            "title":      item["title"],
            "price":      str(item.get("price", 0)),
            "url":        item["url"],
            "image_url":  item.get("image_url", ""),
            "location":   item.get("location", ""),
            "time":       item.get("time", ""),
        })
```

### 에러 처리 전략

- 스크래퍼 실패 시 해당 플랫폼 건너뛰고 다음 실행 대기 (서비스 중단 없음)
- Redis 연결 실패 시 해당 실행 skip 후 다음 주기 재시도
- 요청 타임아웃: 각 플랫폼 15초, 전체 폴링 목표 30초 이내 완료
- 연속 실패 카운터: 5회 연속 실패 시 stderr 로그 출력

---

## 9. FastAPI 백엔드 API 명세

### 인증 (Auth)

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| POST | `/auth/register` | 불필요 | 자체 회원가입 (이메일 + 비밀번호 + 닉네임) |
| POST | `/auth/login` | 불필요 | 자체 로그인 → JWT 발급 |
| POST | `/auth/refresh` | 불필요 | JWT 갱신 |
| GET | `/auth/social/{provider}` | 불필요 | 소셜 로그인 OAuth URL 반환 (`naver` \| `kakao` \| `google`) |
| POST | `/auth/social/{provider}/callback` | 불필요 | 소셜 OAuth code 교환 → JWT 발급 |
| PATCH | `/auth/fcm-token` | **필요** | FCM 토큰 업데이트 |

**소셜 로그인 흐름:**
```
앱 → GET /auth/social/kakao → { "auth_url": "https://kauth.kakao.com/oauth/..." }
앱 → InAppWebView에서 OAuth 진행 → code 수신
앱 → POST /auth/social/kakao/callback { "code": "..." } → { "access_token": "...", "user": {...} }
```

**자체 로그인 Request/Response:**
```json
// POST /auth/login
Request:  { "email": "user@example.com", "password": "password123" }
Response: { "access_token": "eyJ...", "token_type": "bearer", "user": { "id": "...", "nickname": "..." } }
```

### 키워드 관리 (Keywords) — 인증 필요

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/keywords` | 내 키워드 목록 조회 |
| POST | `/keywords` | 키워드 등록 |
| PATCH | `/keywords/{id}` | 키워드 수정 (가격범위, 플랫폼 설정) |
| DELETE | `/keywords/{id}` | 키워드 삭제 |
| PATCH | `/keywords/{id}/toggle` | 활성/비활성 토글 |

**키워드 등록 Request Body:**
```json
{
  "keyword": "아이폰 15",
  "platforms": ["bunjang", "joongna"],
  "min_price": 500000,
  "max_price": 1500000
}
```

### 알림 이력 (Notifications) — 인증 필요

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/notifications` | 내 알림 이력 (최신순, cursor 기반 페이지네이션) |
| PATCH | `/notifications/{id}/read` | 단건 읽음 처리 |
| POST | `/notifications/read-all` | 전체 읽음 처리 |
| DELETE | `/notifications` | 전체 알림 삭제 |
| GET | `/notifications/unread-count` | 읽지 않은 알림 건수 |

### 검색 프록시 (Search) — 인증 불필요 (비로그인 허용)

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/search/bunjang` | 번개장터 검색 (크롤러 API 중계) |
| GET | `/search/joongna` | 중고나라 검색 (크롤러 API 중계) |
| GET | `/search/daangn` | 당근 동 레벨 직접 검색 |
| GET | `/search/daangn/district` | 당근 구/군 레벨 검색 (하위 동 전체 병렬) |
| GET | `/search/all` | 번개장터 + 중고나라 통합 검색 |
| GET | `/search/daangn/regions` | 당근 지역 자동완성 검색 |
| GET | `/search/daangn/districts` | 구/군 목록 조회 (탭1 지역 선택용) |

**당근 구/군 레벨 검색 파라미터:**
```
GET /search/daangn/district?keyword=아이폰&district=강남구-10

동작:
  1. daangn_regions.py에서 강남구(강남구-10) 하위 모든 동 목록 조회
     예: [역삼동-360, 논현동-123, 개포동-456, 대치동-789, ...]
  2. ThreadPoolExecutor로 각 동에서 병렬 검색 실행
  3. 결과 합산 + 상품 ID 기준 중복 제거
  4. 최신순 정렬 후 반환
```

**공통 쿼리 파라미터:**
```
keyword     (필수) 검색어
page        (선택) 페이지 번호, 기본 1
count       (선택) 결과 수, 기본 20, 최대 100
min_price   (선택) 최소 가격
max_price   (선택) 최대 가격
sort        (선택) recommend | recent | price_asc | price_desc
```

### Redis Stream Consumer (FastAPI 백그라운드 태스크)

```python
# services/alert_consumer.py

async def run_alert_consumer():
    """FastAPI startup 시 asyncio 태스크로 실행"""
    while True:
        messages = redis.xreadgroup(
            groupname="alert_consumer",
            consumername="fastapi-worker-1",
            streams={"product_alerts": ">"},
            count=100,
            block=5000,  # 5초 대기
        )

        for stream, entries in (messages or []):
            for entry_id, fields in entries:
                await process_alert(fields)
                redis.xack("product_alerts", "alert_consumer", entry_id)

async def process_alert(product: dict):
    # 1. 활성 키워드 전체 로드 (Redis 캐시 우선)
    keywords = await get_active_keywords_cached()

    # 2. 키워드 매칭: 번개장터/중고나라 플랫폼 포함 + 제목 부분 일치 + 가격 범위
    matched_users: dict[str, list] = {}  # user_id → matched keywords
    for kw in keywords:
        if product["platform"] not in kw["platforms"]:
            continue
        if kw["keyword"] not in product["title"]:
            continue
        if kw["min_price"] and int(product["price"]) < kw["min_price"]:
            continue
        if kw["max_price"] and int(product["price"]) > kw["max_price"]:
            continue
        matched_users.setdefault(kw["user_id"], []).append(kw)

    # 3. 매칭된 사용자별 알림 이력 저장 + FCM 발송
    for user_id, kws in matched_users.items():
        await save_notification_history(user_id, kws[0], product)
        unread_count = await get_unread_count(user_id)
        await send_fcm_notification(user_id, unread_count)
```

---

## 10. 키워드 매칭 로직

### 매칭 규칙 (번개장터·중고나라만)

```
[번개장터 / 중고나라 - 1분 폴링 방식]
  신규 매물 감지 → 전체 활성 키워드와 대조

[공통 필터 (AND 조건)]
  1. 플랫폼 포함 여부: keyword.platforms에 product.platform 포함
  2. 키워드 부분 일치: keyword.keyword in product.title (대소문자 무시)
  3. 최소 가격: keyword.min_price is NULL OR product.price >= min_price
  4. 최대 가격: keyword.max_price is NULL OR product.price <= max_price
  5. 판매 상태: product.status in ('판매중', '예약중')  -- 판매완료 제외
```

### 중복 알림 방지 (2단계)

```
Level 1: Redis seen_ids (24시간 TTL)
  → 같은 상품 ID가 다음 폴링에서 재수집되는 것 방지

Level 2: notification_history DB unique 체크
  → (user_id, product_id, platform) 조합으로 이미 발송된 알림 재발송 방지
```

---

## 11. FCM 알림 설계

### 알림 방식: 건수 집약형

- 개별 매물 정보가 아닌 **미읽음 건수**만 발송합니다.
- 이전에 읽지 않은 알림이 있는 상태에서 새 매물이 매칭되면 **누적 건수**로 발송합니다.

**FCM 페이로드 구조:**
```json
{
  "token": "{user_fcm_token}",
  "notification": {
    "title": "새 매물 알림",
    "body": "신규 알림이 총 3건 있습니다."
  },
  "data": {
    "unread_count": "3",
    "type": "keyword_alert"
  },
  "android": {
    "priority": "high",
    "notification": {
      "channel_id": "keyword_alerts",
      "notification_count": 3
    }
  },
  "apns": {
    "headers": { "apns-priority": "10" },
    "payload": {
      "aps": {
        "badge": 3,
        "sound": "default"
      }
    }
  }
}
```

**발송 로직:**
```python
async def send_fcm_notification(user_id: str, unread_count: int):
    user = await get_user(user_id)
    if not user.fcm_token:
        return

    message = messaging.Message(
        token=user.fcm_token,
        notification=messaging.Notification(
            title="새 매물 알림",
            body=f"신규 알림이 총 {unread_count}건 있습니다.",
        ),
        data={"unread_count": str(unread_count), "type": "keyword_alert"},
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                channel_id="keyword_alerts",
                notification_count=unread_count,
            ),
        ),
        apns=messaging.APNSConfig(
            headers={"apns-priority": "10"},
            payload=messaging.APNSPayload(
                aps=messaging.Aps(badge=unread_count, sound="default"),
            ),
        ),
    )
    firebase_admin.messaging.send(message)
```

### Firebase Admin SDK 설정 (Python)

```python
import firebase_admin
from firebase_admin import credentials, messaging

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
```

- Android: `google-services.json` → Flutter `android/app/` 에 배치
- iOS: `GoogleService-Info.plist` → Flutter `ios/Runner/` 에 배치
- 서버: `serviceAccountKey.json` → `backend/` 루트에 배치 (`.gitignore` 필수)

---

## 12. Flutter 앱 화면 명세

### 탭 구성 (4개 탭 BottomNavigationBar)

```
BottomNavigationBar
 ├── 탭1: 🥕 당근 검색     — 구/군 지역 선택 + 하위 동 전체 병렬 검색
 ├── 탭2: 🔍 매물 검색     — 번개장터 + 중고나라 통합 검색
 ├── 탭3: 🔔 알림 이력     — FCM 수신 내역 목록 (로그인 필요)
 └── 탭4: ⚙️ 설정        — 비로그인: 로그인 화면 / 로그인: 설정·키워드 관리
```

> **탭1, 탭2 검색은 비로그인 상태에서도 사용 가능합니다.**

---

### 탭1: 당근 검색

**지역 선택 UI:**
- 시/도 선택 드롭다운 (예: 서울특별시)
- 구/군 선택 드롭다운 (예: 강남구) — depth=2 레벨
- 선택 후 `GET /search/daangn/districts?city=서울특별시` 로 구/군 목록 로드

**검색 동작:**
- 키워드 입력 + 검색 버튼 → `GET /search/daangn/district?keyword=아이폰&district=강남구-10`
- 백엔드에서 강남구 하위 모든 동(역삼동, 논현동, 개포동 등) 자동 병렬 검색
- 중복 제거 후 통합 결과 반환
- 결과: 상품 카드 리스트 (썸네일 / 제목 / 가격 / 동 지역 / 등록시간)
- 카드 탭 → 당근 앱 딥링크 (`karrot://`) / 앱 없으면 당근 모바일 웹 오픈
- 가격 범위 필터 지원 (선택)

---

### 탭2: 매물 검색 (번개장터 + 중고나라)

- 플랫폼 선택 토글: `[번개장터]` `[중고나라]` `[통합]`
- 검색창 + 검색 버튼
- 가격 범위 필터 (선택)
- 정렬 선택: 최신순 / 추천순 / 낮은가격 / 높은가격
- 결과: 상품 카드 리스트 (썸네일 / 제목 / 가격 / 지역 / 플랫폼 뱃지 / 등록시간)
- 카드 탭 → 각 플랫폼 앱 딥링크 / 앱 없으면 모바일 웹 오픈
  - 번개장터: `bunjang://products/{id}` → `https://m.bunjang.co.kr/products/{id}`
  - 중고나라: `joonggonara://product/{id}` → `https://web.joongna.com/product/{id}`
- Pull-to-refresh 지원

---

### 탭3: 알림 이력 (로그인 필요)

- 비로그인: "알림을 받으려면 로그인이 필요합니다" + 로그인 버튼
- 로그인 상태:
  - FCM으로 수신된 매물 알림 목록 (최신순, 무한 스크롤)
  - 각 항목: 플랫폼 뱃지 / 매물 제목 / 가격 / 매칭 키워드 / 수신 시각 / 읽음 여부
  - 읽지 않은 항목: 배경색 강조 표시
  - 날짜별 섹션 헤더 그룹핑
  - 항목 탭 → 읽음 처리 + 해당 플랫폼 앱 딥링크 / 앱 없으면 모바일 웹 오픈
  - 우측 상단: 전체 읽음 처리 버튼
  - BottomNavigationBar 탭 뱃지: 읽지 않은 알림 건수 표시

---

### 탭4: 설정

**비로그인 상태:**
- "로그인이 필요합니다" 안내 문구
- [로그인 / 회원가입] 버튼 → 로그인 화면으로 이동

**로그인 상태:**

| 섹션 | 항목 | 설명 |
|---|---|---|
| 계정 | 닉네임 / 이메일 표시 | |
| 알림 키워드 | [키워드 관리] 버튼 | 키워드 목록 화면으로 이동 |
| 알림 설정 | 알림 수신 ON/OFF 전체 토글 | |
| | 방해금지 시간대 | 예: 23:00 ~ 08:00 |
| | 진동 / 사운드 설정 | |
| 기타 | 앱 버전 | |
| | 로그아웃 버튼 | |
| | 회원 탈퇴 버튼 | |

---

### 로그인 화면 (Login Screen)

```
[소셜 로그인]
  ┌──────────────────────────────────┐
  │  N  네이버로 로그인               │
  └──────────────────────────────────┘
  ┌──────────────────────────────────┐
  │  K  카카오로 로그인               │
  └──────────────────────────────────┘
  ┌──────────────────────────────────┐
  │  G  Google로 로그인              │
  └──────────────────────────────────┘

─────── 또는 ───────

[자체 로그인]
  이메일: [________________]
  비밀번호: [________________]
  [로그인]

  계정이 없으신가요? → [회원가입]
```

---

### 키워드 관리 화면

- 등록된 키워드 카드 목록
- 각 카드: 키워드명 / 플랫폼 뱃지(번개장터, 중고나라) / 가격 범위 / 활성 토글
- 스와이프 왼쪽 → 삭제 버튼 표시
- 카드 탭 → 수정 화면
- 우측 하단 FAB `+` → 키워드 추가 화면

**키워드 추가/수정 입력 항목:**
```
키워드 입력 (필수)        예: 아이폰 15
플랫폼 선택 (다중)        ☑ 번개장터  ☑ 중고나라
최소 가격 (선택)          예: 500,000원
최대 가격 (선택)          예: 1,500,000원
```

> **키워드 제한**: 사용자당 최대 10개 등록 가능 (서버 부하 방지)

---

## 13. 소셜 로그인 구현 상세

### 지원 소셜 로그인 제공자

| 제공자 | OAuth2 인가 URL | 필요 설정 |
|---|---|---|
| 네이버 | `https://nid.naver.com/oauth2.0/authorize` | 네이버 개발자센터 앱 등록, Client ID/Secret |
| 카카오 | `https://kauth.kakao.com/oauth/authorize` | 카카오 개발자센터 앱 등록, REST API 키 |
| 구글 | `https://accounts.google.com/o/oauth2/auth` | Google Cloud Console OAuth2 클라이언트 |

### FastAPI 소셜 OAuth 흐름

```python
# routers/auth.py

@router.get("/social/{provider}")
async def social_login_url(provider: str):
    """소셜 로그인 URL 생성 후 앱에 반환"""
    urls = {
        "naver":  build_naver_auth_url(),
        "kakao":  build_kakao_auth_url(),
        "google": build_google_auth_url(),
    }
    return {"auth_url": urls[provider]}


@router.post("/social/{provider}/callback")
async def social_login_callback(provider: str, body: SocialCallbackSchema, db: Session):
    """소셜 code → 제공자 access_token 교환 → 사용자 조회/생성 → 우리 JWT 발급"""
    user_info = await exchange_code_for_user_info(provider, body.code)

    user = db.query(User).filter_by(
        auth_provider=provider,
        provider_id=user_info["provider_id"]
    ).first()

    if not user:
        user = create_user(db, auth_provider=provider, **user_info)

    access_token = create_jwt_token(user.id)
    return {"access_token": access_token, "user": user}
```

---

## 14. 환경 변수

### crawler/.env

```env
# Flask 서버
FLASK_HOST=0.0.0.0
FLASK_PORT=5000

# Redis
REDIS_URL=redis://localhost:6379/0

# Scraper 설정
CRAWLER_DELAY=0.5
BUNJANG_POLL_INTERVAL_MINUTES=1
JOONGNA_POLL_INTERVAL_MINUTES=1
```

### backend/.env

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/secondhand_alert

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_SECRET=your-secret-key-here
JWT_EXPIRES_IN_DAYS=30

# Firebase FCM
FIREBASE_SERVICE_ACCOUNT_PATH=serviceAccountKey.json

# Crawler API (내부 통신)
CRAWLER_API_URL=http://localhost:5000

# 서버
PORT=8000
ENV=development

# 소셜 로그인 - 네이버
NAVER_CLIENT_ID=your-naver-client-id
NAVER_CLIENT_SECRET=your-naver-client-secret
NAVER_REDIRECT_URI=http://localhost:8000/auth/social/naver/callback

# 소셜 로그인 - 카카오
KAKAO_CLIENT_ID=your-kakao-rest-api-key
KAKAO_REDIRECT_URI=http://localhost:8000/auth/social/kakao/callback

# 소셜 로그인 - 구글
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/social/google/callback
```

### mobile/.env

```env
API_BASE_URL=http://localhost:8000
```

---

## 15. Docker Compose 구성 (로컬 개발)

```yaml
# docker-compose.yml
version: '3.8'
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: secondhand_alert
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

---

## 16. 개발 순서 (구현 우선순위)

### Phase 1: 인프라 + 크롤러

1. `docker-compose.yml` 작성 → PostgreSQL + Redis 로컬 환경 구성
2. `crawler/` 전체 작성
   - `scrapers/bunjang_scraper.py` — 번개장터 스크래퍼 (알림 폴링: 카테고리 병렬 / 앱 검색: 키워드)
   - `scrapers/daangn_scraper.py` — 당근 스크래퍼 (동 레벨 검색)
   - `scrapers/joongna_scraper.py` — 중고나라 스크래퍼 (알림 폴링: 카테고리 병렬 / 앱 검색: 키워드)
   - `data/daangn_regions.py` — 지역 코드 + 구/군별 하위 동 목록
   - `server.py` — Flask REST API (구/군 병렬 검색 엔드포인트 포함)
   - `redis_client.py` — Redis Stream 발행
   - `scheduler.py` — APScheduler 1분 폴링 (번개장터+중고나라만)

### Phase 2: FastAPI 백엔드 기초

3. FastAPI 프로젝트 초기화
4. SQLAlchemy 모델 정의 + Alembic 마이그레이션
5. Auth API: 자체 로그인/회원가입 + JWT
6. Auth API: 소셜 로그인 (네이버, 카카오, 구글)
7. Keywords CRUD API (인증 필요)
8. Notifications 이력 API (인증 필요)
9. Search 프록시 API (인증 불필요 — 비로그인 허용)

### Phase 3: 알림 파이프라인

10. Redis Stream Consumer 백그라운드 태스크 구현
11. 키워드 매칭 로직 구현
12. FCM Admin SDK 연동 (건수 집약형 발송)
13. 중복 알림 방지 로직 (2단계)

### Phase 4: Flutter 앱

14. Flutter 프로젝트 초기화 (Riverpod, GoRouter, Dio, freezed, url_launcher)
15. FCM 플러그인 설정 (firebase_messaging)
16. `deep_link_service.dart` — 앱 딥링크 + 모바일 웹 폴백
17. BottomNavigationBar 4탭 구조
18. 탭1: 당근 검색 (시/도 → 구/군 선택 → 하위 동 전체 검색)
19. 탭2: 번개장터+중고나라 통합 검색
20. 탭3: 알림 이력 (비로그인 안내 처리 포함)
21. 탭4: 설정 + 로그인/회원가입 (자체 + 소셜)
22. 키워드 관리 화면
23. Android `AndroidManifest.xml` + iOS `Info.plist` 딥링크 쿼리 등록

### Phase 5: 최적화 + 출시 준비

24. 방해금지 시간대 로직 (FCM 발송 전 시간 체크)
25. FCM 토큰 만료 처리 (unregistered 오류 시 토큰 삭제)
26. 에러 모니터링 (Sentry)
27. 프로덕션 배포 (Docker + Railway/GCP)
28. iOS/Android 스토어 배포 준비

---

## 17. 플랫폼별 기술적 제약 및 주의사항

### 번개장터

- API 호출 간격: 최소 0.5초 delay 유지
- 카테고리당 최대 100개 상품 수집 (`n` 파라미터)
- `update_time` 필드: Unix timestamp → ISO 8601 변환 필요
- 이미지 URL 리사이즈 파라미터(`?xxx=NxN`) 포함 시 원본 URL로 정규화
- HTTP 헤더 필수: `Origin: https://m.bunjang.co.kr` (CORS 우회)
- 앱 딥링크: `bunjang://products/{id}` (iOS `LSApplicationQueriesSchemes`에 `bunjang` 등록 필요)

### 당근 (탭 직접 검색 전용)

- **스케줄러 폴링 없음** — 앱 탭에서 사용자가 직접 검색할 때만 호출
- **구/군 레벨 검색**: 선택된 구/군의 모든 동(depth=3)에 대해 병렬 검색 → 중복 제거
  - 강남구 하위 동 수: 20~30개 수준 → ThreadPoolExecutor(max_workers=10) 권장
- `window.__remixContext` JSON 탐색 경로:
  `state.loaderData["routes/kr.buy-sell.s.allPage"].fleamarketArticles`
- 상품 ID가 URL 경로 형식(`/kr/buy-sell/abc123`)으로 오므로 파싱 주의
- 목록 페이지에서 판매자 닉네임·조회수·찜수 제공 안 됨
- 앱 딥링크: `karrot://articles/{id}` (iOS `LSApplicationQueriesSchemes`에 `karrot` 등록 필요)

### 중고나라

- **내부 검색 API 직접 호출 불가** (`search-api.joongna.com` 차단) → HTML 우회 필수
- **앱 검색 시 카테고리 병렬 처리 없음** — 키워드 직접 검색만 사용
- **알림 폴링 시에만** 최상위 카테고리 병렬 수집 사용
- `__NEXT_DATA__` 탐색: `props.pageProps.dehydratedState.queries[]`에서
  `queryKey[0] == "get-search-products"` 항목 우선 탐색
- `saleYn=ALL` 파라미터로 판매완료 포함/제외 제어
- User-Agent 고정 필수 (Chrome 131)
- 앱 딥링크: `joonggonara://product/{id}` (실제 스킴 확인 필요, 미확인 시 웹으로만 처리)

---

## 18. 미결정 사항 (코딩 전 결정 필요)

| 항목 | 옵션 A | 옵션 B | 현재 결정/권장 |
|---|---|---|---|
| **소셜 로그인 Redirect URI** | 앱 딥링크 스킴 (`myapp://callback`) | FastAPI 서버 URL | 앱 딥링크 권장 |
| **키워드 최대 개수** | 사용자당 10개 | 20개 | **10개** (서버 부하) |
| **알림 이력 보존 기간** | 30일 자동 삭제 | 무제한 | **30일** (비용 절감) |
| **스케줄러 실행 방식** | APScheduler (Flask 내장) | 별도 프로세스 | **APScheduler** (단순함) |
| **방해금지 시간대 기본값** | 23:00~08:00 | 사용자 설정만 | **23:00~08:00 기본** |
| **회원탈퇴 처리** | Soft delete (is_active=false) | Hard delete | **Soft delete** |
| **중고나라 앱 딥링크 스킴** | `joonggonara://product/{id}` | 확인 불가 시 웹만 | 실제 스킴 확인 후 결정 |
| **당근 구/군 병렬 workers** | 10 | 5 | **10** (동 수 많음) |

---

## 19. 추가로 필요한 정보 (현재 미확보)

코딩 시작 전 또는 진행 중 확인·설정이 필요한 항목입니다.

1. **앱 이름 / 패키지명** — Flutter 초기화 시 필요 (`com.xxx.앱이름`)
2. **Firebase 프로젝트** — 생성 및 `google-services.json`, `GoogleService-Info.plist` 발급
3. **네이버 개발자센터** — 앱 등록, Client ID/Secret, Redirect URI 설정
4. **카카오 개발자센터** — 앱 등록, REST API 키, Redirect URI 설정
5. **Google Cloud Console** — OAuth2 클라이언트 생성, Client ID/Secret 발급
6. **iOS 개발자 계정** — Apple Push Notification (APNs) 인증서 설정
7. **중고나라 앱 딥링크 스킴** — 실제 `joonggonara://` 스킴 동작 여부 확인 필요
8. **프로덕션 배포 환경** — Railway / GCP / AWS 결정
9. **번개장터 Rate Limit** — 분당 최대 요청 수 공식 문서 없음, 실험적 파악 필요
10. **중고나라 HTML 구조 변경 모니터링** — `__NEXT_DATA__` 경로가 배포마다 변경 가능성 있음
