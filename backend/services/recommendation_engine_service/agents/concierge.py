"""
SOTA 2026 Movie Concierge Agent
===============================
Powered by Groq Llama 3 (70B) for ultra-fast reasoning.
LangGraph agent with RAG, memory, and 10 specialized tools.
"""

import json
import logging
from typing import List, Dict, Optional

from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool

from backend.services.recommendation_engine_service.engines.vector_engine import (
    get_vector_engine,
)
from backend.services.recommendation_engine_service.engines.recommendation import (
    get_engine,
)
from backend.config import GROQ_API_KEY

logger = logging.getLogger(__name__)

# --- Tool Definitions ---


@tool
def search_movies_semantic(query: str) -> str:
    """Search for movies based on plot, vibe, or semantic description.
    Use this when the user describes what the movie is about or how it feels."""
    engine = get_vector_engine()
    if not engine.is_ready:
        engine.initialize_collection()
    results = engine.search(query, k=5)
    return json.dumps(results)


@tool
def search_movies_metadata(
    genre: Optional[str] = None, director: Optional[str] = None, min_rating: float = 0.0
) -> str:
    """Search for movies by specific metadata filters (genre, director, rating)."""
    engine = get_engine()
    results, _ = engine.search_movies(
        genre=genre, director=director, min_rating=min_rating, limit=5
    )
    simplified = [
        {
            "title": m["title"],
            "director": m.get("director"),
            "rating": m["vote_average"],
            "overview": (m.get("overview") or "")[:100],
        }
        for m in results
    ]
    return json.dumps(simplified)


@tool
def get_trending_movies() -> str:
    """Get the current trending or popular movies."""
    engine = get_engine()
    results = engine.get_trending(limit=5)
    simplified = [
        {
            "title": m["title"],
            "genres": m["genres"],
            "rating": m.get("weighted_rating", m.get("vote_average")),
        }
        for m in results
    ]
    return json.dumps(simplified)


@tool
def get_movie_details(title_or_id: str) -> str:
    """Get detailed information about a specific movie by title or ID."""
    engine = get_engine()
    try:
        movie_id = int(title_or_id)
        movie = engine.get_movie_by_id(movie_id)
    except (ValueError, TypeError):
        movie = engine.find_movie(title_or_id)
    if not movie:
        return json.dumps({"error": "Movie not found"})
    return json.dumps(
        {
            k: movie[k]
            for k in [
                "title",
                "genres",
                "director",
                "cast",
                "vote_average",
                "overview",
                "release_date",
                "runtime",
            ]
            if k in movie
        }
    )


@tool
def get_recommendations_for_movie(title: str) -> str:
    """Get movies similar to a given movie title."""
    engine = get_engine()
    movie = engine.find_movie(title)
    if not movie:
        return json.dumps({"error": "Movie not found"})
    recs = engine.get_content_recommendations(movie["id"], limit=5)
    return json.dumps(
        [
            {
                "title": r["title"],
                "genres": r["genres"],
                "rating": r["vote_average"],
                "reason": r.get("reason", ""),
            }
            for r in recs
        ]
    )


@tool
def compare_movies(movie1: str, movie2: str) -> str:
    """Compare two movies side-by-side with stats."""
    engine = get_engine()
    m1 = engine.find_movie(movie1)
    m2 = engine.find_movie(movie2)
    if not m1 or not m2:
        return json.dumps({"error": "One or both movies not found"})
    fields = ["title", "genres", "director", "vote_average", "runtime", "release_date"]
    return json.dumps(
        {
            "movie1": {k: m1.get(k) for k in fields},
            "movie2": {k: m2.get(k) for k in fields},
        }
    )


@tool
def detect_mood_and_recommend(mood_text: str) -> str:
    """Detect user's mood from text and recommend matching movies."""
    try:
        from backend.services.recommendation_engine_service.engines.mood_engine import (
            get_mood_engine,
        )

        mood_engine = get_mood_engine()
        rec_engine = get_engine()
        results = mood_engine.get_mood_recommendations(
            mood_text, rec_engine.movies_df, limit=5
        )
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_user_taste_profile(user_id: int) -> str:
    """Get a user's taste profile computed from their ratings."""
    engine = get_engine()
    if engine.ratings_df is None or engine.movies_df is None:
        return json.dumps({"error": "No data available"})
    user_ratings = engine.ratings_df[engine.ratings_df["user_id"] == user_id]
    if len(user_ratings) == 0:
        return json.dumps({"error": "No ratings found for user"})
    genre_scores = {}
    for _, row in user_ratings.iterrows():
        movie = engine.get_movie_by_id(int(row["movie_id"]))
        if movie and movie.get("genres"):
            genres_val = movie["genres"]
            if isinstance(genres_val, list):
                genre_list = genres_val
            elif isinstance(genres_val, str) and "|" in genres_val:
                genre_list = [g.strip() for g in genres_val.split("|") if g.strip()]
            else:
                genre_list = [g.strip() for g in str(genres_val).split() if g.strip()]
            for genre in genre_list:
                genre_scores.setdefault(genre, []).append(float(row["rating"]))
    profile = {
        g: round(sum(s) / len(s), 1)
        for g, s in sorted(genre_scores.items(), key=lambda x: -sum(x[1]) / len(x[1]))[
            :8
        ]
    }
    return json.dumps(
        {
            "user_id": user_id,
            "genre_preferences": profile,
            "total_ratings": len(user_ratings),
        }
    )


@tool
def find_movie_connections(movie1: str, movie2: str) -> str:
    """Find connections between two movies via shared cast/crew/genres."""
    try:
        from backend.services.recommendation_engine_service.engines.knowledge_graph import (
            get_knowledge_graph,
        )

        kg = get_knowledge_graph()
        paths = kg.find_paths(movie1, movie2)
        return json.dumps({"paths": paths[:3]})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def create_mood_playlist(mood: str, count: int = 5) -> str:
    """Create a movie playlist matching a specific mood."""
    try:
        from backend.services.recommendation_engine_service.engines.mood_engine import (
            get_mood_engine,
        )

        mood_engine = get_mood_engine()
        rec_engine = get_engine()
        results = mood_engine.get_mood_recommendations(
            mood, rec_engine.movies_df, limit=count
        )
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": str(e)})


class MovieAgent:
    def __init__(self):
        self.tools = [
            search_movies_semantic,
            search_movies_metadata,
            get_trending_movies,
            get_movie_details,
            get_recommendations_for_movie,
            compare_movies,
            detect_mood_and_recommend,
            get_user_taste_profile,
            find_movie_connections,
            create_mood_playlist,
        ]

        api_key = GROQ_API_KEY
        if not api_key:
            logger.warning("GROQ_API_KEY not found. Concierge will use mock responses.")
            self.llm = None
            self.agent_executor = None
        else:
            self.llm = ChatGroq(
                groq_api_key=api_key,
                model_name="llama-3.3-70b-versatile",
                temperature=0.2,
            )
            self.agent_executor = create_react_agent(
                self.llm, self.tools, prompt=self._system_message()
            )

    @staticmethod
    def _system_message() -> str:
        return (
            "You are an elite movie concierge AI from 2026. "
            "Your goal is to find the perfect movie for the user. "
            "You have 10 tools available:\n"
            "1. search_movies_semantic — vector/vibe search\n"
            "2. search_movies_metadata — genre/director/rating filters\n"
            "3. get_trending_movies — current popular movies\n"
            "4. get_movie_details — detailed info on a specific movie\n"
            "5. get_recommendations_for_movie — similar movies\n"
            "6. compare_movies — side-by-side comparison\n"
            "7. detect_mood_and_recommend — mood-based recommendations\n"
            "8. get_user_taste_profile — user taste analysis\n"
            "9. find_movie_connections — connections between movies\n"
            "10. create_mood_playlist — curated mood playlist\n\n"
            "Use the right tool for each query. Explain WHY you chose each movie. "
            "Be passionate about cinema, helpful, and conversational."
        )

    def _create_mock_response(self, query: str) -> Dict:
        return {
            "output": f"I understood you're looking for '{query}'. To unlock my full SOTA potential, please set the GROQ_API_KEY environment variable. In the meantime, I recommend 'The Matrix'!"
        }

    def run(
        self,
        query: str,
        chat_history: Optional[List[Dict]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict:
        if not self.llm:
            return self._create_mock_response(query)
        history = chat_history or []

        # RAG: retrieve context for grounding
        rag_context = ""
        try:
            from backend.services.recommendation_engine_service.agents.rag import (
                get_rag_retriever,
            )

            retriever = get_rag_retriever()
            rag_context = retriever.retrieve(query, k=5)
        except Exception:
            pass

        # Memory: save turn and load preferences
        preferences = {}
        if session_id:
            try:
                from backend.services.recommendation_engine_service.agents.memory import (
                    get_conversation_memory,
                )

                memory = get_conversation_memory()
                memory.save_turn(session_id, user_id, "user", query)
                preferences = memory.get_preferences(session_id)
            except Exception:
                pass

        # Build messages
        messages = []

        # Prepend RAG context if available
        if rag_context:
            messages.append(
                SystemMessage(
                    content=f"Relevant movies from our database:\n{rag_context}"
                )
            )

        if preferences:
            pref_str = json.dumps(preferences)
            messages.append(
                SystemMessage(
                    content=f"User preferences from prior conversation: {pref_str}"
                )
            )

        for turn in history:
            role = turn.get("role")
            content = turn.get("content")
            if role == "user":
                messages.append(HumanMessage(content=str(content)))
            elif role in ["assistant", "agent"]:
                messages.append(AIMessage(content=str(content)))

        messages.append(HumanMessage(content=str(query)))

        try:
            final_state = self.agent_executor.invoke({"messages": messages})
            response_message = final_state["messages"][-1]

            intermediate_steps = []
            for m in final_state["messages"]:
                if hasattr(m, "tool_calls") and m.tool_calls:
                    for tc in m.tool_calls:
                        intermediate_steps.append(
                            {"tool": tc["name"], "input": tc["args"]}
                        )

            # Save assistant response to memory
            if session_id:
                try:
                    from backend.services.recommendation_engine_service.agents.memory import (
                        get_conversation_memory,
                    )

                    memory = get_conversation_memory()
                    memory.save_turn(
                        session_id, user_id, "assistant", response_message.content
                    )
                    memory.extract_preferences(session_id)
                except Exception:
                    pass

            return {
                "output": response_message.content,
                "intermediate_steps": intermediate_steps,
            }
        except Exception as e:
            logger.exception("Agent error: %s", e)
            return {
                "output": f"I encountered an error processing your request: {str(e)}"
            }


# Singleton
_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = MovieAgent()
    return _agent
