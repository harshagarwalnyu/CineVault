"""
MMR — Maximal Marginal Relevance Reranker
===========================================
Principled diversity-aware reranking that balances relevance and novelty.

Formula: MMR(d) = λ · Relevance(d) - (1-λ) · max_{s∈S} Similarity(d, s)

Where:
  - d is a candidate document
  - S is the set of already-selected documents
  - λ controls the relevance/diversity trade-off (1.0 = pure relevance, 0.0 = pure diversity)

Based on:
  - Carbonell & Goldstein (1998) — original MMR paper
  - SMMR: Sampling-Based MMR (SIGIR 2025) — sampling extension for scale

This replaces the crude "max 3 per genre" diversity heuristic in
ranking_pipeline.py with a mathematically principled approach that
considers actual feature similarity between items.
"""

import logging
import threading
from typing import Any, Dict, List, Optional, Set

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class MMRReranker:
    """
    Maximal Marginal Relevance reranker.

    Greedily selects items that maximize:
      score = λ * relevance - (1-λ) * max_similarity_to_selected

    This ensures each new item adds *marginal* information to the list,
    preventing redundancy while maintaining relevance.
    """

    def rerank(
        self,
        candidates: List[Dict[str, Any]],
        content_matrix: Optional[csr_matrix] = None,
        movie_index_by_id: Optional[Dict[int, int]] = None,
        lambda_param: float = 0.7,
        k: int = 10,
        relevance_key: str = "hybrid_score",
    ) -> List[Dict[str, Any]]:
        """
        Apply MMR reranking to a list of scored candidates.

        Parameters
        ----------
        candidates : list of movie dicts with relevance scores
        content_matrix : sparse TF-IDF matrix for computing similarity
        movie_index_by_id : mapping from movie_id to row in content_matrix
        lambda_param : relevance/diversity trade-off (0.7 = slightly favour relevance)
        k : number of items to select
        relevance_key : which field in candidate dict holds the relevance score
        """
        if not candidates:
            return []

        n = len(candidates)
        k = min(k, n)

        # Extract relevance scores, normalise to [0, 1]
        relevance_scores = np.array([
            float(c.get(relevance_key, 0)) for c in candidates
        ], dtype=np.float64)

        max_rel = relevance_scores.max()
        if max_rel > 0:
            relevance_scores = relevance_scores / max_rel

        # Build similarity matrix
        sim_matrix = self._build_similarity_matrix(candidates, content_matrix, movie_index_by_id)

        # Greedy MMR selection
        selected_indices: List[int] = []
        remaining = set(range(n))

        for _ in range(k):
            if not remaining:
                break

            best_idx = -1
            best_score = float("-inf")

            for idx in remaining:
                relevance = relevance_scores[idx]

                # Max similarity to already selected items
                if selected_indices:
                    max_sim = max(sim_matrix[idx][s] for s in selected_indices)
                else:
                    max_sim = 0.0

                mmr_score = lambda_param * relevance - (1.0 - lambda_param) * max_sim

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx

            if best_idx >= 0:
                selected_indices.append(best_idx)
                remaining.discard(best_idx)

        # Annotate with MMR metadata
        result = []
        for rank, idx in enumerate(selected_indices):
            movie = candidates[idx].copy()
            movie["mmr_rank"] = rank + 1
            movie["mmr_diversity_penalty"] = round(
                max(sim_matrix[idx][s] for s in selected_indices if s != idx) * 100, 1
            ) if len(selected_indices) > 1 else 0.0
            result.append(movie)

        return result

    def _build_similarity_matrix(
        self,
        candidates: List[Dict],
        content_matrix: Optional[csr_matrix],
        movie_index_by_id: Optional[Dict[int, int]],
    ) -> np.ndarray:
        """
        Build pairwise similarity matrix for candidates.

        Uses TF-IDF content similarity if available, otherwise falls back
        to genre-based Jaccard similarity.
        """
        n = len(candidates)

        # Try TF-IDF cosine similarity first (best quality)
        if content_matrix is not None and movie_index_by_id is not None:
            indices = []
            valid_mask = []
            for c in candidates:
                mid = c.get("id", 0)
                idx = movie_index_by_id.get(mid)
                if idx is not None and idx < content_matrix.shape[0]:
                    indices.append(idx)
                    valid_mask.append(True)
                else:
                    indices.append(0)
                    valid_mask.append(False)

            if any(valid_mask):
                candidate_vecs = content_matrix[indices]
                sim = cosine_similarity(candidate_vecs).astype(np.float64)
                # Zero out invalid entries
                for i in range(n):
                    if not valid_mask[i]:
                        sim[i, :] = 0.0
                        sim[:, i] = 0.0
                np.fill_diagonal(sim, 0.0)
                return sim

        # Fallback: genre-based Jaccard similarity
        return self._genre_similarity_matrix(candidates)

    def _genre_similarity_matrix(self, candidates: List[Dict]) -> np.ndarray:
        """Compute genre Jaccard similarity between all candidate pairs."""
        n = len(candidates)
        genre_sets = []
        for c in candidates:
            genres_val = c.get("genres", "")
            if isinstance(genres_val, list):
                genre_sets.append({g.lower() for g in genres_val})
            elif isinstance(genres_val, str) and "|" in genres_val:
                genre_sets.append({g.strip().lower() for g in genres_val.split("|") if g.strip()})
            else:
                genre_sets.append({g.lower() for g in str(genres_val).split() if g})


        sim = np.zeros((n, n), dtype=np.float64)
        for i in range(n):
            for j in range(i + 1, n):
                if genre_sets[i] and genre_sets[j]:
                    intersection = len(genre_sets[i] & genre_sets[j])
                    union = len(genre_sets[i] | genre_sets[j])
                    jaccard = intersection / union if union > 0 else 0.0
                    sim[i, j] = jaccard
                    sim[j, i] = jaccard

        return sim

    def adaptive_lambda(
        self,
        query: Optional[str] = None,
        num_genres_in_query: int = 0,
        user_diversity_preference: float = 0.5,
    ) -> float:
        """
        Dynamically adjust λ based on context.

        - Specific queries (genre+language+keyword) → higher λ (more relevance)
        - Broad queries ("good movies") → lower λ (more diversity)
        - User's historical diversity preference
        """
        base_lambda = 0.7

        # Specific queries need more relevance
        if query:
            words = query.lower().split()
            if len(words) >= 3:
                base_lambda = min(0.9, base_lambda + 0.1)
            elif len(words) <= 1:
                base_lambda = max(0.5, base_lambda - 0.1)

        if num_genres_in_query >= 2:
            base_lambda = min(0.85, base_lambda + 0.05)

        # Blend with user preference
        final = 0.7 * base_lambda + 0.3 * user_diversity_preference
        return round(max(0.3, min(0.95, final)), 2)


# --- Singleton ---
_engine: Optional[MMRReranker] = None
_lock = threading.Lock()


def get_mmr_reranker() -> MMRReranker:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = MMRReranker()
    return _engine
