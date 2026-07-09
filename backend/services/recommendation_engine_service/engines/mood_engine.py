"""
Mood/Emotion Recommendation Engine
====================================
Parse natural language via Gemini API -> structured mood output.
12-mood taxonomy mapped to genre affinity vectors for scoring.
"""

import json
import logging
import threading
from typing import Any, Dict, List, Optional, cast

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
            "sad": "melancholic",
            "cry": "melancholic",
            "depress": "melancholic",
            "grief": "melancholic",
            "fun": "happy",
            "laugh": "happy",
            "cheer": "happy",
            "joy": "happy",
            "feel-good": "happy",
            "scary": "tense",
            "suspense": "tense",
            "thrill": "tense",
            "edge": "tense",
            "nerve": "tense",
            "love": "romantic",
            "date": "romantic",
            "heart": "romantic",
            "passion": "romantic",
            "think": "intellectual",
            "smart": "intellectual",
            "mind": "intellectual",
            "thought": "intellectual",
            "relax": "cozy",
            "chill": "cozy",
            "comfort": "cozy",
            "calm": "cozy",
            "warm": "cozy",
            "explore": "adventurous",
            "epic": "adventurous",
            "adrenaline": "adventurous",
            "rush": "adventurous",
            "excit": "adventurous",
            "pump": "adventurous",
            "rage": "angry",
            "revenge": "angry",
            "fury": "angry",
            "fight": "angry",
            "creepy": "dark",
            "grim": "dark",
            "disturb": "dark",
            "bleak": "dark",
            "motivat": "inspired",
            "uplift": "inspired",
            "inspir": "inspired",
            "triumph": "inspired",
            "magic": "whimsical",
            "wonder": "whimsical",
            "dream": "whimsical",
            "fairy": "whimsical",
            "classic": "nostalgic",
            "old": "nostalgic",
            "retro": "nostalgic",
            "childhood": "nostalgic",
        }
        # Detect all matching moods (direct and keyword-based)
        detected_moods = []
        for mood in VALID_MOODS:
            if mood in text_lower:
                detected_moods.append(mood)
        for keyword, mood in keyword_map.items():
            if keyword in text_lower and mood not in detected_moods:
                detected_moods.append(mood)

        if detected_moods:
            primary = detected_moods[0]
            secondary = detected_moods[1] if len(detected_moods) > 1 else None
            return {
                "primary_mood": primary,
                "secondary_mood": secondary,
                "energy_level": 0.5,
                "valence": 0.5,
            }

        return {
            "primary_mood": "happy",
            "secondary_mood": None,
            "energy_level": 0.5,
            "valence": 0.5,
        }

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
            vote_count = int(row.get("vote_count", 0) or 0)
            if vote_count < 50:
                continue
            genre_str = str(row.get("genres", "")).strip()
            # Match multi-word genres (e.g. "Science Fiction") via substring containment
            score = sum(
                w for g, w in genre_scores.items() if g.lower() in genre_str.lower()
            )
            vote_avg = float(row.get("vote_average", 0) or 0)
            # Bayesian weighted rating: (v/(v+m)) * R + (m/(v+m)) * C
            # where m=300 (min votes for confidence), C=6.5 (dataset mean)
            m, C = 300, 6.5
            bayesian_avg = (vote_count / (vote_count + m)) * vote_avg + (
                m / (vote_count + m)
            ) * C

            # Recency boost: recent movies get a small uplift
            release = str(row.get("release_date", ""))
            recency = 0.0
            try:
                release_year = (
                    int(release[:4]) if release and len(release) >= 4 else 2000
                )
                from datetime import date as _date

                age = max(0, _date.today().year - release_year)
                recency = 0.05 * np.exp(-age / 2.0)
            except (ValueError, TypeError):
                pass

            final_score = score * 0.65 + (bayesian_avg / 10.0) * 0.30 + recency
            if final_score > 0:
                movie_scores.append((idx, final_score))

        movie_scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in movie_scores[:limit]:
            result_row = movies_df.loc[cast(int, idx)]
            results.append(
                {
                    "id": int(cast(Any, result_row.get("id", 0))),
                    "title": str(result_row.get("title", "")),
                    "genres": [
                        g.strip()
                        for g in str(result_row.get("genres", "")).split("|")
                        if g.strip()
                    ]
                    if "|" in str(result_row.get("genres", ""))
                    else [g for g in str(result_row.get("genres", "")).split() if g],
                    "vote_average": float(result_row.get("vote_average", 0) or 0),
                    "poster_path": str(result_row.get("poster_path", "") or ""),
                    "overview": str(result_row.get("overview", "") or "")[:200],
                    "release_date": str(result_row.get("release_date", "") or ""),
                    "mood_score": round(score * 100, 1),
                    "mood": mood_result.get("primary_mood", ""),
                    "reason": f"Matches your {mood_result.get('primary_mood', '')} mood",
                }
            )

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
