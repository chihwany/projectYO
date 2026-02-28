# 소셜 로그인 제공자 추가

`$ARGUMENTS` 소셜 로그인을 구현하라. 지원 값: `naver` | `kakao` | `google`

## 수정할 파일 (4개)

1. `backend/app/routers/auth.py` — OAuth 엔드포인트 추가
2. `backend/app/services/auth_service.py` — 토큰 교환 로직 추가
3. `backend/app/core/config.py` — 환경변수 필드 추가
4. `.env.example` — 새 환경변수 키 추가

## OAuth 흐름 (앱 ↔ 서버)

```
앱: GET /auth/social/{provider}
  → 서버: OAuth 인가 URL 생성 후 반환
  → 앱: InAppWebView 또는 외부 브라우저로 열기
  → 소셜 로그인 완료 → 앱 딥링크로 code 수신
앱: POST /auth/social/{provider}/callback  { "code": "..." }
  → 서버: code로 소셜 access_token 교환
  → 서버: 사용자 정보 조회 (이메일, 닉네임, provider_id)
  → 서버: users 테이블 조회/생성 (auth_provider + provider_id)
  → 서버: 우리 JWT 발급 후 반환
```

## 제공자별 OAuth 엔드포인트

| 제공자 | 인가 URL | 토큰 URL | 사용자 정보 URL |
|---|---|---|---|
| 네이버 | `https://nid.naver.com/oauth2.0/authorize` | `https://nid.naver.com/oauth2.0/token` | `https://openapi.naver.com/v1/nid/me` |
| 카카오 | `https://kauth.kakao.com/oauth/authorize` | `https://kauth.kakao.com/oauth/token` | `https://kapi.kakao.com/v2/user/me` |
| 구글 | `https://accounts.google.com/o/oauth2/auth` | `https://oauth2.googleapis.com/token` | `https://www.googleapis.com/oauth2/v2/userinfo` |

## 라우터 엔드포인트 구조

```python
@router.get("/social/{provider}")
async def get_social_login_url(provider: str):
    """소셜 로그인 인가 URL 반환 — 인증 불필요"""
    if provider not in ("naver", "kakao", "google"):
        raise HTTPException(status_code=400, detail="지원하지 않는 소셜 로그인입니다.")
    url = auth_service.build_oauth_url(provider)
    return {"auth_url": url}

@router.post("/social/{provider}/callback")
async def social_login_callback(
    provider: str,
    body: SocialCallbackRequest,
    db: Session = Depends(get_db),
):
    """소셜 code 교환 → JWT 발급 — 인증 불필요"""
    user_info = await auth_service.exchange_code(provider, body.code)
    user = auth_service.get_or_create_social_user(db, provider, user_info)
    token = security.create_access_token(str(user.id))
    return {"access_token": token, "token_type": "bearer", "user": UserResponse.model_validate(user)}
```

## DB 사용자 조회/생성 로직

```python
# users 테이블: auth_provider + provider_id 조합으로 식별
user = db.query(User).filter_by(
    auth_provider=provider,
    provider_id=user_info["provider_id"]
).first()

if not user:
    user = User(
        auth_provider=provider,
        provider_id=user_info["provider_id"],
        email=user_info.get("email"),
        nickname=user_info.get("nickname", "사용자"),
        password_hash=None,  # 소셜 로그인은 비밀번호 없음
    )
    db.add(user)
    db.commit()
    db.refresh(user)
```

## 환경변수 (config.py에 추가)

```python
# 네이버
NAVER_CLIENT_ID: str = ""
NAVER_CLIENT_SECRET: str = ""
NAVER_REDIRECT_URI: str = "http://localhost:8000/auth/social/naver/callback"

# 카카오
KAKAO_CLIENT_ID: str = ""
KAKAO_REDIRECT_URI: str = "http://localhost:8000/auth/social/kakao/callback"

# 구글
GOOGLE_CLIENT_ID: str = ""
GOOGLE_CLIENT_SECRET: str = ""
GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/social/google/callback"
```

## Flutter 측 처리

소셜 로그인은 `login_screen.dart`에서:
```dart
// 1. 서버에서 인가 URL 받기
final url = await ref.read(apiServiceProvider).getSocialLoginUrl(provider);

// 2. 앱 내 WebView 또는 외부 브라우저로 열기
await launchUrl(Uri.parse(url));

// 3. 딥링크로 code 수신 후 서버에 전달
// (deep_link_service.dart에서 URI scheme 처리)
final result = await ref.read(apiServiceProvider).socialCallback(provider, code);
```
