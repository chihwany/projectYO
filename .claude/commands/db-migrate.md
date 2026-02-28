# Alembic 마이그레이션 생성 및 적용

`$ARGUMENTS` 설명으로 마이그레이션을 생성하고 DB에 적용하라.

## 사전 확인

```bash
# PostgreSQL이 실행 중인지 확인
docker-compose ps
# postgres 컨테이너가 Up 상태여야 함
# 아니라면: docker-compose up -d postgres
```

## 실행 순서

```bash
cd backend

# 1. 현재 마이그레이션 상태 확인
alembic current

# 2. 마이그레이션 자동 생성
alembic revision --autogenerate -m "$ARGUMENTS"
# → alembic/versions/ 에 새 파일 생성됨

# 3. 생성된 파일 반드시 검토
#    - 불필요한 drop_table, drop_column 없는지 확인
#    - 인덱스 이름 중복 없는지 확인

# 4. 마이그레이션 적용
alembic upgrade head

# 5. 적용 확인
alembic current
```

## 자주 쓰는 Alembic 명령어

```bash
# 현재 버전 확인
alembic current

# 마이그레이션 이력 전체 보기
alembic history --verbose

# 1단계 롤백
alembic downgrade -1

# 특정 버전으로 롤백
alembic downgrade {revision_id}

# 최신으로 업그레이드
alembic upgrade head

# 다음 단계로 업그레이드
alembic upgrade +1

# SQL만 출력 (실제 적용 안 함, 검토용)
alembic upgrade head --sql
```

## autogenerate가 자동 감지 못하는 것

수동으로 마이그레이션 파일을 편집해야 하는 경우:
- 인덱스 이름 변경
- `CHECK` 제약 조건
- PostgreSQL 전용 타입 (예: `UUID`, `ARRAY`)
- 파티셔닝

## 이 프로젝트 DB 연결

`backend/.env`의 `DATABASE_URL` 사용:
```
DATABASE_URL=postgresql://user:password@localhost:5432/secondhand_alert
```

`alembic.ini`의 `sqlalchemy.url`이 이 값을 읽도록 설정되어 있어야 함.

## 초기 마이그레이션 (최초 1회)

```bash
cd backend
alembic init alembic          # alembic 폴더 생성 (이미 있으면 skip)
alembic revision --autogenerate -m "initial_tables"
alembic upgrade head
```

## 트러블슈팅

- **`Target database is not up to date`**: `alembic upgrade head` 먼저 실행
- **`Can't locate revision`**: `alembic/versions/` 파일 확인, 파일명과 revision ID 일치 확인
- **`Table already exists`**: `alembic stamp head`로 현재 상태 동기화
