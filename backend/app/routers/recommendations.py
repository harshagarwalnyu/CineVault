"""Recommendation endpoints."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.app.schemas import DiscoveryRequest, DiscoveryResponse, RecommendationListResponse
from backend.app.dependencies import get_rec_engine, get_vec_engine
from backend.services.recommendation_engine_service.engines.recommendation import (
    EnhancedRecommendationEngine,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============== New Schemas ==============


class MoodRequest(BaseModel):
    text: str
    user_id: Optional[int] = None
    limit: int = 10


class SessionTrackRequest(BaseModel):
    session_id: str
    movie_id: int
    action: str = "click"


class MoodPlaylistRequest(BaseModel):
    duration: str = "evening"
    starting_mood: str = "relaxed"
    ending_mood: str = "inspired"
    user_id: Optional[int] = None


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


# ============== Phase 2: New Endpoints ==============


@router.post("/api/v1/recommendations/mood", tags=["Recommendations"])
async def mood_recommendations(
    request: MoodRequest,
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    """Get mood-based movie recommendations."""
    from backend.services.recommendation_engine_service.engines.mood_engine import get_mood_engine

    mood_engine = get_mood_engine()
    results = mood_engine.get_mood_recommendations(request.text, rec_engine.movies_df, limit=request.limit)
    mood_analysis = mood_engine.analyze_mood(request.text)
    return {"mood": mood_analysis, "recommendations": results}


@router.post("/api/v1/sessions/track", tags=["Sessions"])
async def track_session_interaction(request: SessionTrackRequest):
    """Record a user interaction in a session."""
    from backend.database import engine as db_engine
    from sqlmodel import text
    import json as json_lib
    from datetime import datetime

    try:
        with db_engine.connect() as conn:
            existing = conn.execute(
                text("SELECT movie_interactions FROM user_sessions WHERE id = :sid"),
                {"sid": request.session_id},
            ).fetchone()

            interaction = {"movie_id": request.movie_id, "action": request.action, "timestamp": datetime.now().isoformat()}

            if existing:
                interactions = json_lib.loads(existing[0] or "[]")
                interactions.append(interaction)
                conn.execute(
                    text("UPDATE user_sessions SET movie_interactions = :data, updated_at = CURRENT_TIMESTAMP WHERE id = :sid"),
                    {"data": json_lib.dumps(interactions), "sid": request.session_id},
                )
            else:
                conn.execute(
                    text("INSERT INTO user_sessions (id, movie_interactions) VALUES (:sid, :data)"),
                    {"sid": request.session_id, "data": json_lib.dumps([interaction])},
                )
            conn.commit()
    except Exception as e:
        logger.warning("Session tracking failed: %s", e)

    return {"status": "ok"}


@router.get("/api/v1/recommendations/session/{session_id}", tags=["Sessions"])
async def session_recommendations(
    session_id: str,
    limit: int = Query(10, ge=1, le=50),
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    """Get session-based recommendations."""
    from backend.database import engine as db_engine
    from sqlmodel import text
    import json as json_lib

    movie_ids = []
    try:
        with db_engine.connect() as conn:
            row = conn.execute(
                text("SELECT movie_interactions FROM user_sessions WHERE id = :sid"),
                {"sid": session_id},
            ).fetchone()
            if row and row[0]:
                interactions = json_lib.loads(row[0])
                movie_ids = [i["movie_id"] for i in interactions if "movie_id" in i]
    except Exception as e:
        logger.warning("Session load failed: %s", e)

    if not movie_ids:
        return {"recommendations": rec_engine.get_trending(limit)}

    # Try session engine first, fall back to content-based
    try:
        from backend.services.recommendation_engine_service.engines.session_engine import get_session_engine
        sess_engine = get_session_engine()
        if sess_engine.is_ready:
            candidate_ids = sess_engine.get_candidates(movie_ids, k=limit)
            results = [rec_engine.get_movie_by_id(mid) for mid in candidate_ids if rec_engine.get_movie_by_id(mid)]
            if results:
                return {"recommendations": results}
    except Exception:
        pass

    # Fallback: get recs from last viewed movie
    last_movie_id = movie_ids[-1]
    recs = rec_engine.get_content_recommendations(last_movie_id, limit=limit)
    return {"recommendations": recs}


# ============== Phase 5: Novel Feature Endpoints ==============


@router.get("/api/v1/movies/{movie_id}/visual-dna", tags=["Visual"])
async def get_visual_dna(
    movie_id: int,
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    """Get cinematographic DNA breakdown + similar-by-DNA movies."""
    movie = rec_engine.get_movie_by_id(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    try:
        from backend.services.recommendation_engine_service.engines.nebula.pipeline import get_nebula_pipeline
        pipeline = get_nebula_pipeline()
        dna = pipeline.get_dna(movie_id)
        similar = pipeline.find_visual_similar(movie_id, k=10) if dna else []
        return {"movie": movie["title"], "dna": dna, "visual_similar": similar}
    except Exception as e:
        logger.warning("Visual DNA not available: %s", e)
        return {"movie": movie["title"], "dna": None, "visual_similar": []}


@router.get("/api/v1/recommendations/visual-similar/{movie_id}", tags=["Visual"])
async def get_visual_similar(
    movie_id: int,
    limit: int = Query(10, ge=1, le=50),
):
    """Find cinematographically similar movies."""
    try:
        from backend.services.recommendation_engine_service.engines.nebula.pipeline import get_nebula_pipeline
        pipeline = get_nebula_pipeline()
        results = pipeline.find_visual_similar(movie_id, k=limit)
        return {"results": results}
    except Exception as e:
        logger.warning("Visual similarity not available: %s", e)
        return {"results": []}


@router.get("/api/v1/users/{user_id}/taste-profile", tags=["Users"])
async def get_user_taste_profile(
    user_id: int,
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    """Computed taste fingerprint from ratings/history/favorites."""
    from backend.database import engine as db_engine
    from sqlmodel import text
    from collections import Counter

    genre_scores: dict[str, list[float]] = {}
    decade_counts: Counter = Counter()
    director_scores: dict[str, list[float]] = {}

    try:
        with db_engine.connect() as conn:
            ratings = conn.execute(
                text("SELECT movie_id, rating FROM ratings WHERE user_id = :uid"),
                {"uid": user_id},
            ).fetchall()
    except Exception:
        ratings = []

    if not ratings:
        raise HTTPException(status_code=404, detail="No ratings found")

    for movie_id, rating in ratings:
        movie = rec_engine.get_movie_by_id(int(movie_id))
        if not movie:
            continue
        for genre in str(movie.get("genres", "")).split():
            genre = genre.strip()
            if genre:
                genre_scores.setdefault(genre, []).append(float(rating))
        release = str(movie.get("release_date", ""))[:4]
        if release.isdigit():
            decade = f"{release[:3]}0s"
            decade_counts[decade] += 1
        director = str(movie.get("director", "")).strip()
        if director:
            director_scores.setdefault(director, []).append(float(rating))

    genres = sorted(
        [{"name": g, "affinity": round(sum(s) / len(s) / 10, 2)} for g, s in genre_scores.items()],
        key=lambda x: -x["affinity"],
    )[:10]
    decades = [{"decade": d, "count": c} for d, c in decade_counts.most_common(5)]
    directors = sorted(
        [{"name": d, "movies_rated": len(s), "avg_rating": round(sum(s) / len(s), 1)} for d, s in director_scores.items() if len(s) >= 2],
        key=lambda x: -x["avg_rating"],
    )[:10]

    avg_rating = sum(r for _, r in ratings) / len(ratings)
    novelty_appetite = 0.5  # placeholder

    return {
        "user_id": user_id,
        "total_ratings": len(ratings),
        "average_rating": round(avg_rating, 1),
        "genres": genres,
        "decades": decades,
        "directors": directors,
        "novelty_appetite": novelty_appetite,
    }


@router.post("/api/v1/playlists/mood", tags=["Playlists"])
async def create_mood_playlist(
    request: MoodPlaylistRequest,
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    """Create emotional arc movie playlist."""
    from backend.services.recommendation_engine_service.engines.mood_engine import get_mood_engine

    mood_engine = get_mood_engine()

    # Define arc based on duration
    arc_moods = {
        "evening": [request.starting_mood, "tense", "melancholic", request.ending_mood],
        "weekend": [request.starting_mood, "adventurous", "tense", "melancholic", "romantic", request.ending_mood],
    }
    moods = arc_moods.get(request.duration, [request.starting_mood, request.ending_mood])

    playlist = []
    for mood in moods:
        recs = mood_engine.get_mood_recommendations(mood, rec_engine.movies_df, limit=2)
        for rec in recs:
            rec["arc_position"] = mood
        playlist.extend(recs)

    return {"duration": request.duration, "arc": moods, "playlist": playlist}


@router.get("/api/v1/recommendations/era/{decade}", tags=["Recommendations"])
async def get_era_recommendations(
    decade: str,
    limit: int = Query(20, ge=1, le=50),
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    """Time Machine: era-specific recommendations."""
    if rec_engine.movies_df is None or rec_engine.movies_df.empty:
        return {"decade": decade, "recommendations": []}

    # Parse decade (e.g., "1990s" -> "199")
    decade_prefix = decade.replace("s", "")[:3]

    df = rec_engine.movies_df.copy()
    df["release_year"] = df["release_date"].astype(str).str[:4]
    era_movies = df[df["release_year"].str.startswith(decade_prefix)]
    era_movies = era_movies.sort_values("vote_average", ascending=False).head(limit)

    results = [rec_engine._movie_to_dict(row) for _, row in era_movies.iterrows()]
    for r in results:
        r["reason"] = f"Top rated from the {decade}"

    era_context = {
        "1950": "The Golden Age of Hollywood — epics, musicals, and film noir ruled the screen",
        "1960": "The New Wave era — French cinema, Hitchcock, and the birth of modern filmmaking",
        "1970": "New Hollywood — Coppola, Scorsese, and Spielberg redefined American cinema",
        "1980": "The Blockbuster era — action, sci-fi, and John Hughes defined a generation",
        "1990": "The Indie Renaissance — Tarantino, the Coens, and the rise of independent film",
        "2000": "The Digital Revolution — CGI, superhero franchises, and global cinema",
        "2010": "The Streaming Age — prestige TV influence, diverse voices, and MCU dominance",
        "2020": "The Hybrid Era — streaming-first releases, AI-enhanced production, and nostalgia revivals",
    }

    return {
        "decade": decade,
        "context": era_context.get(decade_prefix, f"Movies from the {decade}"),
        "recommendations": results,
    }


@router.get("/api/v1/directors/{name}/journey", tags=["Directors"])
async def get_director_journey(
    name: str,
    rec_engine: EnhancedRecommendationEngine = Depends(get_rec_engine),
):
    """Director's Journey: chronological filmography with rating trends."""
    if rec_engine.movies_df is None or rec_engine.movies_df.empty:
        raise HTTPException(status_code=404, detail="No movie data")

    df = rec_engine.movies_df
    director_movies = df[df["director"].astype(str).str.contains(name, case=False, na=False)]

    if director_movies.empty:
        raise HTTPException(status_code=404, detail=f"No movies found for director: {name}")

    director_movies = director_movies.sort_values("release_date")
    filmography = []
    for _, row in director_movies.iterrows():
        movie = rec_engine._movie_to_dict(row)
        filmography.append({
            "id": movie["id"],
            "title": movie["title"],
            "release_date": movie["release_date"],
            "vote_average": movie["vote_average"],
            "genres": movie["genres"],
            "poster_path": movie["poster_path"],
        })

    avg_rating = director_movies["vote_average"].mean()
    total_films = len(filmography)

    return {
        "director": name,
        "total_films": total_films,
        "average_rating": round(float(avg_rating), 1),
        "filmography": filmography,
    }
