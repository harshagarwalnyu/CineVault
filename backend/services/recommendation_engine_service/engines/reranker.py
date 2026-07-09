"""
SOTA Reranker (2026 Edition)
============================
Supports dual-mode reranking:
1. Cohere API (Gold Standard, Cloud)
2. FlashRank (Silver Standard, Local ONNX/CPU Optimized)
"""

import cohere
import logging
import os
from typing import List, Dict
from flashrank import Ranker, RerankRequest
from backend.config import COHERE_API_KEY

logger = logging.getLogger(__name__)


class Reranker:
    def __init__(self):
        self.cohere_client = None
        self.flash_ranker = None

        # Check for Cohere API Key
        self.cohere_key = os.getenv("COHERE_API_KEY") or COHERE_API_KEY
        if self.cohere_key:
            try:
                self.cohere_client = cohere.Client(self.cohere_key)
                logger.info("Using Cohere rerank API.")
            except Exception as e:
                logger.warning("Cohere init failed: %s", e)

        # Initialize FlashRank (Local Fallback)
        # Using ms-marco-TinyBERT-L-2-v2 (extremely fast on CPU)
        import tempfile

        try:
            cache_dir = os.path.join(tempfile.gettempdir(), "flashrank")
            self.flash_ranker = Ranker(
                model_name="ms-marco-TinyBERT-L-2-v2", cache_dir=cache_dir
            )
            logger.info("Using FlashRank local reranker. Cache: %s", cache_dir)
        except Exception as e:
            logger.warning("FlashRank init failed: %s", e)

    def rerank(self, query: str, candidates: List[Dict], top_k: int = 5) -> List[Dict]:
        """
        Re-rank a list of candidate movies based on query relevance.
        Prioritizes Cohere API -> FlashRank -> No Rerank.
        """
        if not candidates:
            return []

        # Strategy 1: Cohere API
        if self.cohere_client:
            try:
                docs = [f"{m['title']}: {m.get('overview', '')}" for m in candidates]
                response = self.cohere_client.rerank(
                    model="rerank-english-v3.0",
                    query=query,
                    documents=docs,
                    top_n=top_k,
                )

                reranked_results = []
                for hit in response.results:
                    # Map back to original candidate
                    original = candidates[hit.index]
                    original["rerank_score"] = hit.relevance_score
                    reranked_results.append(original)

                return reranked_results
            except Exception as e:
                logger.warning("Cohere API error, falling back to FlashRank: %s", e)

        # Strategy 2: FlashRank (Local)
        if self.flash_ranker:
            try:
                pass_candidates = [
                    {
                        "id": idx,
                        "text": f"{m['title']}: {m.get('overview', '')}",
                        "meta": m,
                    }
                    for idx, m in enumerate(candidates)
                ]

                request = RerankRequest(query=query, passages=pass_candidates)
                results = self.flash_ranker.rerank(request)

                reranked_results = []
                for res in results[:top_k]:
                    original = res["meta"]
                    original["rerank_score"] = res["score"]
                    reranked_results.append(original)

                return reranked_results
            except Exception as e:
                logger.warning("FlashRank error: %s", e)

        # Strategy 3: No Rerank (Return Top K from retrieval)
        return candidates[:top_k]


# Singleton
_reranker = None


def get_reranker():
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker
