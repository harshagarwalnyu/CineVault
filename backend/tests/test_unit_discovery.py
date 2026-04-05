import pandas as pd
import pytest

from backend.services.recommendation_engine_service.engines.recommendation import (
    EnhancedRecommendationEngine,
)


def _build_test_engine() -> EnhancedRecommendationEngine:
    engine = EnhancedRecommendationEngine()
    engine.movies_df = pd.DataFrame(
        [
            {
                "id": 1,
                "title": "Space Hearts",
                "genres": "Sci-Fi Romance",
                "keywords": "spaceship love found-family",
                "tagline": "Love among the stars",
                "cast": "Ava Stone Liam Hart",
                "director": "Nora Vale",
                "vote_average": 8.3,
                "vote_count": 1800,
                "poster_path": "",
                "overview": "A hopeful space opera about a crew finding love and home.",
                "release_date": "2024-05-01",
                "runtime": 120,
                "original_language": "en",
            },
            {
                "id": 2,
                "title": "Galaxy Love",
                "genres": "Sci-Fi Romance",
                "keywords": "starship romance hopeful crew",
                "tagline": "Hope travels light years",
                "cast": "Ava Stone Mira Chen",
                "director": "Nora Vale",
                "vote_average": 8.1,
                "vote_count": 1500,
                "poster_path": "",
                "overview": "A warm-hearted space adventure about connection, loyalty, and love.",
                "release_date": "2023-03-11",
                "runtime": 118,
                "original_language": "en",
            },
            {
                "id": 3,
                "title": "Robo War",
                "genres": "Sci-Fi Action",
                "keywords": "android battle war dystopia",
                "tagline": "Metal never sleeps",
                "cast": "Max Steel Ira Kane",
                "director": "Victor Hale",
                "vote_average": 7.4,
                "vote_count": 2000,
                "poster_path": "",
                "overview": "An intense future war between rogue machines and desperate rebels.",
                "release_date": "2022-08-14",
                "runtime": 132,
                "original_language": "en",
            },
            {
                "id": 4,
                "title": "Courtroom Ashes",
                "genres": "Drama",
                "keywords": "court betrayal confession",
                "tagline": "Truth burns slowly",
                "cast": "Elena Ward Theo Price",
                "director": "Marta Quill",
                "vote_average": 7.8,
                "vote_count": 950,
                "poster_path": "",
                "overview": "A restrained legal drama about grief, testimony, and moral compromise.",
                "release_date": "2021-10-05",
                "runtime": 109,
                "original_language": "en",
            },
        ]
    )
    engine.movies_df["combined_features"] = (
        engine.movies_df["title"]
        + " "
        + engine.movies_df["genres"]
        + " "
        + engine.movies_df["keywords"]
        + " "
        + engine.movies_df["director"]
        + " "
        + engine.movies_df["overview"]
    )
    engine.movies_df["title_normalized"] = engine.movies_df["title"].str.casefold()
    engine.movies_df["genres_normalized"] = engine.movies_df["genres"].str.casefold()
    engine.movies_df["director_normalized"] = engine.movies_df["director"].str.casefold()
    engine.movies_df["cast_normalized"] = engine.movies_df["cast"].str.casefold()
    engine._movie_index_by_id = {
        int(movie_id): int(idx)
        for idx, movie_id in engine.movies_df["id"].items()
    }
    engine._normalized_titles = engine.movies_df["title_normalized"].tolist()
    engine._title_lookup = dict(
        zip(engine._normalized_titles, engine.movies_df["title"].astype(str).tolist())
    )
    engine._precompute_genres()
    engine._train_content_model()
    engine.is_trained = True
    return engine


@pytest.mark.unit
def test_discover_movies_uses_query_and_liked_seed():
    engine = _build_test_engine()

    payload = engine.discover_movies(
        query="space adventure with heart",
        liked_movie_ids=[1],
        limit=2,
        diversity_factor=0.35,
    )

    assert payload["recommendation_type"] == "discover"
    assert payload["recommendations"][0]["title"] == "Galaxy Love"
    assert all(movie["id"] != 1 for movie in payload["recommendations"])
    assert "query_intent" in payload["applied_signals"]
    assert "taste_feedback" in payload["applied_signals"]
    assert payload["recommendations"][0]["hybrid_score"] > payload["recommendations"][1]["hybrid_score"]
    assert payload["recommendations"][0]["reason"]
