# Tech Stack: oh-my-stock

## Runtime
- Node.js 22 LTS
- Python 3.12+

## Frontend
- Framework: Next.js (App Router)
- Language: TypeScript
- UI: Tailwind CSS
- State/Data: TanStack Query

## Backend
- Framework: FastAPI
- Validation: Pydantic
- ORM/DB Access: SQLAlchemy + Alembic
- Async Tasks: Celery (broker: Redis)

## Data & Infra
- Primary DB: PostgreSQL 16
- Cache/Queue: Redis 7
- Container: Docker + docker compose

## Testing & Quality
- Python: pytest, pytest-asyncio
- Frontend: vitest, testing-library
- Lint/Format:
  - TS: eslint, prettier
  - Python: ruff, black, mypy

## Core External Data Sources (MVP)
- US filings: SEC EDGAR API
- KR filings: OPEN DART API
- Market data: 상용 가격 피드(초기 1개 공급자)

## Environment Variables (initial)
- `DATABASE_URL`
- `REDIS_URL`
- `SEC_USER_AGENT`
- `DART_API_KEY`
- `MARKET_DATA_API_KEY`
- `JWT_SECRET`

## Setup Commands (reference)
```bash
# frontend
pnpm install
pnpm --filter web dev

# backend/worker
uv sync
uv run uvicorn apps.api.main:app --reload
uv run celery -A apps.worker.celery_app worker -l info

# local infra
docker compose up -d postgres redis
```
