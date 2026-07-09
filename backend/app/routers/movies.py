"""Movie browsing, detail, and genre endpoints."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlmodel import text

from backend.app.schemas import MovieDetail, PaginatedResponse
from backend.app.dependencies import get_rec_engine, _total_pages
from backend.cache import cache_key, cached
from backend.database import engine
from backend.services.recommendation_engine_service.engines.recommendation import (
    EnhancedRecommendationEngine,
    normalize_genres,
    split_genres,
)

logger = logging.getLogger(__name__)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/movies/browse", response_model=PaginatedResponse, tags=["Browsing"])
async def browse_movies(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    genre: Optional[str] = None,
    min_rating: float = 0,
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    offset = (page - 1) * per_page
    movies, total = rec_engine.search_movies(
        genre=genre, min_rating=min_rating, limit=per_page, offset=offset
    )
    return {
        "items": movies,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": _total_pages(total, per_page),
    }


@router.get("/movies/title/{title}", response_model=MovieDetail, tags=["Search"])
async def find_movie_by_title(
    title: str, rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine)
):
    movie = rec_engine.find_movie(title)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie


@router.get(
    "/movies/genre/{genre}", response_model=PaginatedResponse, tags=["Browsing"]
)
async def get_movies_by_genre(
    genre: str,
    limit: int = Query(20, ge=1, le=100),
    response: Response = None,  # type: ignore[assignment]
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    ck = cache_key("genre", genre, limit)

    def _compute():
        movies, total = rec_engine.search_movies(genre=genre, limit=limit)
        return {
            "items": movies,
            "total": total,
            "page": 1,
            "per_page": limit,
            "total_pages": _total_pages(total, limit),
        }

    result = cached(ck, _compute, ttl=120)
    if response:
        response.headers["Cache-Control"] = (
            "public, max-age=120, stale-while-revalidate=240"
        )
    return result


@router.get("/movies/{movie_id}", response_model=MovieDetail, tags=["Movies"])
async def get_movie(
    movie_id: int,
    response: Response = None,  # type: ignore[assignment]
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    ck = cache_key("movie", movie_id)
    movie = cached(ck, lambda: rec_engine.get_movie_by_id(movie_id), ttl=300)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    if response:
        response.headers["Cache-Control"] = (
            "public, max-age=300, stale-while-revalidate=600"
        )
    return movie


@router.get("/genres", tags=["Genres"])
async def get_genres(
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    return rec_engine.get_genres()


@router.get("/trending", tags=["Recommendations"])
async def get_trending(
    limit: int = Query(10, ge=1, le=50),
    response: Response = None,  # type: ignore[assignment]
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    ck = cache_key("trending", limit)
    result = cached(ck, lambda: {"movies": rec_engine.get_trending(limit)}, ttl=60)
    if response:
        response.headers["Cache-Control"] = (
            "public, max-age=60, stale-while-revalidate=120"
        )
    return result


@router.get("/latest", tags=["Recommendations"])
async def get_latest(
    limit: int = Query(10, ge=1, le=50),
    response: Response = None,  # type: ignore[assignment]
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    ck = cache_key("latest", limit)
    result = cached(ck, lambda: {"movies": rec_engine.get_latest(limit)}, ttl=60)
    if response:
        response.headers["Cache-Control"] = (
            "public, max-age=60, stale-while-revalidate=120"
        )
    return result


@router.get("/api/movies", tags=["Scalability"])
@limiter.limit("100/minute")
async def get_movies_api(
    request: Request,
    last_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=500),
):
    """Scalable movie listing with cursor-based pagination and Redis caching."""
    from backend.app.main import _get_redis

    r = _get_redis()
    ck = f"movies_cursor_{last_id}_{limit}"
    if r:
        hit = r.get(ck)
        if hit:
            return json.loads(str(hit))

    with engine.connect() as conn:
        where_clause = "WHERE id > :last_id" if last_id else ""
        query = text(f"""
            SELECT id, title, genres, director, "cast", vote_average, poster_path, popularity_score, original_language
            FROM movies
            {where_clause}
            ORDER BY id ASC
            LIMIT :limit
        """)
        result = conn.execute(query, {"last_id": last_id, "limit": limit})
        columns = result.keys()
        movies = [dict(zip(columns, row)) for row in result]

    # Normalize genres from legacy space-delimited to JSON array
    for m in movies:
        if "genres" in m and m["genres"]:
            m["genres"] = split_genres(normalize_genres(str(m["genres"])))

    response = {
        "results": movies,
        "next_cursor": movies[-1]["id"] if movies else None,
        "has_more": len(movies) == limit,
    }
    if r:
        r.setex(ck, 3600, json.dumps(response, default=str))
    return response
