# 새 FastAPI 라우터 생성

`$ARGUMENTS` 기능의 라우터, 스키마, 서비스 파일을 생성하라.

## 생성할 파일 (3개)

1. `backend/app/routers/{name}.py` — APIRouter + 엔드포인트 정의
2. `backend/app/schemas/{name}.py` — 요청/응답 Pydantic v2 스키마
3. `backend/app/services/{name}_service.py` — 비즈니스 로직

## ⚠️ 인증 정책 (반드시 준수)

| 경로 | 인증 여부 | 처리 방법 |
|---|---|---|
| `/search/*` | **불필요** — 비로그인 허용 | `Depends()` 없음 |
| `/keywords/*` | **필요** — JWT 필수 | `user = Depends(get_current_user)` |
| `/notifications/*` | **필요** — JWT 필수 | `user = Depends(get_current_user)` |
| `/auth/register`, `/auth/login` | **불필요** | `Depends()` 없음 |
| `PATCH /auth/fcm-token` | **필요** | `user = Depends(get_current_user)` |

## 라우터 기본 구조

```python
# backend/app/routers/{name}.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..core.security import get_current_user  # 인증 필요한 경우만
from ..models.user import User

router = APIRouter(prefix="/{name}s", tags=["{Name}"])

@router.get("/")
async def list_{name}s(db: Session = Depends(get_db)):  # 비인증
    ...

@router.post("/")
async def create_{name}(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # 인증 필요
):
    ...
```

## 공통 응답 형식

```python
# 성공
return {"success": True, "data": result}
return {"success": True, "data": result, "count": len(result)}

# 실패
raise HTTPException(status_code=404, detail="리소스를 찾을 수 없습니다.")
raise HTTPException(status_code=400, detail="잘못된 요청입니다.")
```

## 완료 후 처리

`backend/app/main.py`에 라우터 등록:
```python
from .routers.{name} import router as {name}_router
app.include_router({name}_router)
```

## 크롤러 API 프록시 패턴 (search 라우터 전용)

`/search/*` 라우터는 직접 DB 조회가 아닌 크롤러 Flask API를 중계함:
```python
import httpx
from ..core.config import settings

async def proxy_to_crawler(endpoint: str, params: dict):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{settings.CRAWLER_API_URL}{endpoint}", params=params)
        resp.raise_for_status()
        return resp.json()
```
