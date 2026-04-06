"""
Mood/Emotion Recommendation Engine
====================================
Parse natural language via Gemini API -> structured mood output.
12-mood taxonomy mapped to genre affinity vectors for scoring.
"""

import json
import logging
import threading
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from backend.config import settings

logger = logging.getLogger(__name__)

MOOD_GENRE_MAP: Dict[str, Dict[str, float]] = {
    "happy": {"Comedy": 0.4, "Romance": 0.2, "Animation": 0.2},
    "melancholic": {"Drama": 0.4, "Art House": 0.3},
    "tense": {"Thriller": 0.4, "Horror": 0.2, "Mystery": 0.2},
    "adventurous": {"Adventure": 0.4, "Science Fiction": 0.3},
    "nostalgic": {"Drama": 0.3, "Romance": 0.2},
    "angry": {"Action": 0.4, "Crime": 0.3},
    "romantic": {"Romance": 0.5, "Drama": 0.2},
    "intellectual": {"Documentary": 0.3, "Mystery": 0.3},
    "cozy": {"Comedy": 0.3, "Family": 0.3},
    "dark": {"Horror": 0.3, "Thriller": 0.3},
    "inspired": {"Biography": 0.3, "Sports": 0.3},
    "whimsical": {"Fantasy": 0.3, "Animation": 0.3},
}

VALID_MOODS = list(MOOD_GENRE_MAP.keys())


class MoodEngine:
    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None and settings.GEMINI_API_KEY:
            try:
                from google import genai
                self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
            except Exception as e:
                logger.warning("Gemini client init failed: %s", e)
        return self._client

    def analyze_mood(self, text: str) -> Dict[str, Any]:
        client = self._get_client()
        if client:
            try:
                from google.genai import types
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=f'Analyze the mood and return JSON: {{primary_mood: one of {VALID_MOODS}, secondary_mood: one of {VALID_MOODS} or null, energy_level: 0-1, valence: 0-1}}. Text: "{text}"',
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
                result = json.loads(response.text)
                if result.get("primary_mood") in VALID_MOODS:
                    return result
            except Exception as e:
                logger.warning("Gemini mood analysis failed: %s", e)

        # Keyword fallback
        text_lower = text.lower()
        keyword_map = {
            "sad": "melancholic", "cry": "melancholic", "fun": "happy", "laugh": "happy",
            "scary": "tense", "suspense": "tense", "love": "romantic", "date": "romantic",
            "think": "intellectual", "smart": "intellectual", "relax": "cozy", "chill": "cozy",
            "explore": "adventurous", "epic": "adventurous", "rage": "angry", "revenge": "angry",
            "creepy": "dark", "grim": "dark", "motivat": "inspired", "uplift": "inspired",
            "magic": "whimsical", "wonder": "whimsical", "classic": "nostalgic", "old": "nostalgic",
        }
        for mood in VALID_MOODS:
            if mood in text_lower:
                return {"primary_mood": mood, "secondary_mood": None, "energy_level": 0.5, "valence": 0.5}
        for keyword, mood in keyword_map.items():
            if keyword in text_lower:
                return {"primary_mood": mood, "secondary_mood": None, "energy_level": 0.5, "valence": 0.5}

        return {"primary_mood": "happy", "secondary_mood": None, "energy_level": 0.5, "valence": 0.5}

    def _compute_genre_scores(self, mood_result: Dict) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        primary = mood_result.get("primary_mood", "happy")
        secondary = mood_result.get("secondary_mood")

        for genre, weight in MOOD_GENRE_MAP.get(primary, {}).items():
            scores[genre] = scores.get(genre, 0) + weight
        if secondary and secondary in MOOD_GENRE_MAP:
            for genre, weight in MOOD_GENRE_MAP[secondary].items():
                scores[genre] = scores.get(genre, 0) + weight * 0.5

        return scores

    def get_mood_recommendations(
        self, text: str, movies_df: Optional[pd.DataFrame], limit: int = 10
    ) -> List[Dict]:
        if movies_df is None or movies_df.empty:
            return []

        mood_result = self.analyze_mood(text)
        genre_scores = self._compute_genre_scores(mood_result)
        if not genre_scores:
            return []

        movie_scores = []
        for idx, row in movies_df.iterrows():
            genres = str(row.get("genres", "")).split()
            score = sum(genre_scores.get(g.strip(), 0) for g in genres)
            vote_avg = float(row.get("vote_average", 0) or 0)
            final_score = score * 0.7 + (vote_avg / 10.0) * 0.3
            if final_score > 0:
                movie_scores.append((idx, final_score))

        movie_scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in movie_scores[:limit]:
            row = movies_df.loc[idx]
            results.append({
                "id": int(row.get("id", 0)),
                "title": str(row.get("title", "")),
                "genres": str(row.get("genres", "")),
                "vote_average": float(row.get("vote_average", 0) or 0),
                "poster_path": str(row.get("poster_path", "") or ""),
                "overview": str(row.get("overview", "") or "")[:200],
                "mood_score": round(score * 100, 1),
                "mood": mood_result.get("primary_mood", ""),
                "reason": f"Matches your {mood_result.get('primary_mood', '')} mood",
            })

        return results


_engine: Optional[MoodEngine] = None
_lock = threading.Lock()


def get_mood_engine() -> MoodEngine:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = MoodEngine()
    return _engine
