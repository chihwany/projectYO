# 바이브 코딩 시작 전 사전 작업 체크리스트

---

## 완료된 항목

- [x] `docs/plan.md` — 전체 설계 문서 작성
- [x] `.claude/commands/` — 커스텀 스킬 11개 작성 (`/new-db-model`, `/new-fastapi-router` 등)
- [x] `.agents/skills/` — 외부 스킬 설치 (`fastapi-python`, `redis-development`, `web-scraping`, `flutter`, `push-notification-setup`)

---

## 🔴 필수 — 코딩 시작 전 반드시 결정/준비

### 앱 기본 정보

- [ ] **앱 이름 확정** — Flutter 프로젝트 초기화 시 사용 (`com.xxx.앱이름`)
- [ ] **패키지명 확정** — 한 번 정하면 스토어 배포 후 변경 불가

### Firebase 설정 (FCM 없으면 알림 파이프라인 테스트 불가)

- [ ] Firebase Console에서 프로젝트 생성
- [ ] Android 앱 등록 → `google-services.json` 다운로드 → `mobile/android/app/` 에 배치
- [ ] iOS 앱 등록 → `GoogleService-Info.plist` 다운로드 → `mobile/ios/Runner/` 에 배치
- [ ] 서버용 Service Account 생성 → `serviceAccountKey.json` 다운로드 → `backend/` 루트에 배치
- [ ] FCM API 활성화 확인

### 프로젝트 설정 파일

- [ ] **`docker-compose.yml`** 생성 (PostgreSQL 16 + Redis 7)
- [ ] **`crawler/.env`** 생성 (`.env.example` 기반)
- [ ] **`backend/.env`** 생성 (DB URL, JWT Secret, Firebase 경로 등)
- [ ] **`.gitignore`** 생성 — 아래 항목 반드시 포함
  ```
  .env
  serviceAccountKey.json
  *.pyc
  __pycache__/
  venv/
  .DS_Store
  *.g.dart
  *.freezed.dart
  ```

---

## 🟡 권장 — 소셜 로그인 개발 전까지는 미뤄도 OK

### 소셜 로그인 외부 서비스 등록

- [ ] **네이버 개발자센터** 앱 등록 → Client ID / Client Secret 발급
- [ ] **카카오 개발자센터** 앱 등록 → REST API 키 발급
- [ ] **Google Cloud Console** OAuth2 클라이언트 생성 → Client ID / Secret 발급
- [ ] 각 소셜 로그인 **Redirect URI 방식 결정** — 앱 딥링크 vs FastAPI 서버 URL
  - 권장: 앱 딥링크 스킴 (`myapp://callback`) — plan.md 섹션 18 참고

### iOS 관련

- [ ] Apple Developer 계정 확인 (APNs 인증서 설정용)

---

## 🟢 코딩 시작 직전에 확인

### 개발 환경 동작 확인

- [ ] Docker Desktop 실행 확인
- [ ] `docker compose up -d postgres redis` → 컨테이너 정상 기동 확인
- [ ] Python 3.11+ 설치 확인 (`python --version`)
- [ ] Flutter 3.x 설치 확인 (`flutter doctor`)
- [ ] Node.js 설치 확인 (`node --version`, npx skills 사용용)

### 디렉토리 초기화

- [ ] `crawler/`, `backend/`, `mobile/` 폴더 생성
- [ ] Flutter 프로젝트 초기화 (`flutter create mobile --org com.xxx`)
- [ ] FastAPI 프로젝트 `backend/venv` 생성 + `requirements.txt` 준비
- [ ] Alembic 초기화 (`cd backend && alembic init alembic`)

---

## 우선순위 순서

```
1. 앱 이름 / 패키지명 결정
2. Firebase 프로젝트 생성 + 설정 파일 3개 다운로드
3. .gitignore + docker-compose.yml + .env 파일 준비
4. Docker로 인프라 실행 확인 (postgres + redis)
5. Flutter / Python 환경 확인 (flutter doctor, python --version)
── 이후 Phase 1 크롤러 코딩 시작 ──
6. (Phase 2~3 진행 중) 소셜 로그인 외부 서비스 등록
```

> **가장 막히는 구간**: Firebase 설정과 앱 패키지명. 이 두 가지가 결정되면 코딩 바로 시작 가능.
