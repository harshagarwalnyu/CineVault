"""
Temporal Decay Collaborative Filtering Engine
===============================================
Time-aware collaborative filtering that weights recent interactions
more heavily using exponential decay, capturing evolving user preferences.

Based on:
  - Koren (2009) — "Collaborative Filtering with Temporal Dynamics" (KDD Best Paper)
  - Xia et al. (2025) — "Time-Aware Sequential Recommendation with Decay Functions"

Key insight: A user's rating from last week is more indicative of their
current taste than a rating from 2 years ago. Standard CF treats all
ratings equally, which causes stale recommendations.

The engine applies exponential time-decay to the user-item interaction
matrix before computing SVD, then blends the temporal signal into
the existing collaborative filtering pipeline.
"""

import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import svds

logger = logging.getLogger(__name__)


class TemporalDecayEngine:
    """
    Time-aware collaborative filtering with exponential decay.

    Each user-item interaction is weighted by:
      w(t) = exp(-λ · Δt)

    where Δt = (now - interaction_time) in days, and λ is the decay rate.
    Higher λ = faster forgetting (more focus on recent behavior).
    """

    def __init__(self):
        self.user_factors: Optional[np.ndarray] = None
        self.item_factors: Optional[np.ndarray] = None
        self.user_id_map: Dict[int, int] = {}
        self.movie_id_map: Dict[int, int] = {}
        self.reverse_movie_map: Dict[int, int] = {}
        self.global_mean: float = 0.0
        self._ready = False
        self._lock = threading.Lock()

    def load(
        self,
        ratings_df: Optional[pd.DataFrame] = None,
        movies_df: Optional[pd.DataFrame] = None,
        decay_rate: float = 0.005,
        n_factors: int = 50,
    ) -> "TemporalDecayEngine":
        """
        Build time-weighted SVD from ratings data.

        Parameters
        ----------
        ratings_df : DataFrame with columns [user_id, movie_id, rating, timestamp]
        movies_df : movie catalog for ID mapping
        decay_rate : λ — decay per day. 0.005 ≈ 50% weight after 139 days
        n_factors : SVD latent dimensions
        """
        try:
            if ratings_df is None or ratings_df.empty:
                logger.warning("Temporal engine: No ratings data.")
                return self

            # Build ID mappings
            unique_users = ratings_df["user_id"].unique()
            unique_movies = ratings_df["movie_id"].unique()

            self.user_id_map = {uid: idx for idx, uid in enumerate(unique_users)}
            self.movie_id_map = {mid: idx for idx, mid in enumerate(unique_movies)}
            self.reverse_movie_map = {v: k for k, v in self.movie_id_map.items()}

            num_users = len(unique_users)
            num_movies = len(unique_movies)

            if num_users < 2 or num_movies < 2:
                logger.warning("Temporal engine: Not enough users/movies for SVD.")
                return self

            # Compute temporal weights
            now = datetime.now()
            if "timestamp" in ratings_df.columns:
                timestamps = pd.to_datetime(ratings_df["timestamp"], errors="coerce")
                days_ago = (now - timestamps).dt.total_seconds() / 86400.0
                days_ago = days_ago.fillna(365.0)  # default: assume 1 year old
            else:
                days_ago = pd.Series(
                    [180.0] * len(ratings_df)
                )  # no timestamps → 6 months

            # Exponential decay weights
            weights = np.exp(-decay_rate * days_ago.to_numpy(dtype=np.float64))

            # Build weighted interaction matrix
            user_indices = (
                ratings_df["user_id"].map(self.user_id_map).to_numpy(dtype=np.int64)
            )
            movie_indices = (
                ratings_df["movie_id"].map(self.movie_id_map).to_numpy(dtype=np.int64)
            )
            ratings = ratings_df["rating"].to_numpy(dtype=np.float64)

            # Apply time decay to ratings
            weighted_ratings = ratings * weights

            self.global_mean = float(np.mean(weighted_ratings))

            # Center ratings (critical for SVD quality)
            centered_ratings = weighted_ratings - self.global_mean

            # Build sparse matrix
            interaction_matrix = coo_matrix(
                (centered_ratings, (user_indices, movie_indices)),
                shape=(num_users, num_movies),
            ).tocsr()

            # Truncated SVD
            k = min(n_factors, min(num_users, num_movies) - 1)
            if k < 1:
                logger.warning("Temporal engine: Not enough data for SVD (k=%d).", k)
                return self

            U: np.ndarray
            Vt: np.ndarray
            U, sigma, Vt = svds(interaction_matrix, k=k)

            # Store user and item factors (with sigma folded into both)
            sqrt_sigma = np.sqrt(np.diag(sigma))
            self.user_factors = U @ sqrt_sigma
            self.item_factors = (sqrt_sigma @ Vt).T  # (num_movies, k)

            self._ready = True
            logger.info(
                "Temporal decay engine loaded (%d users, %d movies, "
                "k=%d, decay=%.4f, half-life=%.0f days).",
                num_users,
                num_movies,
                k,
                decay_rate,
                np.log(2) / decay_rate,
            )
        except Exception as e:
            logger.error("Temporal engine load failed: %s", e)
            self._ready = False
        return self

    @property
    def is_ready(self) -> bool:
        return self._ready

    def predict(self, user_id: int, movie_id: int) -> float:
        """Predict rating for a (user, movie) pair."""
        if not self._ready or self.user_factors is None or self.item_factors is None:
            return 0.0

        uidx = self.user_id_map.get(user_id)
        midx = self.movie_id_map.get(movie_id)

        if uidx is None or midx is None:
            return self.global_mean

        score = self.global_mean + float(
            self.user_factors[uidx] @ self.item_factors[midx]
        )
        return max(0.0, min(10.0, score))

    def get_candidates(self, user_id: int, k: int = 100) -> List[int]:
        """Get top-k movie recommendations for a user via temporal CF."""
        if not self._ready or self.user_factors is None or self.item_factors is None:
            return []

        uidx = self.user_id_map.get(user_id)
        if uidx is None:
            return []

        user_vec = self.user_factors[uidx]  # (k,)
        scores = self.item_factors @ user_vec  # (num_movies,)
        scores += self.global_mean

        top_indices = np.argsort(scores)[::-1][:k]
        return [
            self.reverse_movie_map[int(idx)]
            for idx in top_indices
            if int(idx) in self.reverse_movie_map
        ]

    def score_candidates(
        self, user_id: int, candidate_ids: List[int]
    ) -> Dict[int, float]:
        """Score a list of candidates for a specific user."""
        if not self._ready or self.user_factors is None or self.item_factors is None:
            return {}

        uidx = self.user_id_map.get(user_id)
        if uidx is None:
            return {}

        scores = {}
        user_vec = self.user_factors[uidx]
        for mid in candidate_ids:
            midx = self.movie_id_map.get(mid)
            if midx is not None:
                score = self.global_mean + float(user_vec @ self.item_factors[midx])
                scores[mid] = max(0.0, min(1.0, score / 10.0))  # normalise to [0, 1]
        return scores

    def get_temporal_trend(self, user_id: int, recent_k: int = 10) -> Dict[str, float]:
        """
        Analyse how a user's taste has shifted recently.
        Returns genre affinity shifts (positive = growing interest).
        """
        # This would require per-timestamp genre tracking — stub for now
        return {}


# --- Singleton ---
_engine: Optional[TemporalDecayEngine] = None
_lock = threading.Lock()


def get_temporal_engine() -> TemporalDecayEngine:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = TemporalDecayEngine()
    return _engine
