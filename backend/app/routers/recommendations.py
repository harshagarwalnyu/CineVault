"""Recommendation endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.schemas import DiscoveryRequest, DiscoveryResponse, RecommendationListResponse
from backend.app.dependencies import get_rec_engine, get_vec_engine
from backend.services.recommendation_engine_service.engines.recommendation import (
    EnhancedRecommendationEngine,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/recommendations/personalized/{user_id}", tags=["Recommendations"])
async def get_recommendations(
    user_id: int,
    limit: int = Query(10, ge=1, le=100),
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    recs = rec_engine.get_personalized_recommendations(user_id=user_id, limit=limit)
    return {"recommendations": recs}


@router.post(
    "/recommendations/discover",
    response_model=DiscoveryResponse,
    tags=["Recommendations"],
)
async def discover_movies(
    request: DiscoveryRequest,
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
    vector_engine=Depends(get_vec_engine),
):
    semantic_candidates = []
    if request.query:
        try:
            semantic_limit = min(max(request.limit * 4, 40), 200)
            semantic_candidates = vector_engine.search(
                request.query,
                k=semantic_limit,
                use_reranker=request.use_reranker,
            )
        except Exception as exc:
            logger.warning("Dense semantic candidate generation skipped: %s", exc)

    return rec_engine.discover_movies(
        query=request.query,
        user_id=request.user_id,
        liked_movie_ids=request.liked_movie_ids,
        liked_titles=request.liked_titles,
        excluded_movie_ids=request.excluded_movie_ids,
        limit=request.limit,
        min_rating=request.min_rating,
        diversity_factor=request.diversity_factor,
        semantic_candidates=semantic_candidates,
    )


@router.get("/recommendations/{movie_id}", response_model=RecommendationListResponse, tags=["Recommendations"])
@router.get("/recommendations/similar/{movie_id}", response_model=RecommendationListResponse, tags=["Recommendations"])
async def get_similar_movies(
    movie_id: int,
    limit: int = Query(10, ge=1, le=100),
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    movie = rec_engine.get_movie_by_id(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    recs = rec_engine.get_content_recommendations(movie_id, limit=limit)
    return {"movie": movie["title"], "recommendations": recs}
