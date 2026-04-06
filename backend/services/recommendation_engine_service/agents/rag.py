"""
RAG Retrieval Layer for Movie Concierge
========================================
Retrieves relevant movie context from Qdrant for LLM grounding.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RAGRetriever:
    """Retrieves top-k relevant movies as context for the LLM agent."""

    def __init__(self):
        self._vector_engine = None

    def _get_engine(self):
        if self._vector_engine is None:
            from backend.services.recommendation_engine_service.engines.vector_engine import get_vector_engine
            self._vector_engine = get_vector_engine()
        return self._vector_engine

    def retrieve(self, query: str, k: int = 10) -> str:
        """Retrieve top-k relevant movies as formatted context string."""
        try:
            engine = self._get_engine()
            if not engine.is_ready:
                engine.initialize_collection()

            results = engine.search(query, k=k)
            context_parts = []
            for movie in results:
                title = movie.get("title", "Unknown")
                year = str(movie.get("release_date", ""))[:4]
                genres = movie.get("genres", "")
                overview = (movie.get("overview", "") or "")[:150]
                rating = movie.get("vote_average", 0)
                context_parts.append(
                    f"- {title} ({year}): {genres}. Rating: {rating}/10. {overview}"
                )
            return "\n".join(context_parts) if context_parts else "No relevant movies found."
        except Exception as e:
            logger.warning("RAG retrieval failed: %s", e)
            return "Movie context unavailable."


_rag: Optional[RAGRetriever] = None


def get_rag_retriever() -> RAGRetriever:
    global _rag
    if _rag is None:
        _rag = RAGRetriever()
    return _rag
