"""
Multi-Stage Ranking Pipeline
==============================
L0: Candidate Generation (parallel) -> L1: Merge -> L2: Scoring -> L3: Post-processing
Production standard at Netflix, YouTube, Spotify (2026).
"""

import logging
import threading
from typing import Any, Dict, List, Optional, Set

import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)


class RankingPipeline:
    """Orchestrates the full multi-stage recommendation pipeline."""

    def rank(
        self,
        query: Optional[str] = None,
        user_id: Optional[int] = None,
        session_movie_ids: Optional[List[int]] = None,
        mood_text: Optional[str] = None,
        rec_engine=None,
        limit: int = 10,
        diversity_factor: float = 0.2,
        serendipity_factor: float = 0.2,
    ) -> List[Dict]:
        """Full L0->L3 ranking pipeline with graceful degradation."""
        if rec_engine is None or rec_engine.movies_df is None:
            return []

        # ── L0: Candidate Generation ──
        candidate_ids: Set[int] = set()
        source_scores: Dict[int, Dict[str, float]] = {}

        # L0a: Two-Tower ANN
        try:
            from backend.services.recommendation_engine_service.engines.two_tower import get_two_tower_engine
            tt_engine = get_two_tower_engine()
            if tt_engine.is_ready and user_id is not None:
                tt_candidates = tt_engine.get_candidates(user_id, k=200)
                for rank, mid in enumerate(tt_candidates):
                    candidate_ids.add(mid)
                    source_scores.setdefault(mid, {})["two_tower"] = 1.0 - rank / max(len(tt_candidates), 1)
        except Exception as e:
            logger.debug("Two-Tower skipped: %s", e)

        # L0b: Content TF-IDF (from existing engine)
        if query and rec_engine.content_matrix is not None:
            try:
                from sklearn.metrics.pairwise import linear_kernel
                query_vec = rec_engine.vectorizer.transform([query])
                content_scores = linear_kernel(rec_engine.content_matrix, query_vec).ravel()
                top_indices = np.argsort(content_scores)[::-1][:100]
                for rank, idx in enumerate(top_indices):
                    mid = int(rec_engine.movies_df.iloc[idx]["id"])
                    candidate_ids.add(mid)
                    source_scores.setdefault(mid, {})["content"] = float(content_scores[idx])
            except Exception as e:
                logger.debug("Content TF-IDF skipped: %s", e)

        # L0c: Session Transformer
        if session_movie_ids:
            try:
                from backend.services.recommendation_engine_service.engines.session_engine import get_session_engine
                sess_engine = get_session_engine()
                if sess_engine.is_ready:
                    sess_candidates = sess_engine.get_candidates(session_movie_ids, k=50)
                    for rank, mid in enumerate(sess_candidates):
                        candidate_ids.add(mid)
                        source_scores.setdefault(mid, {})["session"] = 1.0 - rank / max(len(sess_candidates), 1)
            except Exception as e:
                logger.debug("Session engine skipped: %s", e)

        # L0d: LightGCN
        try:
            from backend.services.recommendation_engine_service.engines.lightgcn import get_lightgcn_engine
            gcn_engine = get_lightgcn_engine()
            if gcn_engine.is_ready and user_id is not None:
                gcn_candidates = gcn_engine.get_candidates(user_id, k=100)
                for rank, mid in enumerate(gcn_candidates):
                    candidate_ids.add(mid)
                    source_scores.setdefault(mid, {})["lightgcn"] = 1.0 - rank / max(len(gcn_candidates), 1)
        except Exception as e:
            logger.debug("LightGCN skipped: %s", e)

        # L0e: Mood-filtered
        mood_scores_map: Dict[int, float] = {}
        if mood_text:
            try:
                from backend.services.recommendation_engine_service.engines.mood_engine import get_mood_engine
                mood_engine = get_mood_engine()
                mood_recs = mood_engine.get_mood_recommendations(mood_text, rec_engine.movies_df, limit=100)
                for rank, rec in enumerate(mood_recs):
                    mid = rec["id"]
                    candidate_ids.add(mid)
                    mood_scores_map[mid] = rec.get("mood_score", 0) / 100.0
                    source_scores.setdefault(mid, {})["mood"] = mood_scores_map[mid]
            except Exception as e:
                logger.debug("Mood engine skipped: %s", e)

        # Fallback: if no candidates from neural models, use trending
        if not candidate_ids:
            return rec_engine.get_trending(limit)

        # ── L1: Merge & Deduplicate ──
        candidate_list = list(candidate_ids)

        # ── L2: Feature Scoring ──
        scored_candidates = []
        for mid in candidate_list:
            movie = rec_engine.get_movie_by_id(mid)
            if movie is None:
                continue

            scores = source_scores.get(mid, {})
            vote_avg = float(movie.get("vote_average", 0) or 0)
            vote_count = int(movie.get("vote_count", 0) or 0)

            quality = vote_avg / 10.0
            popularity = min(1.0, np.log1p(vote_count) / np.log1p(10000))
            collab = rec_engine.get_collaborative_score(user_id, mid) / 10.0 if user_id else 0.5

            # Weighted feature combination
            final_score = (
                scores.get("two_tower", 0) * 0.20
                + scores.get("content", 0) * 0.15
                + scores.get("session", 0) * 0.15
                + scores.get("lightgcn", 0) * 0.15
                + scores.get("mood", 0) * 0.10
                + collab * 0.10
                + quality * 0.10
                + popularity * 0.05
            )

            movie.update({
                "two_tower_score": round(scores.get("two_tower", 0) * 100, 1),
                "lightgcn_score": round(scores.get("lightgcn", 0) * 100, 1),
                "content_score": round(scores.get("content", 0) * 100, 1),
                "session_score": round(scores.get("session", 0) * 100, 1),
                "mood_affinity": round(scores.get("mood", 0) * 100, 1),
                "collaborative_score": round(collab * 100, 1),
                "quality_score": round(quality * 100, 1),
                "popularity_score": round(popularity * 100, 1),
                "hybrid_score": round(final_score * 100, 1),
            })
            scored_candidates.append((final_score, movie))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        # ── L3: Post-Processing ──
        ranked_list = [m for _, m in scored_candidates[:limit * 3]]

        # Diversity: simple genre dedup (keep at most 3 per primary genre)
        genre_counts: Dict[str, int] = {}
        diverse_list = []
        for movie in ranked_list:
            primary_genre = str(movie.get("genres", "")).split()[0] if movie.get("genres") else "Other"
            if genre_counts.get(primary_genre, 0) < 3:
                diverse_list.append(movie)
                genre_counts[primary_genre] = genre_counts.get(primary_genre, 0) + 1
            if len(diverse_list) >= limit + 5:
                break

        # Serendipity injection
        try:
            from backend.services.recommendation_engine_service.engines.serendipity import get_serendipity_engine
            seren_engine = get_serendipity_engine()
            user_rated = set()
            if user_id and rec_engine.ratings_df is not None:
                user_rated = set(
                    int(r) for r in rec_engine.ratings_df[rec_engine.ratings_df["user_id"] == user_id]["movie_id"]
                )
            diverse_list = seren_engine.inject(
                diverse_list[:limit],
                user_rated,
                rec_engine.movies_df,
                rec_engine.content_matrix,
                rec_engine._movie_index_by_id,
                serendipity_factor=serendipity_factor,
            )
        except Exception as e:
            logger.debug("Serendipity injection skipped: %s", e)

        # Business rules: boost new releases
        for movie in diverse_list:
            release = str(movie.get("release_date", ""))
            if release >= "2025-01-01":
                movie["hybrid_score"] = round(movie.get("hybrid_score", 0) * 1.1, 1)
                if not movie.get("reason"):
                    movie["reason"] = "Recent release"

        # Generate explanations
        try:
            from backend.services.recommendation_engine_service.engines.explainability import get_explainability_engine
            explain_engine = get_explainability_engine()
            for movie in diverse_list:
                if not movie.get("reason"):
                    movie["reason"] = explain_engine.explain(movie, source_scores.get(movie["id"], {}), {
                        "query": query, "mood": mood_text, "user_id": user_id,
                    })
        except Exception as e:
            logger.debug("Explainability skipped: %s", e)

        # Final sort and limit
        diverse_list.sort(key=lambda x: x.get("hybrid_score", 0), reverse=True)
        return diverse_list[:limit]


_pipeline: Optional[RankingPipeline] = None
_lock = threading.Lock()


def get_ranking_pipeline() -> RankingPipeline:
    global _pipeline
    if _pipeline is None:
        with _lock:
            if _pipeline is None:
                _pipeline = RankingPipeline()
    return _pipeline
