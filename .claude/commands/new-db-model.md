# 새 DB 모델 생성

`$ARGUMENTS` 이름의 SQLAlchemy 모델, Pydantic 스키마, Alembic 마이그레이션을 한번에 생성하라.

## 생성할 파일 (3개)

1. `backend/app/models/{name}.py` — SQLAlchemy 2.x ORM 모델
2. `backend/app/schemas/{name}.py` — Pydantic v2 스키마 (Create / Update / Response 분리)
3. Alembic 마이그레이션: `alembic revision --autogenerate -m "add_{name}_table"` 실행

## 프로젝트 DB 패턴 (반드시 준수)

```python
# models 기본 구조
import uuid
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID

class {Name}(Base):
    __tablename__ = "{name}s"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    is_active  = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- PK: `UUID(as_uuid=True)` — gen_random_uuid() 상당
- 시간: `DateTime(timezone=True)` — TIMESTAMPTZ
- 소프트 삭제: `is_active = Column(Boolean, default=True)`
- 외래키: `ForeignKey("users.id", ondelete="CASCADE")` 기본

## 스키마 패턴

```python
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class {Name}Create(BaseModel):
    # 생성 시 필요한 필드

class {Name}Update(BaseModel):
    # 수정 가능한 필드 (모두 Optional)

class {Name}Response(BaseModel):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
```

## 기존 모델 참고

- `backend/app/models/user.py` — 소셜 로그인 포함 복잡한 모델 패턴
- `backend/app/models/keyword.py` — 외래키·배열 필드 패턴
- `backend/app/models/notification.py` — 이력성 테이블 패턴

## 완료 후 처리

생성 후 `backend/app/models/__init__.py`에 import 추가:
```python
from .{name} import {Name}
```

그리고 마이그레이션 파일을 `alembic/versions/`에서 열어 내용을 확인한 뒤 `alembic upgrade head` 실행.
