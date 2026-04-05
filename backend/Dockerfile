# Stage 1: Get uv binary
FROM ghcr.io/astral-sh/uv:latest AS uv_bin

# Stage 2: Base image with system dependencies
FROM python:3.12-slim AS base

# Install system dependencies with caching
RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy uv from stage 1
COPY --from=uv_bin /uv /usr/local/bin/uv

# Set environment variables
ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

# Stage 3: Development
FROM base AS development

# Install dependencies using cache mount for uv
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Copy application layers - order by change frequency
COPY alembic.ini ./
COPY alembic ./alembic
COPY backend ./backend
COPY data ./data

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Stage 4: Production
FROM base AS production

# Install dependencies using cache mount for uv
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy application layers
COPY alembic.ini ./
COPY alembic ./alembic
COPY backend ./backend
COPY data ./data

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

