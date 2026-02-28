# 개발 환경 시작

개발 서버를 순서대로 실행하라.

## 실행 순서

### 1단계: 인프라 (PostgreSQL + Redis)

```bash
# projectYO 루트에서
docker-compose up -d postgres redis

# 상태 확인
docker-compose ps
# postgres, redis 모두 Up 상태여야 함
```

### 2단계: 크롤러 서버 (Flask + APScheduler)

```bash
cd crawler

# 가상환경 활성화 (없으면 생성)
python -m venv venv
source venv/bin/activate       # macOS/Linux
# venv\Scripts\activate        # Windows

# 의존성 설치
pip install -r requirements.txt

# 크롤러 서버 실행 (포트 5000)
python server.py
```

> **확인**: `http://localhost:5000/` 접근 시 API 엔드포인트 목록 JSON 반환

### 3단계: FastAPI 백엔드

```bash
cd backend

# 가상환경 활성화
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# DB 마이그레이션 확인
alembic current
# → 최신 revision이 표시돼야 함 (안 되면 alembic upgrade head)

# 백엔드 실행 (포트 8000)
uvicorn app.main:app --reload --port 8000
```

> **확인**: `http://localhost:8000/docs` 에서 Swagger UI 접근 가능

### 4단계: Flutter 앱

```bash
cd mobile

# 의존성 설치
flutter pub get

# 코드 생성 (freezed, riverpod_annotation)
dart run build_runner build --delete-conflicting-outputs

# iOS 시뮬레이터 또는 Android 에뮬레이터 실행
flutter run
```

## 빠른 시작 (전체 한 번에)

```bash
# 터미널 4개 열어서 각각 실행

# T1: 인프라
docker-compose up -d postgres redis

# T2: 크롤러
cd crawler && source venv/bin/activate && python server.py

# T3: 백엔드
cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000

# T4: Flutter
cd mobile && flutter run
```

## 서비스 포트 정리

| 서비스 | 포트 | 비고 |
|---|---|---|
| Flask 크롤러 | 5000 | 검색·수집 API |
| FastAPI 백엔드 | 8000 | 사용자·키워드·알림 API |
| PostgreSQL | 5432 | 사용자/키워드/알림 이력 DB |
| Redis | 6379 | seen_ids + Stream 큐 |

## 종료

```bash
# 크롤러/백엔드: Ctrl+C

# 인프라 중지 (데이터 보존)
docker-compose stop

# 인프라 완전 삭제 (데이터 포함)
docker-compose down -v
```

## 자주 발생하는 문제

- **`Connection refused :5432`**: `docker-compose up -d postgres` 먼저 실행
- **`Connection refused :6379`**: `docker-compose up -d redis` 먼저 실행
- **`Module not found`**: 가상환경 활성화 확인 (`source venv/bin/activate`)
- **`alembic: command not found`**: `pip install alembic` 또는 가상환경 재확인
- **Flutter 빌드 오류**: `dart run build_runner build --delete-conflicting-outputs` 재실행
