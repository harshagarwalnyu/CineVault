# Backend Service

This directory contains the Python backend for the Movies Recommender.

## Structure

- **app/**: Main application logic (FastAPI, Models, Database).
  - `main.py`: Entry point.
- **engines/**: Recommendation logic.
  - `recommendation.py`: Hybrid recommendation engine.
  - `vector_engine.py`: Semantic search.
  - `visual_engine.py`: Visual search.
  - `knowledge_graph.py`: Graph analysis.
  - `reranker.py`: Result reranking.
- **nebula/**: Project NEBULA (Video DNA analysis).
- **scripts/**: Ingestion and maintenance scripts.
- **tests/**: Test suite.

## Usage

Apply migrations:
```bash
uv run alembic -c alembic.ini upgrade head
```

Run the API:
```bash
uv run uvicorn backend.app.main:app --reload
```

Run backend checks:
```bash
uv run ruff check backend
uv run mypy backend
uv run pytest -m "unit or integration" --cov=backend --cov-report=term-missing
```

Notes:
1. Startup now expects migrated schema by default (`AUTO_INIT_DB=false`).
2. Use `AUTO_INIT_DB=true` only for local bootstrap scenarios.
