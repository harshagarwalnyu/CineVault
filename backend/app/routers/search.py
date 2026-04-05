"""Search endpoints — semantic, keyword, visual, Elasticsearch."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.schemas import PaginatedResponse
from backend.app.dependencies import get_api_key, get_rec_engine, get_vec_engine, _total_pages
from backend.services.recommendation_engine_service.engines.recommendation import (
    EnhancedRecommendationEngine,
)
from backend.services.recommendation_engine_service.engines.visual_engine import (
    get_visual_engine,
)

logger = logging.getLogger(__name__)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/movies/semantic-search", response_model=PaginatedResponse, tags=["Search"])
async def semantic_search_movies(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    rerank: bool = Query(False),
    vector_engine=Depends(get_vec_engine),
):
    if not vector_engine.is_ready:
        vector_engine.initialize_collection()
    results = vector_engine.search(q, k=limit, use_reranker=rerank)
    return {
        "items": results,
        "total": len(results),
        "page": 1,
        "per_page": limit,
        "total_pages": _total_pages(len(results), limit),
    }


@router.get("/movies/search", response_model=PaginatedResponse, tags=["Search"])
async def search_movies(
    q: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    movies, total = rec_engine.search_movies(query=q, limit=limit)
    return {
        "items": movies,
        "total": total,
        "page": 1,
        "per_page": limit,
        "total_pages": _total_pages(total, limit),
    }


@router.get("/movies/visual/search", tags=["Search"])
async def visual_search_movies(
    q: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=20),
):
    visual_engine = get_visual_engine()
    results = visual_engine.search(q, top_k=limit)
    return {
        "items": results,
        "total": len(results),
        "page": 1,
        "per_page": limit,
        "total_pages": _total_pages(len(results), limit),
    }


@router.get("/api/search", tags=["Scalability"])
@limiter.limit("30/minute")
async def search_movies_es(
    request: Request,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    api_key: str = Depends(get_api_key),
):
    """Elasticsearch-powered sub-second movie search."""
    from backend.app.main import _get_es, _get_redis

    r = _get_redis()
    es = _get_es()
    cache_key = f"search_secure_{q}_{limit}"
    if r:
        cached = r.get(cache_key)
        if cached:
            return json.loads(str(cached))

    if not es:
        return {"error": "Search service temporarily unavailable", "fallback": True}

    try:
        query = {
            "multi_match": {
                "query": q,
                "fields": ["title^3", "overview", "genres", "director", "cast"],
                "fuzziness": "AUTO",
            }
        }
        res = es.search(index="movies", query=query, size=limit)
        results = [hit["_source"] for hit in res["hits"]["hits"]]

        response = {
            "query": q,
            "results": results,
            "total": res["hits"]["total"]["value"],
            "latency_ms": res["took"],
        }
        if r:
            r.setex(cache_key, 600, json.dumps(response, default=str))
        return response
    except Exception as e:
        logger.error(f"ES Error: {e}")
        return {"error": "Search service temporarily unavailable", "fallback": True}
