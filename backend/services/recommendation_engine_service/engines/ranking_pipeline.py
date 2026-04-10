"""
Multi-Stage Ranking Pipeline (v2 — 2026 Edition)
===================================================
L0: Candidate Generation (parallel) -> L1: Merge -> L2: Multi-signal Scoring
-> L3: MMR Diversity Reranking -> L4: Post-processing

Engines integrated:
  - Two-Tower (ANN candidate generation)
  - Content TF-IDF (query-based retrieval)
  - Session Transformer (session continuity)
  - HSTU (advanced sequential prediction)
  - LightGCN (graph collaborative filtering)
  - Temporal Decay CF (time-weighted collaborative)
  - CLRec (contrastive learning similarity)
  - Multi-Objective MTL (watch/rate/engage prediction)
  - Thompson Sampling Bandit (exploration-exploitation)
  - Mood Engine (affective filtering)
  - Serendipity Engine (novelty injection)
  - MMR Reranker (principled diversity)
  - Explainability Engine (reason generation)

Production standard at Netflix, YouTube, Spotify (2026).
"""

import logging
import threading
from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as _pd

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
        diversity_factor: float = 0.7,
        serendipity_factor: float = 0.2,
    ) -> List[Dict]:
        """Full L0->L4 ranking pipeline with graceful degradation."""
        if rec_engine is None or rec_engine.movies_df is None:
            return []

        # ── L0: Candidate Generation (parallel sources) ──
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

        # L0d: HSTU (advanced sequential model)
        if session_movie_ids:
            try:
                from backend.services.recommendation_engine_service.engines.hstu_engine import get_hstu_engine
                hstu = get_hstu_engine()
                if hstu.is_ready:
                    hstu_candidates = hstu.get_candidates(session_movie_ids, k=50)
                    for rank, mid in enumerate(hstu_candidates):
                        candidate_ids.add(mid)
                        source_scores.setdefault(mid, {})["hstu"] = 1.0 - rank / max(len(hstu_candidates), 1)
            except Exception as e:
                logger.debug("HSTU skipped: %s", e)

        # L0e: LightGCN
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

        # L0f: Temporal Decay CF
        try:
            from backend.services.recommendation_engine_service.engines.temporal_engine import get_temporal_engine
            temporal = get_temporal_engine()
            if temporal.is_ready and user_id is not None:
                temp_candidates = temporal.get_candidates(user_id, k=100)
                for rank, mid in enumerate(temp_candidates):
                    candidate_ids.add(mid)
                    source_scores.setdefault(mid, {})["temporal"] = 1.0 - rank / max(len(temp_candidates), 1)
        except Exception as e:
            logger.debug("Temporal engine skipped: %s", e)

        # L0g: Mood-filtered
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

        # ── L1.5: CLRec similarity scoring (enriches all candidates) ──
        clrec_scores: Dict[int, float] = {}
        if session_movie_ids:
            try:
                from backend.services.recommendation_engine_service.engines.clrec_engine import get_clrec_engine
                clrec = get_clrec_engine()
                if clrec.is_ready:
                    clrec_scores = clrec.score_candidates(session_movie_ids, candidate_list)
                    for mid, score in clrec_scores.items():
                        source_scores.setdefault(mid, {})["clrec"] = score
            except Exception as e:
                logger.debug("CLRec skipped: %s", e)

        # ── L2: Multi-Signal Feature Scoring ──

        # Batch score with Multi-Objective MTL
        mtl_scores: Dict[int, Dict[str, float]] = {}
        try:
            from backend.services.recommendation_engine_service.engines.multiobjective_engine import get_multiobjective_engine
            mtl = get_multiobjective_engine()
            if mtl.is_ready:
                mtl_scores = mtl.score_batch(candidate_list)
        except Exception as e:
            logger.debug("Multi-Objective skipped: %s", e)

        # Thompson Sampling exploration scores
        bandit_scores: Dict[int, float] = {}
        try:
            from backend.services.recommendation_engine_service.engines.bandit_engine import get_bandit_engine
            bandit = get_bandit_engine()
            if bandit.is_ready:
                sampled = bandit.select_arms(candidate_list, user_id=user_id, k=len(candidate_list))
                bandit_scores = {mid: score for mid, score in sampled}
        except Exception as e:
            logger.debug("Bandit skipped: %s", e)

        movies_map = rec_engine.get_movies_by_ids(candidate_list)

        scored_candidates = []
        for mid in candidate_list:
            movie = movies_map.get(mid)
            if movie is None:
                continue

            scores = source_scores.get(mid, {})
            vote_avg = float(movie.get("vote_average", 0) or 0)
            vote_count = int(movie.get("vote_count", 0) or 0)

            quality = vote_avg / 10.0
            popularity = min(1.0, np.log1p(vote_count) / np.log1p(10000))
            collab = rec_engine.get_collaborative_score(user_id, mid) / 10.0 if user_id else 0.5

            # MTL scores
            mtl = mtl_scores.get(mid, {})
            ev_score = mtl.get("ev_score", 0.5)

            # Bandit exploration score
            bandit_val = bandit_scores.get(mid, 0.5)

            # Weighted multi-signal combination
            # Weights sum to ~1.0 for interpretability
            final_score = (
                scores.get("two_tower", 0) * 0.12
                + scores.get("content", 0) * 0.12
                + scores.get("session", 0) * 0.08
                + scores.get("hstu", 0) * 0.10
                + scores.get("lightgcn", 0) * 0.08
                + scores.get("temporal", 0) * 0.08
                + scores.get("clrec", 0) * 0.07
                + scores.get("mood", 0) * 0.07
                + ev_score * 0.10
                + bandit_val * 0.05
                + collab * 0.05
                + quality * 0.05
                + popularity * 0.03
            )

            movie.update({
                "two_tower_score": round(scores.get("two_tower", 0) * 100, 1),
                "lightgcn_score": round(scores.get("lightgcn", 0) * 100, 1),
                "content_score": round(scores.get("content", 0) * 100, 1),
                "session_score": round(scores.get("session", 0) * 100, 1),
                "hstu_score": round(scores.get("hstu", 0) * 100, 1),
                "temporal_score": round(scores.get("temporal", 0) * 100, 1),
                "clrec_score": round(scores.get("clrec", 0) * 100, 1),
                "mood_affinity": round(scores.get("mood", 0) * 100, 1),
                "ev_score": round(ev_score * 100, 1),
                "watch_prob": round(mtl.get("watch_prob", 0) * 100, 1),
                "rating_pred": round(mtl.get("rating_pred", 0) * 100, 1),
                "engagement_pred": round(mtl.get("engagement_pred", 0) * 100, 1),
                "bandit_score": round(bandit_val * 100, 1),
                "collaborative_score": round(collab * 100, 1),
                "quality_score": round(quality * 100, 1),
                "popularity_score": round(popularity * 100, 1),
                "hybrid_score": round(final_score * 100, 1),
            })
            scored_candidates.append((final_score, movie))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        # ── L3: MMR Diversity Reranking ──
        ranked_list = [m for _, m in scored_candidates[:limit * 3]]

        try:
            from backend.services.recommendation_engine_service.engines.mmr_engine import get_mmr_reranker
            mmr = get_mmr_reranker()
            lambda_param = mmr.adaptive_lambda(query=query)
            ranked_list = mmr.rerank(
                ranked_list,
                content_matrix=rec_engine.content_matrix,
                movie_index_by_id=rec_engine._movie_index_by_id,
                lambda_param=lambda_param,
                k=limit + 5,
                relevance_key="hybrid_score",
            )
        except Exception as e:
            logger.debug("MMR reranking skipped, falling back to genre dedup: %s", e)
            # Fallback: simple genre dedup (keep at most 3 per primary genre)
            genre_counts: Dict[str, int] = {}
            diverse_list = []
            for movie in ranked_list:
                genres_val = movie.get("genres", "")
                if isinstance(genres_val, list):
                    genre_list = genres_val
                else:
                    from backend.services.recommendation_engine_service.engines.recommendation import normalize_genres, split_genres
                    genre_list = split_genres(normalize_genres(str(genres_val)))
                primary_genre = genre_list[0] if genre_list else "Other"
                if genre_counts.get(primary_genre, 0) < 3:
                    diverse_list.append(movie)
                    genre_counts[primary_genre] = genre_counts.get(primary_genre, 0) + 1
                if len(diverse_list) >= limit + 5:
                    break
            ranked_list = diverse_list

        # ── L4: Post-Processing ──

        # Serendipity injection
        try:
            from backend.services.recommendation_engine_service.engines.serendipity import get_serendipity_engine
            seren_engine = get_serendipity_engine()
            user_rated = set()
            if user_id and rec_engine.ratings_df is not None:
                user_rated = set(
                    int(r) for r in rec_engine.ratings_df[rec_engine.ratings_df["user_id"] == user_id]["movie_id"]
                )
            ranked_list = seren_engine.inject(
                ranked_list[:limit],
                user_rated,
                rec_engine.movies_df,
                rec_engine.content_matrix,
                rec_engine._movie_index_by_id,
                serendipity_factor=serendipity_factor,
            )
        except Exception as e:
            logger.debug("Serendipity injection skipped: %s", e)

        # Business rules: recency boost for recent releases (past 2-3 years)
        now = _pd.Timestamp.now()
        for movie in ranked_list:
            release = str(movie.get("release_date", ""))
            try:
                release_dt = _pd.to_datetime(release, errors="coerce")
                if _pd.notna(release_dt):
                    age_years = (now - release_dt).total_seconds() / (365.25 * 86400)
                    if age_years < 3:
                        boost = 1.0 + 0.15 * np.exp(-age_years / 1.5)
                        movie["hybrid_score"] = round(movie.get("hybrid_score", 0) * boost, 1)
                        if not movie.get("reason") and age_years < 1:
                            movie["reason"] = "Recent release"
            except Exception:
                pass

        # Generate explanations
        try:
            from backend.services.recommendation_engine_service.engines.explainability import get_explainability_engine
            explain_engine = get_explainability_engine()
            for movie in ranked_list:
                if not movie.get("reason"):
                    movie["reason"] = explain_engine.explain(movie, source_scores.get(movie["id"], {}), {
                        "query": query, "mood": mood_text, "user_id": user_id,
                    })
        except Exception as e:
            logger.debug("Explainability skipped: %s", e)

        # Final sort and limit
        ranked_list.sort(key=lambda x: x.get("hybrid_score", 0), reverse=True)
        return ranked_list[:limit]


_pipeline: Optional[RankingPipeline] = None
_lock = threading.Lock()


def get_ranking_pipeline() -> RankingPipeline:
    global _pipeline
    if _pipeline is None:
        with _lock:
            if _pipeline is None:
                _pipeline = RankingPipeline()
    return _pipeline
