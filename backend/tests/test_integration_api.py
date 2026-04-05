from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.app.main import (
    discover_movies,
    get_movie,
    get_recommendations,
    get_similar_movies,
    get_trending,
    health_check,
    login_user,
    search_movies,
)
from backend.app.schemas import DiscoveryRequest, UserLogin


@pytest.mark.integration
async def test_health_check(mock_engine):
    payload = await health_check(rec_engine=mock_engine)
    assert payload["status"] == "healthy"
    assert payload["ready"] is True


@pytest.mark.integration
async def test_login_success():
    with (
        patch(
            "backend.app.main.authenticate_user",
            return_value={"id": 1, "username": "user_1", "email": "user1@example.com"},
        ),
        patch("backend.app.main.touch_user_last_login") as touch_last_login,
    ):
        response = await login_user(
            UserLogin(username="user_1", password="sample-user-1")
        )

    assert response["success"] is True
    assert response["user"]["username"] == "user_1"
    touch_last_login.assert_called_once_with(1)


@pytest.mark.integration
async def test_login_invalid_credentials():
    with patch("backend.app.main.authenticate_user", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await login_user(UserLogin(username="user_1", password="wrong-password"))

    assert exc_info.value.status_code == 401


@pytest.mark.integration
async def test_search_movies(mock_engine):
    data = await search_movies(q="Test", limit=20, rec_engine=mock_engine)
    assert data["items"][0]["title"] == "Test Movie"


@pytest.mark.integration
async def test_get_movie_details(mock_engine):
    movie = await get_movie(movie_id=1, rec_engine=mock_engine)
    assert movie["title"] == "Test Movie"


@pytest.mark.integration
async def test_get_movie_not_found(mock_engine):
    with pytest.raises(HTTPException) as exc_info:
        await get_movie(movie_id=999999, rec_engine=mock_engine)
    assert exc_info.value.status_code == 404


@pytest.mark.integration
async def test_trending(mock_engine):
    response = await get_trending(limit=10, rec_engine=mock_engine)
    assert len(response["movies"]) > 0


@pytest.mark.integration
async def test_personalized_recs(mock_engine):
    response = await get_recommendations(user_id=1, limit=10, rec_engine=mock_engine)
    assert len(response["recommendations"]) > 0


@pytest.mark.integration
async def test_discovery_recommendations(mock_engine):
    mock_vector_engine = type(
        "VectorEngineStub",
        (),
        {
            "search": lambda self, query, k, use_reranker=False: [
                {"id": 2, "title": "Discovery Movie", "score": 0.93}
            ]
        },
    )()

    payload = await discover_movies(
        request=DiscoveryRequest(query="space opera with heart", limit=5),
        rec_engine=mock_engine,
        vector_engine=mock_vector_engine,
    )

    assert payload["recommendation_type"] == "discover"
    assert payload["recommendations"][0]["title"] == "Discovery Movie"
    assert "query_intent" in payload["applied_signals"]


@pytest.mark.integration
async def test_similar_recommendations_contract(mock_engine):
    payload = await get_similar_movies(movie_id=1, limit=10, rec_engine=mock_engine)
    assert payload["movie"] == "Test Movie"
    assert payload["recommendations"][0]["title"] == "Similar Movie"
    assert payload["recommendations"][0]["content_score"] == 87.0
