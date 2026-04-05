"""Knowledge graph endpoints."""

from fastapi import APIRouter

from backend.services.recommendation_engine_service.engines.knowledge_graph import (
    get_knowledge_graph,
)

router = APIRouter()


@router.get("/movies/graph/related/{title}", tags=["Graph"])
async def get_graph_related(title: str, entity_type: str = "movie"):
    kg = get_knowledge_graph()
    related = kg.get_related_entities(title, entity_type=entity_type)
    return {"related": related}


@router.get("/movies/graph/path", tags=["Graph"])
async def get_graph_path(movie1: str, movie2: str):
    kg = get_knowledge_graph()
    paths = kg.find_paths(movie1, movie2)
    return {"paths": paths}
