"""
Explainability Engine
======================
Generates human-readable explanations for recommendations.
Template-based with optional LLM polish via Gemini.
"""

import logging
import threading
from typing import Any, Dict, Optional

from backend.config import settings

logger = logging.getLogger(__name__)


class ExplainabilityEngine:
    """Generates recommendation explanations from scoring signals."""

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None and settings.GEMINI_API_KEY:
            try:
                from google import genai
                self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
            except Exception:
                pass
        return self._client

    def explain(
        self,
        movie: Dict[str, Any],
        scores: Dict[str, float],
        context: Dict[str, Any],
    ) -> str:
        """Generate explanation for why a movie was recommended."""
        reasons = []
        vote_avg = float(movie.get("vote_average", 0) or 0)
        vote_count = int(movie.get("vote_count", 0) or 0)
        genres = str(movie.get("genres", ""))

        # Identify dominant signal
        dominant_signal = max(scores, key=scores.get, default=None) if scores else None

        if dominant_signal == "two_tower":
            reasons.append("Users with your taste profile love this one")
        elif dominant_signal == "content":
            query = context.get("query", "")
            if query:
                reasons.append(f'Strong match for "{query}"')
            else:
                reasons.append("Highly similar content to your preferences")
        elif dominant_signal == "session":
            reasons.append("Continues the vibe of your current session")
        elif dominant_signal == "hstu":
            reasons.append("Predicted as your ideal next watch")
        elif dominant_signal == "lightgcn":
            reasons.append("Discovered through collaborative taste patterns")
        elif dominant_signal == "temporal":
            reasons.append("Aligned with your recent viewing evolution")
        elif dominant_signal == "clrec":
            reasons.append("Deep feature similarity to movies you enjoy")
        elif dominant_signal == "mood":
            mood = context.get("mood", "")
            if mood:
                reasons.append(f"Matches your {mood} mood perfectly")
            else:
                reasons.append("Great mood match")

        # Quality signal
        if vote_avg >= 8.0 and vote_count < 5000:
            reasons.append(f"Hidden gem: only {vote_count:,} ratings but {vote_avg} average")
        elif vote_avg >= 8.0:
            reasons.append(f"Critically acclaimed ({vote_avg}/10)")

        # Collaborative signal
        collab_score = scores.get("collaborative", 0)
        if collab_score >= 0.7:
            reasons.append(f"Users with similar taste rate this {round(collab_score * 5, 1)}/5")

        if not reasons:
            if genres:
                if isinstance(genres, list):
                    primary_genre = genres[0] if genres else "movies"
                elif isinstance(genres, str) and "|" in genres:
                    primary_genre = genres.split("|")[0].strip() or "movies"
                else:
                    primary_genre = genres.split()[0]
                reasons.append(f"Top pick in {primary_genre}")
            else:
                reasons.append("Recommended based on your taste profile")

        return "; ".join(reasons[:2])

    def batch_explain(
        self,
        movies: list[Dict],
        scores_map: Dict[int, Dict[str, float]],
        context: Dict[str, Any],
    ) -> list[str]:
        """Generate explanations for a batch of movies."""
        return [
            self.explain(movie, scores_map.get(movie.get("id", 0), {}), context)
            for movie in movies
        ]


_engine: Optional[ExplainabilityEngine] = None
_lock = threading.Lock()


def get_explainability_engine() -> ExplainabilityEngine:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = ExplainabilityEngine()
    return _engine
