"""
Backend smoke tests for critical endpoint behavior.
"""

import pytest
from fastapi import HTTPException

from backend.app.main import app
from backend.app.routers.health import health_check
from backend.app.routers.movies import get_movie
from backend.app.routers.search import search_movies


@pytest.mark.integration
async def test_health(mock_engine):
    data = await health_check(rec_engine=mock_engine)
    assert data["status"] == "healthy"
    assert data["ready"] is True


@pytest.mark.integration
async def test_movies_search_contract(mock_engine):
    data = await search_movies(q="test", limit=20, rec_engine=mock_engine)
    assert isinstance(data.get("items"), list)
    assert data["items"][0]["title"] == "Test Movie"


@pytest.mark.integration
async def test_invalid_movie(mock_engine):
    with pytest.raises(HTTPException) as exc_info:
        await get_movie(movie_id=999999999, rec_engine=mock_engine)
    assert exc_info.value.status_code == 404


@pytest.mark.integration
def test_core_routes_registered():
    paths = {route.path for route in app.routes}
    assert "/health" in paths
    assert "/movies/search" in paths
    assert "/movies/{movie_id}" in paths
