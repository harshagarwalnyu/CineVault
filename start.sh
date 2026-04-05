#!/bin/bash
set -euo pipefail

echo "========================================================"
echo "  Movies Recommender - Startup Script"
echo "========================================================"
echo ""

if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from .env.example..."
    cp .env.example .env
fi

source .env
if [ -z "${TMDB_API_KEY:-}" ] || [ "${TMDB_API_KEY:-}" = "your_tmdb_key_here" ]; then
    echo "⚠️  TMDB_API_KEY is not configured. Data ingestion commands will stay disabled until you set it in .env."
fi

WATCH_MODE=false
if [ "${1:-}" = "watch" ]; then
    WATCH_MODE=true
fi

wait_for_http() {
    local name="$1"
    local url="$2"
    local max_attempts="${3:-30}"
    local interval_seconds="${4:-2}"

    echo "      Waiting for ${name} (${url})..."
    for ((attempt=1; attempt<=max_attempts; attempt++)); do
        if curl -fsS "${url}" >/dev/null 2>&1; then
            echo "      ✅ ${name} is reachable"
            return 0
        fi

        echo "      ...attempt ${attempt}/${max_attempts}"
        sleep "${interval_seconds}"
    done

    echo "      ❌ ${name} did not become reachable in time"
    return 1
}

wait_for_api_ready() {
    local url="$1"
    local max_attempts="${2:-40}"
    local interval_seconds="${3:-2}"

    echo "      Waiting for API readiness (${url})..."
    for ((attempt=1; attempt<=max_attempts; attempt++)); do
        if payload=$(curl -fsS "${url}" 2>/dev/null); then
            if printf '%s' "${payload}" | python3 -c 'import json, sys; data = json.load(sys.stdin); raise SystemExit(0 if data.get("ready") else 1)'; then
                echo "      ✅ API is ready"
                return 0
            fi
        fi

        echo "      ...attempt ${attempt}/${max_attempts}"
        sleep "${interval_seconds}"
    done

    echo "      ❌ API did not report ready=true in time"
    return 1
}

echo "[1/3] Stopping any running containers..."
docker compose down

echo ""
if [ "${WATCH_MODE}" = true ]; then
    echo "[2/3] Starting optimized development mode (watch)..."
    echo "      Source code changes will sync instantly."
    docker compose watch
else
    echo "[2/3] Building and starting the full stack (detached)..."
    docker compose up --build -d
fi

echo ""
echo "[3/3] Checking status..."
if [ "${WATCH_MODE}" = false ]; then
    docker ps
    wait_for_api_ready "http://localhost:8001/health" 40 2
    wait_for_http "Frontend" "http://localhost:3002" 40 2
fi

echo ""
echo "========================================================"
echo "  Application is live"
echo "  Frontend:  http://localhost:3002"
echo "  API Docs:  http://localhost:8001/docs"
echo ""
if [ "${WATCH_MODE}" = false ]; then
    echo "  Tip: Run './start.sh watch' for Docker Compose watch mode."
fi
echo "========================================================"
echo ""
