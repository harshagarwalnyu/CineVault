"""Knowledge graph endpoints."""

import logging

from fastapi import APIRouter, Response

from backend.cache import cache_key, cached
from backend.services.recommendation_engine_service.engines.knowledge_graph import (
    get_knowledge_graph,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/movies/graph/related/{title}", tags=["Graph"])
async def get_graph_related(
    title: str,
    entity_type: str = "movie",
    response: Response = None,  # type: ignore[assignment]
):
    try:
        ck = cache_key("graph_related", title, entity_type)
        related = cached(
            ck,
            lambda: get_knowledge_graph().get_related_entities(
                title, entity_type=entity_type
            ),
            ttl=600,
        )
        if response:
            response.headers["Cache-Control"] = (
                "public, max-age=600, stale-while-revalidate=1200"
            )
        return {"related": related}
    except Exception as exc:
        logger.warning("Graph related lookup failed for %s: %s", title, exc)
        return {"related": []}


@router.get("/movies/graph/path", tags=["Graph"])
async def get_graph_path(
    movie1: str,
    movie2: str,
    response: Response = None,  # type: ignore[assignment]
):
    try:
        ck = cache_key("graph_path", movie1, movie2)
        paths = cached(
            ck,
            lambda: get_knowledge_graph().find_paths(movie1, movie2),
            ttl=600,
        )
        if response:
            response.headers["Cache-Control"] = (
                "public, max-age=600, stale-while-revalidate=1200"
            )
        return {"paths": paths}
    except Exception as exc:
        logger.warning("Graph path lookup failed: %s", exc)
        return {"paths": []}
