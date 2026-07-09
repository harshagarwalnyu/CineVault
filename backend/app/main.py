"""
SOTA 2026 Movie Recommender API
================================
FastAPI + Qdrant + Redis + Elasticsearch + GROQ
Modernized with Lifespan, Pydantic V2, and Dependency Injection.
"""

import json
import logging
import threading
from typing import Any, Callable, cast
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlmodel import text
import redis
from elasticsearch import Elasticsearch

from backend.config import settings, ELASTICSEARCH_URL, REDIS_URL
from backend.database import engine, initialize_database
from backend.services.recommendation_engine_service.engines.recommendation import (
    start_engine_warmup,
)
from backend.services.recommendation_engine_service.engines.vector_engine import (
    get_vector_engine,
)
from backend.services.recommendation_engine_service.engines.reranker import get_reranker

# Routers
from backend.app.routers import health as health_router
from backend.app.routers import movies as movies_router
from backend.app.routers import search as search_router
from backend.app.routers import recommendations as rec_router
from backend.app.routers import users as users_router
from backend.app.routers import agent as agent_router
from backend.app.routers import graph as graph_router

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Global clients — lazy init to avoid crash when services are down
_es: Elasticsearch | None = None
_redis: redis.Redis | None = None


def _get_es() -> Elasticsearch | None:
    global _es
    if _es is None:
        try:
            _es = Elasticsearch(ELASTICSEARCH_URL)
            _es.info()
            logger.info("Elasticsearch connected")
        except Exception as e:
            logger.warning(f"Elasticsearch unavailable: {e}")
            _es = None
    return _es


def _get_redis() -> redis.Redis | None:
    global _redis
    if _redis is None:
        try:
            _redis = redis.from_url(REDIS_URL, decode_responses=True)
            _redis.ping()
            logger.info("Redis connected")
        except Exception as e:
            logger.warning(f"Redis unavailable: {e}")
            _redis = None
    return _redis


def _parse_cors_origins(origins_raw: str) -> list[str]:
    origins = [origin.strip() for origin in origins_raw.split(",") if origin.strip()]
    return origins or ["http://localhost:3002", "http://127.0.0.1:3002"]


_cors_origins = _parse_cors_origins(settings.CORS_ALLOW_ORIGINS)
_cors_allow_credentials = settings.CORS_ALLOW_CREDENTIALS
if "*" in _cors_origins and _cors_allow_credentials:
    logger.warning(
        "CORS_ALLOW_ORIGINS includes '*' with credentials enabled. "
        "Forcing credentials disabled to avoid insecure wildcard credentials."
    )
    _cors_allow_credentials = False


def _build_csp_connect_sources() -> str:
    connect_sources = {
        "'self'",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
    }
    connect_sources.update(_cors_origins)
    return " ".join(sorted(connect_sources))


# ============== Lifespan ==============


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Checking database...")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM movies LIMIT 1"))
    except Exception as e:
        if settings.AUTO_INIT_DB:
            logger.warning(
                "AUTO_INIT_DB is enabled. Initializing database schema automatically."
            )
            initialize_database(include_mock_data=settings.USE_MOCK_DATA)
        else:
            logger.error(
                "Database is not initialized. Run 'uv run alembic -c alembic.ini "
                "upgrade head' before starting the API."
            )
            raise RuntimeError("Database migration required before startup") from e

    if settings.ENABLE_STARTUP_WARMUP:
        start_engine_warmup()
        logger.info(
            "API is ready for connections. Recommendation engine warming in background."
        )

        def phd_init():
            try:
                get_vector_engine()
                get_reranker()
                logger.info("PhD modules (Vector/Reranker) background init complete.")
            except Exception as e:
                logger.warning(f"PhD module background init warning: {e}")

            # Pre-build knowledge graph so first request is fast
            try:
                from backend.services.recommendation_engine_service.engines.knowledge_graph import (
                    get_knowledge_graph,
                )

                kg = get_knowledge_graph()
                kg.build_graph()
                logger.info("Knowledge graph pre-built during startup.")
            except Exception as e:
                logger.warning(f"Knowledge graph pre-build warning: {e}")

        threading.Thread(target=phd_init, daemon=True).start()
    else:
        logger.info("Startup warmup disabled by configuration.")

    yield
    logger.info("Shutting down...")


# ============== App Setup ==============

app = FastAPI(
    title="Netflix-Scale Movie Recommender API (PhD Edition)",
    version="4.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

limiter = Limiter(key_func=get_remote_address, default_limits=["100 per 15 minutes"])
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded, cast(Callable[..., Any], _rate_limit_exceeded_handler)
)


# ============== Security Headers Middleware ==============


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    start = perf_counter()

    response = await call_next(request)
    headers = {
        "Content-Security-Policy": (
            "default-src 'self'; "
            f"connect-src {_build_csp_connect_sources()}; "
            "img-src 'self' data: https:; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline';"
        ),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    }
    if request.url.scheme == "https" or settings.APP_ENV == "production":
        headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
    for key, value in headers.items():
        response.headers[key] = value
    response.headers["X-Request-ID"] = request_id

    latency_ms = round((perf_counter() - start) * 1000, 2)
    status = response.status_code

    # Record metrics
    health_router.record_request(latency_ms, status)

    logger.info(
        json.dumps(
            {
                "event": "request_completed",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status,
                "latency_ms": latency_ms,
            }
        )
    )

    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from fastapi import HTTPException

    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "Client Error", "message": exc.detail},
        )

    request_id = request.headers.get("X-Request-ID", "unknown")
    logger.exception(
        "Unhandled request error",
        extra={
            "request_id": request_id,
            "path": str(request.url.path),
            "method": request.method,
        },
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred.",
        },
    )


# ============== Register Routers ==============

app.include_router(health_router.router)
app.include_router(users_router.router)
app.include_router(agent_router.router)
app.include_router(search_router.router)
app.include_router(movies_router.router)
app.include_router(rec_router.router)
app.include_router(graph_router.router)


if __name__ == "__main__":
    import uvicorn

    host = "0.0.0.0"
    port = 8000
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=True)
