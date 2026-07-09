"""Health and admin endpoints."""

import logging
import threading
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import text

from backend.database import engine
from backend.app.dependencies import get_api_key, get_rec_engine
from backend.services.recommendation_engine_service.engines.recommendation import (
    EnhancedRecommendationEngine,
)
from backend.services.recommendation_engine_service.engines.vector_engine import (
    get_vector_engine,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ============== Request Metrics ==============
REQUEST_METRICS: dict[str, Any] = {
    "total_requests": 0,
    "total_errors": 0,
    "recent_latencies_ms": [],
}
REQUEST_METRICS_LOCK = threading.Lock()


def record_request(latency_ms: float, status_code: int):
    """Record a request metric (called from middleware)."""
    with REQUEST_METRICS_LOCK:
        REQUEST_METRICS["total_requests"] += 1
        if status_code >= 500:
            REQUEST_METRICS["total_errors"] += 1
        REQUEST_METRICS["recent_latencies_ms"].append(latency_ms)
        if len(REQUEST_METRICS["recent_latencies_ms"]) > 500:
            REQUEST_METRICS["recent_latencies_ms"] = REQUEST_METRICS[
                "recent_latencies_ms"
            ][-500:]


def compute_slo_snapshot() -> dict:
    with REQUEST_METRICS_LOCK:
        total_requests = REQUEST_METRICS["total_requests"]
        total_errors = REQUEST_METRICS["total_errors"]
        latencies = list(REQUEST_METRICS["recent_latencies_ms"])

    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
    if latencies:
        sorted_latencies = sorted(latencies)
        p95_idx = max(0, int(0.95 * (len(sorted_latencies) - 1)))
        p95_latency = round(sorted_latencies[p95_idx], 2)
    else:
        p95_latency = 0.0

    error_rate = round((total_errors / total_requests), 4) if total_requests else 0.0
    return {
        "total_requests": total_requests,
        "total_errors": total_errors,
        "error_rate": error_rate,
        "avg_latency_ms": avg_latency,
        "p95_latency_ms": p95_latency,
    }


def _engine_snapshot(rec_engine: EnhancedRecommendationEngine) -> dict:
    movies_df = getattr(rec_engine, "movies_df", None)
    movies_loaded = len(movies_df) if movies_df is not None else 0
    ready = bool(rec_engine.is_trained and movies_loaded > 0)
    return {
        "status": "healthy" if ready else "warming_up",
        "ready": ready,
        "movies_loaded": movies_loaded,
        "engine_trained": rec_engine.is_trained,
        "slo": compute_slo_snapshot(),
        "timestamp": datetime.now().isoformat(),
    }


# ============== Endpoints ==============


@router.get("/health", tags=["Health"])
async def health_check(
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    return _engine_snapshot(rec_engine)


@router.get("/api/v1/health", tags=["Health"])
async def health_check_v1(
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    return await health_check(rec_engine=rec_engine)


@router.get("/admin/health/full", tags=["Admin"])
async def full_health_check(api_key: str = Depends(get_api_key)):
    health: dict[str, Any] = {
        "status": "healthy",
        "components": {
            "database": "unhealthy",
            "elasticsearch": "unhealthy",
            "redis": "unhealthy",
            "vector_db": "unhealthy",
        },
    }

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            health["components"]["database"] = "healthy"
    except Exception:
        pass

    from backend.app.main import _get_es, _get_redis

    es = _get_es()
    if es:
        try:
            if es.ping():
                health["components"]["elasticsearch"] = "healthy"
        except Exception:
            pass

    r = _get_redis()
    if r:
        try:
            if r.ping():
                health["components"]["redis"] = "healthy"
        except Exception:
            pass

    try:
        vector_engine = get_vector_engine()
        if getattr(vector_engine, "is_connected", False):
            health["components"]["vector_db"] = "healthy"
        elif getattr(vector_engine, "storage_mode", "") == "in_memory":
            health["components"]["vector_db"] = "degraded"
    except Exception:
        pass

    health["slo"] = compute_slo_snapshot()
    return health


@router.get("/admin/slo", tags=["Admin"])
async def slo_metrics(api_key: str = Depends(get_api_key)):
    return {
        "status": "ok",
        "slo": compute_slo_snapshot(),
        "timestamp": datetime.now().isoformat(),
    }
