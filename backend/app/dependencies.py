"""
Shared FastAPI Dependencies
============================
Dependency injection providers used across all routers.
"""

import hmac
import logging

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from backend.database import engine
from backend.config import API_KEY_NAME, PHD_SECRET_KEY
from backend.services.recommendation_engine_service.engines.recommendation import (
    get_engine,
    EnhancedRecommendationEngine,
)
from backend.services.recommendation_engine_service.engines.vector_engine import (
    get_vector_engine,
)

logger = logging.getLogger(__name__)

# ============== Security ==============
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def get_api_key(api_key: str = Security(api_key_header)):
    if not PHD_SECRET_KEY:
        logger.error("PHD_SECRET_KEY is not configured; rejecting protected endpoint access")
        raise HTTPException(status_code=503, detail="Auth is not configured")
    if api_key and hmac.compare_digest(str(api_key), str(PHD_SECRET_KEY)):
        return api_key
    raise HTTPException(status_code=403, detail="Could not validate credentials")


# ============== Database ==============

def get_db_conn():
    """Database connection dependency (Raw)."""
    conn = engine.raw_connection()
    try:
        yield conn
    finally:
        conn.close()


# ============== Engines ==============

def get_rec_engine() -> EnhancedRecommendationEngine:
    """Recommendation engine dependency."""
    return get_engine()


def get_vec_engine():
    """Vector engine dependency."""
    return get_vector_engine()


# ============== Helpers ==============

def _total_pages(total: int, per_page: int) -> int:
    if total == 0:
        return 0
    return (total + per_page - 1) // per_page
