# Makefile for Movies Recommender

VENV_DIR = .venv
PYTHON = $(VENV_DIR)/bin/python
UV_BIN = uv
BUN_BIN = bun
FRONTEND_DIR = frontend
PYTHON_VERSION = 3.12
BACKEND_PORT = 8001
FRONTEND_PORT = 3002

.PHONY: help docker watch run dev frontend-dev frontend-install deploy-1m clean check-uv check-bun run_backend_seeding

help:
	@echo "Available commands:"
	@echo "  make docker         - Run the full Docker stack"
	@echo "  make watch          - Run Docker Compose watch mode"
	@echo "  make dev            - Run backend and frontend locally with uv + bun"
	@echo "  make run            - Run only the backend locally on $(BACKEND_PORT)"
	@echo "  make frontend-dev   - Run only the frontend locally on $(FRONTEND_PORT)"
	@echo "  make deploy-1m      - Initialize DB and ingest the large IMDb dataset"
	@echo "  make clean          - Remove local build artifacts"

docker:
	@chmod +x start.sh
	@./start.sh

watch:
	@chmod +x start.sh
	@./start.sh watch

run: $(PYTHON)
	@echo "Starting backend on http://localhost:$(BACKEND_PORT)"
	@$(PYTHON) -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port $(BACKEND_PORT)

frontend-dev: check-bun frontend-install
	@echo "Starting frontend on http://localhost:$(FRONTEND_PORT)"
	@cd $(FRONTEND_DIR) && $(BUN_BIN) run dev -- --port $(FRONTEND_PORT)

check-uv:
	@command -v $(UV_BIN) >/dev/null 2>&1 || (echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" && exit 1)

check-bun:
	@command -v $(BUN_BIN) >/dev/null 2>&1 || (echo "bun is required. Install it from https://bun.sh/docs/installation" && exit 1)

$(PYTHON): check-uv
	@echo "Ensuring Python $(PYTHON_VERSION) is available..."
	@$(UV_BIN) python install $(PYTHON_VERSION)
	@echo "Creating or syncing virtual environment..."
	@$(UV_BIN) venv $(VENV_DIR) --python $(PYTHON_VERSION) --allow-existing
	@echo "Syncing Python dependencies..."
	@$(UV_BIN) sync
	@echo "Environment ready."

frontend-install: check-bun
	@echo "Installing frontend dependencies with bun..."
	@cd $(FRONTEND_DIR) && ($(BUN_BIN) install --frozen-lockfile || $(BUN_BIN) install)

.env:
	@echo ".env file not found. Creating from .env.example..."
	@cp .env.example .env

deploy-1m: $(PYTHON) .env
	@echo "Launching Project NEBULA (1.2M scale)..."
	@echo "Initializing database schema..."
	@export PYTHONPATH=$${PYTHONPATH}:. && $(PYTHON) -m backend.database
	@echo "Starting massive IMDb ingestion..."
	@export PYTHONPATH=$${PYTHONPATH}:. && $(PYTHON) -m backend.scripts.imdb_ingest
	@echo "Deployment sequence complete."

dev: $(PYTHON) .env frontend-install run_backend_seeding
	@echo "Starting backend and frontend for local development..."
	@trap 'kill 0' INT TERM EXIT; \
	$(PYTHON) -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port $(BACKEND_PORT) & \
	cd $(FRONTEND_DIR) && $(BUN_BIN) run dev -- --port $(FRONTEND_PORT) & \
	wait

run_backend_seeding:
	@echo "Running backend data seeding (conditional)..."
	@export PYTHONPATH=$${PYTHONPATH}:. && $(PYTHON) backend/scripts/seed_data.py

clean:
	@rm -rf $(VENV_DIR)
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@rm -rf .ruff_cache .pytest_cache .hypothesis
	@rm -rf $(FRONTEND_DIR)/.next $(FRONTEND_DIR)/tsconfig.tsbuildinfo
