#!/usr/bin/env bash
set -euo pipefail
cd ~/projects/Movies-Recommender

echo "=== Checking SQLite data ==="
uv run python -c "
from backend.database import engine
from sqlmodel import text
with engine.connect() as conn:
    try:
        count = conn.execute(text('SELECT COUNT(*) FROM movies')).scalar()
        print(f'Movies in SQLite: {count}')
        sample = conn.execute(text('SELECT id, title, vote_average FROM movies ORDER BY vote_average DESC LIMIT 5')).fetchall()
        for r in sample:
            print(f'  {r[0]}: {r[1]} ({r[2]})')
    except Exception as e:
        print(f'No tables yet: {e}')
"

echo ""
echo "=== Starting backend server test ==="
timeout 15 uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8001 2>&1 || true
