"""
SOTA 2026 Movie Concierge Agent
===============================
Powered by Groq Llama 3 (70B) for ultra-fast reasoning.
Refactored to use LangGraph (modern standard) replacing legacy AgentExecutor.
"""

import json
import logging
from typing import List, Dict, Optional

from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage
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
    """
    Search for movies based on plot, vibe, or semantic description.
    Use this when the user describes *what* the movie is about or how it feels.
    Example: "movies about time travel", "heartbreaking dramas"
    """
    engine = get_vector_engine()
    # Ensure index is built/loaded (in prod this would be async/pre-loaded)
    if not engine.is_ready:
        engine.initialize_collection()

    results = engine.search(query, k=5)
    return json.dumps(results)


@tool
def search_movies_metadata(
    genre: Optional[str] = None, director: Optional[str] = None, min_rating: float = 0.0
) -> str:
    """
    Search for movies based on specific metadata filters.
    Use this when the user specifies explicit criteria.
    """
    engine = get_engine()
    results, _ = engine.search_movies(
        genre=genre, director=director, min_rating=min_rating, limit=5
    )
    # Simplify output for the LLM
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


class MovieAgent:
    def __init__(self):
        self.tools = [
            search_movies_semantic,
            search_movies_metadata,
            get_trending_movies,
        ]

        # SOTA: Groq API with Llama 3 70B
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
                self.llm, self.tools, messages_modifier=self._system_message()
            )

    @staticmethod
    def _system_message() -> str:
        return (
            "You are an elite movie concierge AI from 2026. "
            "Your goal is to find the perfect movie for the user. "
            "You have access to semantic search (vector db) and metadata search. "
            "Don't just list titles; explain WHY you chose them based on the user's mood. "
            "If the user asks for something vague, use semantic search. "
            "If they ask for specific genres/directors, use metadata search. "
            "Always be helpful, professional, and passionate about cinema."
        )

    def _create_mock_response(self, query: str) -> Dict:
        """Fallback for when no API key is present."""
        return {
            "output": f"I understood you're looking for '{query}'. To unlock my full SOTA potential, please set the GROQ_API_KEY environment variable. In the meantime, I recommend 'The Matrix'!"
        }

    def run(self, query: str, chat_history: Optional[List[Dict]] = None) -> Dict:
        if not self.llm:
            return self._create_mock_response(query)
        history = chat_history or []

        # Prepare messages including history
        messages = []
        for turn in history:
            role = turn.get("role")
            content = turn.get("content")
            if role == "user":
                messages.append(HumanMessage(content=str(content)))
            elif role in ["assistant", "agent"]:
                messages.append(AIMessage(content=str(content)))

        # Add current query
        messages.append(HumanMessage(content=str(query)))

        try:
            # invoke returns the final state
            final_state = self.agent_executor.invoke({"messages": messages})

            # The last message is the AI response
            response_message = final_state["messages"][-1]

            # Extract intermediate steps (tool calls) if possible for metadata
            intermediate_steps = []
            for m in final_state["messages"]:
                if hasattr(m, "tool_calls") and m.tool_calls:
                    for tc in m.tool_calls:
                        intermediate_steps.append(
                            {"tool": tc["name"], "input": tc["args"]}
                        )

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
