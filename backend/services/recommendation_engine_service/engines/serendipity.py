"""
Serendipity Injection Engine
==============================
Injects novel, unexpected but high-quality recommendations into ranked lists.
"""

import logging
import threading
from typing import Dict, List, Optional, Set

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class SerendipityEngine:
    """Injects serendipitous picks into recommendation lists."""

    def novelty_score(self, popularity_rank: int, max_rank: int) -> float:
        """Score based on inverse popularity (obscure = more novel)."""
        if max_rank <= 1:
            return 0.5
        return 1.0 - np.log1p(popularity_rank) / np.log1p(max_rank)

    def unexpectedness_score(
        self,
        candidate_idx: int,
        user_rated_indices: List[int],
        content_matrix: Optional[csr_matrix],
    ) -> float:
        """1 - max similarity between candidate and user's rated movies."""
        if content_matrix is None or not user_rated_indices:
            return 0.5

        try:
            candidate_vec = content_matrix[candidate_idx]
            rated_vecs = content_matrix[user_rated_indices]
            sims = cosine_similarity(candidate_vec, rated_vecs).ravel()
            return float(1.0 - sims.max()) if len(sims) > 0 else 0.5
        except Exception:
            return 0.5

    def compute_serendipity(
        self,
        novelty: float,
        unexpectedness: float,
        quality: float,
    ) -> float:
        """Combined serendipity score."""
        return novelty * 0.4 + unexpectedness * 0.4 + quality * 0.2

    def inject(
        self,
        ranked_list: List[Dict],
        user_rated_ids: Set[int],
        movies_df,
        content_matrix: Optional[csr_matrix],
        movie_index_by_id: Dict[int, int],
        serendipity_factor: float = 0.2,
        min_quality: float = 6.5,
    ) -> List[Dict]:
        """Replace bottom portion of ranked list with serendipitous picks."""
        if not ranked_list or serendipity_factor <= 0:
            return ranked_list

        if movies_df is None or movies_df.empty:
            return ranked_list

        num_to_replace = max(1, int(len(ranked_list) * serendipity_factor))
        ranked_ids = {m.get("id") for m in ranked_list}

        # Build user rated indices for unexpectedness
        user_rated_indices = [
            movie_index_by_id[mid] for mid in user_rated_ids if mid in movie_index_by_id
        ]

        # Compute popularity ranks
        popularity_sorted = movies_df.sort_values("vote_count", ascending=False)
        pop_rank_map = {
            int(row["id"]): rank
            for rank, (_, row) in enumerate(popularity_sorted.iterrows())
        }
        max_rank = len(pop_rank_map)

        # Score all candidate movies not in current list or user's rated set
        serendipity_candidates = []
        for idx, row in movies_df.iterrows():
            movie_id = int(row.get("id", 0))
            vote_avg = float(row.get("vote_average", 0) or 0)

            if movie_id in ranked_ids or movie_id in user_rated_ids:
                continue
            if vote_avg < min_quality:
                continue

            movie_idx = movie_index_by_id.get(movie_id)
            if movie_idx is None:
                continue

            nov = self.novelty_score(pop_rank_map.get(movie_id, max_rank), max_rank)
            unexp = self.unexpectedness_score(
                movie_idx, user_rated_indices, content_matrix
            )
            quality = vote_avg / 10.0
            seren = self.compute_serendipity(nov, unexp, quality)

            serendipity_candidates.append(
                {
                    "id": movie_id,
                    "title": str(row.get("title", "")),
                    "genres": str(row.get("genres", "")),
                    "vote_average": vote_avg,
                    "poster_path": str(row.get("poster_path", "") or ""),
                    "overview": str(row.get("overview", "") or "")[:200],
                    "serendipity_score": round(seren * 100, 1),
                    "reason": "Hidden gem you might not expect to love",
                    "content_score": 0,
                    "collaborative_score": 0,
                    "hybrid_score": round(seren * 100, 1),
                }
            )

        serendipity_candidates.sort(
            key=lambda x: float(x["serendipity_score"]),  # type: ignore[arg-type]
            reverse=True,
        )
        top_serendipity = serendipity_candidates[:num_to_replace]

        if not top_serendipity:
            return ranked_list

        # Replace bottom N of ranked list
        result = ranked_list[:-num_to_replace] + top_serendipity
        return result


# Singleton
_engine: Optional[SerendipityEngine] = None
_lock = threading.Lock()


def get_serendipity_engine() -> SerendipityEngine:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = SerendipityEngine()
    return _engine
