import os
import sys
from unittest.mock import MagicMock
import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("AUTO_INIT_DB", "false")
os.environ.setdefault("USE_MOCK_DATA", "false")
os.environ.setdefault("ENABLE_STARTUP_WARMUP", "false")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ELASTICSEARCH_URL", "http://localhost:9200")
os.environ.setdefault("COHERE_API_KEY", "")
os.environ.setdefault("GROQ_API_KEY", "")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

@pytest.fixture
def mock_engine():
    mock = MagicMock()
    base_movie = {
        "id": 1,
        "title": "Test Movie",
        "genres": "Action Adventure",
        "overview": "A test overview.",
        "vote_average": 8.2,
        "vote_count": 1200,
        "original_language": "en",
        "cinevault_qualities": ["720p.WEB", "1080p.WEB"],
    }
    similar_movie = {
        "id": 2,
        "title": "Similar Movie",
        "genres": "Action Adventure",
        "overview": "A related test movie.",
        "vote_average": 7.8,
        "vote_count": 900,
        "score": 0.87,
        "content_score": 87.0,
        "collaborative_score": 0.0,
        "hybrid_score": 87.0,
        "reason": "Highly similar content",
        "original_language": "en",
        "cinevault_qualities": ["1080p.WEB"],
    }

    mock.search_movies.return_value = ([base_movie], 1)
    mock.get_movie_by_id.side_effect = (
        lambda movie_id: None if movie_id in {999999, 999999999} else dict(base_movie)
    )
    mock.get_trending.return_value = [dict(base_movie, title="Trending Movie")]
    mock.get_personalized_recommendations.return_value = [
        dict(similar_movie, title="Recommended Movie")
    ]
    mock.get_content_recommendations.return_value = [similar_movie]
    mock.discover_movies.return_value = {
        "query_movie": "space opera with heart",
        "query_user": None,
        "recommendation_type": "discover",
        "total_results": 1,
        "applied_signals": ["query_intent", "dense_semantic", "quality"],
        "recommendations": [
            dict(
                similar_movie,
                title="Discovery Movie",
                semantic_score=91.0,
                profile_score=64.0,
                quality_score=82.0,
                popularity_score=71.0,
                hybrid_score=93.0,
                reason="Strong match for your described vibe",
            )
        ],
    }
    mock.is_trained = True
    mock.movies_df = [base_movie]
    mock.get_genres.return_value = [
        {"name": "Action", "movie_count": 1, "average_rating": 8.2}
    ]
    return mock
