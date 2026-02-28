# plan.md 컨벤션 체크

`$ARGUMENTS` 파일(또는 최근 작성한 코드)이 `docs/plan.md`의 설계 규칙을 준수하는지 검토하라.

## 체크리스트

### 스크래퍼 (crawler/scrapers/)

- [ ] **표준 스키마 10개 필드** 모두 반환: `id, title, price, price_str, image_url, status, location, time, url, source`
- [ ] `price`는 `int` (파싱 실패 시 `0`), `price_str`은 `"1,200,000원"` 형식
- [ ] `time`은 ISO 8601 형식 (`"2024-01-15T10:30:00"`)
- [ ] `status`는 `"판매중" | "예약중" | "판매완료"` 중 하나
- [ ] User-Agent: `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36`
- [ ] 요청 딜레이: `time.sleep(self.delay)` (기본 0.5초 이상)
- [ ] 요청 타임아웃: `requests.get(..., timeout=15)`
- [ ] **카테고리 병렬 처리** = 알림 폴링 시에만. 앱 검색에서는 단순 키워드 검색
- [ ] `source` 필드: `"bunjang" | "daangn" | "joongna"` 중 정확한 값

### Flask 서버 (crawler/server.py)

- [ ] 성공 응답: `_success(data)` 또는 `_success(data, count=..., source=...)` 사용
- [ ] 실패 응답: `_error("메시지", 상태코드)` 사용 (직접 `jsonify` 사용 금지)
- [ ] 새 엔드포인트는 `index()` 함수의 `endpoints` 딕셔너리에도 등록

### FastAPI 백엔드 (backend/)

- [ ] **검색 API** (`/search/*`): 인증 불필요 — `Depends(get_current_user)` 없어야 함
- [ ] **키워드 관리** (`/keywords/*`): JWT 인증 필수 — `Depends(get_current_user)` 있어야 함
- [ ] **알림 이력** (`/notifications/*`): JWT 인증 필수
- [ ] **FCM 토큰** (`PATCH /auth/fcm-token`): JWT 인증 필수
- [ ] 응답 스키마: Pydantic v2 모델 사용 (`BaseModel`, `model_validate` 등)
- [ ] DB 모델: UUID PK (`default=uuid4`), TIMESTAMPTZ, `is_active` soft delete

### FCM 알림

- [ ] 알림 메시지: **"신규 알림이 총 N건 있습니다."** 형식만 사용
- [ ] Badge: 읽지 않은 누적 건수 (`unread_count`)
- [ ] 개별 상품 정보가 알림 본문에 직접 노출되지 않아야 함

### Flutter (mobile/lib/)

- [ ] 상품 카드 탭: `deep_link_service.dart`의 `openProduct()` 호출 (직접 URL 열기 금지)
- [ ] API 호출: `api_service.dart` 경유 (직접 `Dio` 호출 금지)
- [ ] 상태관리: `AsyncNotifierProvider` 패턴 (`StateProvider` 직접 사용 지양)
- [ ] 생성 코드(`*.g.dart`, `*.freezed.dart`)를 직접 편집하지 않음

### 당근 지역 검색

- [ ] 구/군 레벨 선택 시 하위 동 전체 병렬 검색 (`district-search` 엔드포인트 사용)
- [ ] 중복 제거: 상품 ID 기준 `seen_ids` set 사용
- [ ] 결과 정렬: 최신순 (`time` 기준 내림차순)

## 체크 방법

```bash
# 특정 파일 리뷰
/check-plan crawler/scrapers/joongna_scraper.py

# 특정 기능 리뷰
/check-plan FastAPI /keywords 라우터 구현

# 최근 작업 전체 리뷰
/check-plan
```

## 위반 시 처리

각 항목을 확인한 뒤:
1. ✅ 준수: 통과 표시
2. ❌ 위반: 어떤 규칙을 위반했는지 구체적으로 지적하고 수정 방법 제시
3. ⚠️ 불확실: 파일을 읽어서 직접 확인

체크 완료 후 위반 항목이 있으면 자동으로 수정하라.
