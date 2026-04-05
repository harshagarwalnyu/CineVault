# Movies Recommender

AI-assisted movie discovery stack built with FastAPI, Next.js, PostgreSQL/SQLite, Redis, and Qdrant.

## Stack

- Frontend: Next.js 16, React 19, NextAuth
- Backend: FastAPI, SQLModel, Alembic
- Retrieval: TF-IDF + hybrid recommendations, Qdrant semantic search, reranking
- Data: SQLite for local dev, PostgreSQL in Docker

## Prerequisites

- `uv` for Python workflows
- `bun` for frontend workflows
- Docker Desktop / Docker Engine for the full containerized stack

## Local Development

1. Copy `.env.example` to `.env` and set required secrets.
2. Run `make dev`.

That starts:

- Frontend: `http://localhost:3002`
- API docs: `http://localhost:8001/docs`

`make dev` uses `uv` for Python dependencies and `bun` for the frontend. It also seeds local data when needed.

## Docker

Run the full stack with:

```bash
make docker
```

The startup script now waits for the API to report `ready=true` before declaring the stack healthy.

## Database Migrations

Apply migrations explicitly when running outside auto-init flows:

```bash
uv run alembic -c alembic.ini upgrade head
```

## Large-Scale Ingestion

IMDb ingestion requires a valid `TMDB_API_KEY` in `.env`.

```bash
make deploy-1m
```

## Checks

Backend:

```bash
uv run ruff check
uv run pytest
```

Frontend:

```bash
cd frontend
bun run lint
bun run build
```

## Operations Docs

- `docs/runbooks/incident-response.md`
- `docs/runbooks/oncall-handoff.md`
- `docs/runbooks/db-migration-rollback.md`
- `docs/operations/production-readiness-checklist.md`
