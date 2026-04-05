"""
SOTA 2026 Movie Recommender API
================================
FastAPI + Qdrant + Redis + Elasticsearch + GROQ
Modernized with Lifespan, Pydantic V2, and Dependency Injection.
"""

import json
import hmac
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Depends, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlmodel import text
import redis
from elasticsearch import Elasticsearch
import logging
import threading


# Local Imports
from backend.app.schemas import (
    AgentInput,
    DiscoveryRequest,
    DiscoveryResponse,
    MovieDetail,
    PaginatedResponse,
    RecommendationListResponse,
    UserLogin,
)
from backend.services.recommendation_engine_service.engines.recommendation import (
    get_engine,
    EnhancedRecommendationEngine,
)
from backend.services.recommendation_engine_service.engines.vector_engine import (
    get_vector_engine,
)
from backend.services.recommendation_engine_service.engines.visual_engine import (
    get_visual_engine,
)
from backend.services.recommendation_engine_service.engines.reranker import get_reranker
from backend.database import (
    authenticate_user,
    initialize_database,
    engine,
    touch_user_last_login,
)
from backend.services.recommendation_engine_service.engines.knowledge_graph import (
    get_knowledge_graph,
)
from backend.services.recommendation_engine_service.engines.recommendation import (
    start_engine_warmup,
)

from backend.config import (
    settings,
    ELASTICSEARCH_URL,
    REDIS_URL,
    API_KEY_NAME,
    PHD_SECRET_KEY,
)

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
            _es.info()  # test connection
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

REQUEST_METRICS = {
    "total_requests": 0,
    "total_errors": 0,
    "recent_latencies_ms": [],
}
REQUEST_METRICS_LOCK = threading.Lock()

# ============== Security & Rate Limiting ==============
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def get_api_key(api_key: str = Security(api_key_header)):
    if not PHD_SECRET_KEY:
        logger.error("PHD_SECRET_KEY is not configured; rejecting protected endpoint access")
        raise HTTPException(status_code=503, detail="Auth is not configured")

    if api_key and hmac.compare_digest(str(api_key), str(PHD_SECRET_KEY)):
        return api_key

    raise HTTPException(status_code=403, detail="Could not validate credentials")


limiter = Limiter(key_func=get_remote_address, default_limits=["100 per 15 minutes"])

# ============== Dependencies ==============


def get_db_conn():
    """Database connection dependency (Raw)."""
    conn = engine.raw_connection()
    try:
        yield conn
    finally:
        conn.close()


def get_rec_engine() -> EnhancedRecommendationEngine:
    """Recommendation engine dependency."""
    return get_engine()


def _total_pages(total: int, per_page: int) -> int:
    if total == 0:
        return 0
    return (total + per_page - 1) // per_page


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


def _engine_snapshot(rec_engine: EnhancedRecommendationEngine) -> dict:
    movies_loaded = (
        len(rec_engine.movies_df)
        if getattr(rec_engine, "movies_df", None) is not None
        else 0
    )
    ready = bool(rec_engine.is_trained and movies_loaded > 0)
    return {
        "status": "healthy" if ready else "warming_up",
        "ready": ready,
        "movies_loaded": movies_loaded,
        "engine_trained": rec_engine.is_trained,
        "slo": _compute_slo_snapshot(),
        "timestamp": datetime.now().isoformat(),
    }


# ============== Lifespan ==============


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    logger.info("Checking database...")
    try:
        # Verify table existence
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
        # Start background engine initialization immediately without duplicating work.
        start_engine_warmup()
        logger.info(
            "🚀 API is ready for connections. Recommendation engine warming in background."
        )

        # Optimized PhD Init: Offload to background to ensure <1s startup
        def phd_init():
            try:
                get_vector_engine()
                get_reranker()
                logger.info("✅ PhD modules (Vector/Reranker) background init complete.")
            except Exception as e:
                logger.warning(f"PhD module background init warning: {e}")

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

# Rate Limit Handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

    with REQUEST_METRICS_LOCK:
        REQUEST_METRICS["total_requests"] += 1
        if status >= 500:
            REQUEST_METRICS["total_errors"] += 1
        REQUEST_METRICS["recent_latencies_ms"].append(latency_ms)
        if len(REQUEST_METRICS["recent_latencies_ms"]) > 500:
            REQUEST_METRICS["recent_latencies_ms"] = REQUEST_METRICS[
                "recent_latencies_ms"
            ][-500:]

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


def _compute_slo_snapshot() -> dict:
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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Unified error handling for all unexpected exceptions."""
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


# ============== Health Check ==============


@app.get("/health", tags=["Health"])
async def health_check(
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    """Detailed health check."""
    return _engine_snapshot(rec_engine)


@app.get("/api/v1/health", tags=["Health"])
async def health_check_v1(
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    """Versioned health endpoint for contract-stable clients."""
    return await health_check(rec_engine=rec_engine)


# ============== Agent / Chat Endpoints ==============


@app.post("/users/login", tags=["Users"])
async def login_user(payload: UserLogin):
    if not payload.password:
        raise HTTPException(status_code=400, detail="Password is required")

    user = authenticate_user(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    touch_user_last_login(user["id"])
    return {"success": True, "user": user}


@app.post("/agent/chat", tags=["AI Agent"])
async def chat_with_agent(
    payload: AgentInput,
):
    from backend.services.recommendation_engine_service.agents.concierge import get_agent

    agent = get_agent()
    # MovieAgent.run takes query and chat_history
    response = agent.run(payload.input, payload.chat_history)

    return {
        "response": response.get("output", "Sorry, I couldn't generate a response."),
        "metadata": response.get("intermediate_steps", []),
    }

class AgenticDiscoveryInput(BaseModel):
    query: str

@app.post("/api/v1/discovery/agentic", tags=["AI Agent"])
async def agentic_discovery_endpoint(payload: AgenticDiscoveryInput):
    from backend.services.graphrag import GraphRAGService
    service = GraphRAGService()
    return await service.agentic_discovery(payload.query)


# ============== Movie Endpoints ==============


@app.get("/movies/semantic-search", response_model=PaginatedResponse, tags=["Search"])
async def semantic_search_movies(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    rerank: bool = Query(False),
    vector_engine=Depends(get_vector_engine),
):
    """Semantic search using Qdrant vector database."""
    # Ensure index is built/loaded
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


@app.get("/movies/search", response_model=PaginatedResponse, tags=["Search"])
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


@app.get("/movies/title/{title}", response_model=MovieDetail, tags=["Search"])
async def find_movie_by_title(
    title: str, rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine)
):
    movie = rec_engine.find_movie(title)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie


@app.get("/movies/browse", response_model=PaginatedResponse, tags=["Browsing"])
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


@app.get("/movies/{movie_id}", response_model=MovieDetail, tags=["Movies"])
async def get_movie(
    movie_id: int, rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine)
):
    movie = rec_engine.get_movie_by_id(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie


@app.get("/trending", tags=["Recommendations"])
async def get_trending(
    limit: int = Query(10, ge=1, le=50),
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    movies = rec_engine.get_trending(limit)
    return {"movies": movies}


@app.get("/latest", tags=["Recommendations"])
async def get_latest(
    limit: int = Query(10, ge=1, le=50),
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    movies = rec_engine.get_latest(limit)
    return {"movies": movies}


@app.get("/recommendations/personalized/{user_id}", tags=["Recommendations"])
async def get_recommendations(
    user_id: int,
    limit: int = Query(10, ge=1, le=100),
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    recs = rec_engine.get_personalized_recommendations(user_id=user_id, limit=limit)
    return {"recommendations": recs}


@app.post(
    "/recommendations/discover",
    response_model=DiscoveryResponse,
    tags=["Recommendations"],
)
async def discover_movies(
    request: DiscoveryRequest,
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
    vector_engine=Depends(get_vector_engine),
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


@app.get("/recommendations/{movie_id}", response_model=RecommendationListResponse, tags=["Recommendations"])
@app.get("/recommendations/similar/{movie_id}", response_model=RecommendationListResponse, tags=["Recommendations"])
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


@app.get("/movies/genre/{genre}", response_model=PaginatedResponse, tags=["Browsing"])
async def get_movies_by_genre(
    genre: str,
    limit: int = Query(20, ge=1, le=100),
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    movies, total = rec_engine.search_movies(genre=genre, limit=limit)
    return {
        "items": movies,
        "total": total,
        "page": 1,
        "per_page": limit,
        "total_pages": _total_pages(total, limit),
    }


@app.get("/movies/visual/search", tags=["Search"])
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


@app.get("/genres", tags=["Genres"])
async def get_genres(
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    return rec_engine.get_genres()


@app.get("/movies/graph/related/{title}", tags=["Graph"])
async def get_graph_related(title: str, entity_type: str = "movie"):
    kg = get_knowledge_graph()
    related = kg.get_related_entities(title, entity_type=entity_type)
    return {"related": related}


@app.get("/movies/graph/path", tags=["Graph"])
async def get_graph_path(movie1: str, movie2: str):
    kg = get_knowledge_graph()
    paths = kg.find_paths(movie1, movie2)
    return {"paths": paths}


# ============== Scalability / High Concurrency (Redis + ES) ==============


@app.get("/api/movies", tags=["Scalability"])
@limiter.limit("100/minute")
async def get_movies_api(
    request: Request,
    last_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=500),
):
    """Scalable movie listing with cursor-based pagination and Redis caching."""
    r = _get_redis()
    cache_key = f"movies_cursor_{last_id}_{limit}"
    if r:
        cached = r.get(cache_key)
        if cached:
            return json.loads(str(cached))

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

    response = {
        "results": movies,
        "next_cursor": movies[-1]["id"] if movies else None,
        "has_more": len(movies) == limit,
    }
    if r:
        r.setex(cache_key, 3600, json.dumps(response, default=str))
    return response


@app.get("/api/search", tags=["Scalability"])
@limiter.limit("30/minute")
async def search_movies_es(
    request: Request,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    api_key: str = Depends(get_api_key),
):
    """Elasticsearch-powered sub-second movie search with rate limiting and security."""
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


# ============== Advanced Diagnostics ==============


@app.get("/admin/health/full", tags=["Admin"])
async def full_health_check(api_key: str = Depends(get_api_key)):
    """Deep inspection of all backend components."""
    health = {
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

    health["slo"] = _compute_slo_snapshot()

    return health


@app.get("/admin/slo", tags=["Admin"])
async def slo_metrics(api_key: str = Depends(get_api_key)):
    """Operational SLO snapshot used by dashboards and on-call handoffs."""
    return {
        "status": "ok",
        "slo": _compute_slo_snapshot(),
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    # Default to localhost for safety
    host = "0.0.0.0"
    port = 8000
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=True)
