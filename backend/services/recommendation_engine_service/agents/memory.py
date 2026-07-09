"""
Conversation Memory for Movie Concierge
=========================================
Persists conversation turns and extracted preferences in agent_conversations table.
"""

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

from sqlmodel import text

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Manages conversation persistence and preference extraction."""

    def __init__(self):
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from backend.database import engine

            self._engine = engine
        return self._engine

    def save_turn(
        self, conversation_id: str, user_id: Optional[int], role: str, content: str
    ):
        """Save a conversation turn."""
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT messages FROM agent_conversations WHERE id = :cid"),
                    {"cid": conversation_id},
                ).fetchone()

                turn = {
                    "role": role,
                    "content": content,
                    "timestamp": datetime.now().isoformat(),
                }

                if row:
                    messages = json.loads(row[0] or "[]")
                    messages.append(turn)
                    conn.execute(
                        text(
                            "UPDATE agent_conversations SET messages = :msgs, updated_at = CURRENT_TIMESTAMP WHERE id = :cid"
                        ),
                        {"msgs": json.dumps(messages), "cid": conversation_id},
                    )
                else:
                    conn.execute(
                        text(
                            "INSERT INTO agent_conversations (id, user_id, messages, extracted_preferences) VALUES (:cid, :uid, :msgs, :prefs)"
                        ),
                        {
                            "cid": conversation_id,
                            "uid": user_id,
                            "msgs": json.dumps([turn]),
                            "prefs": json.dumps({}),
                        },
                    )
                conn.commit()
        except Exception as e:
            logger.warning("Failed to save conversation turn: %s", e)

    def get_history(self, conversation_id: str) -> List[Dict]:
        """Get conversation history."""
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT messages FROM agent_conversations WHERE id = :cid"),
                    {"cid": conversation_id},
                ).fetchone()
                if row and row[0]:
                    return json.loads(row[0])
        except Exception as e:
            logger.warning("Failed to load conversation: %s", e)
        return []

    def extract_preferences(self, conversation_id: str) -> Dict:
        """Extract preference signals from conversation using pattern matching."""
        history = self.get_history(conversation_id)
        if not history:
            return {}

        liked_genres = set()
        disliked_genres = set()
        mentioned_movies = []
        mood_history = []

        genre_words = {
            "action",
            "comedy",
            "drama",
            "horror",
            "thriller",
            "romance",
            "sci-fi",
            "fantasy",
            "animation",
            "documentary",
            "mystery",
            "crime",
            "adventure",
            "family",
            "music",
            "war",
            "western",
            "history",
        }
        mood_words = {
            "happy",
            "sad",
            "scary",
            "funny",
            "romantic",
            "exciting",
            "relaxing",
            "dark",
            "intense",
            "cozy",
            "nostalgic",
            "inspiring",
        }

        for turn in history:
            content = turn.get("content", "").lower()
            if turn.get("role") == "user":
                # Extract genre preferences
                for genre in genre_words:
                    if genre in content:
                        if any(
                            neg in content
                            for neg in ["don't like", "hate", "not into", "no "]
                        ):
                            disliked_genres.add(genre)
                        else:
                            liked_genres.add(genre)

                # Extract mood signals
                for mood in mood_words:
                    if mood in content:
                        mood_history.append(mood)

                # Extract movie mentions (quoted titles)
                quoted = re.findall(r'"([^"]+)"', content)
                mentioned_movies.extend(quoted)

        prefs = {
            "liked_genres": list(liked_genres),
            "disliked_genres": list(disliked_genres),
            "mood_history": mood_history[-5:],
            "mentioned_movies": mentioned_movies[-10:],
        }

        # Persist
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "UPDATE agent_conversations SET extracted_preferences = :prefs WHERE id = :cid"
                    ),
                    {"prefs": json.dumps(prefs), "cid": conversation_id},
                )
                conn.commit()
        except Exception:
            pass

        return prefs

    def get_preferences(self, conversation_id: str) -> Dict:
        """Get stored preferences."""
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT extracted_preferences FROM agent_conversations WHERE id = :cid"
                    ),
                    {"cid": conversation_id},
                ).fetchone()
                if row and row[0]:
                    return json.loads(row[0])
        except Exception:
            pass
        return {}

    def get_user_conversations(self, user_id: int) -> List[Dict]:
        """Get all conversations for a user."""
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT id, messages, extracted_preferences, created_at FROM agent_conversations WHERE user_id = :uid ORDER BY created_at DESC"
                    ),
                    {"uid": user_id},
                ).fetchall()
                return [
                    {
                        "id": row[0],
                        "message_count": len(json.loads(row[1] or "[]")),
                        "preferences": json.loads(row[2] or "{}"),
                        "created_at": str(row[3]),
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.warning("Failed to load user conversations: %s", e)
        return []


_memory: Optional[ConversationMemory] = None


def get_conversation_memory() -> ConversationMemory:
    global _memory
    if _memory is None:
        _memory = ConversationMemory()
    return _memory
