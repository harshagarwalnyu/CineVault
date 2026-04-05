from google import genai
from google.genai import types
import json
from pydantic import BaseModel

from backend.config import settings
from backend.surreal_db import get_surreal_db

class IntentAnalysis(BaseModel):
    core_theme: str
    mood: str
    pacing: str
    target_tropes: list[str]

class GraphRAGService:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

    async def _analyze_intent(self, user_query: str) -> IntentAnalysis:
        prompt = f"""
        You are an expert movie analyst. Break down the user's vague query into searchable tropes and moods.
        Query: "{user_query}"
        
        Extract the core theme, the desired mood, pacing, and 2-3 specific movie 'tropes' that match this.
        """
        response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=IntentAnalysis,
            ),
        )
        return IntentAnalysis(**json.loads(response.text))

    async def _vector_search_tropes(self, tropes: list[str]) -> list[str]:
        """Find the closest tropes in SurrealDB based on the extracted intent."""
        db = await get_surreal_db()
        matched_tropes = []
        
        # Here we would do a vector search against the 'trope' table in SurrealDB
        # For simplicity in this moat demo, we'll do a semantic-like text search 
        # or just exact matching if vector indices aren't fully populated yet.
        for t in tropes:
            # Simplified search for demonstration
            result = await db.query(
                "SELECT id, name FROM trope WHERE string::lowercase(name) CONTAINS $t LIMIT 3;",
                {"t": t.lower()}
            )
            if result and len(result) > 0 and result[0]['result']:
                matched_tropes.extend([r['id'] for r in result[0]['result']])
                
        return list(set(matched_tropes))

    async def agentic_discovery(self, query: str):
        """
        The core of the Uncopyable Moat: Agent-Mediated Ecosystem Orchestration via GraphRAG.
        """
        if not self.client:
            return {"error": "Gemini API key not configured."}
            
        # 1. LLM breaks down the vague intent
        intent = await self._analyze_intent(query)
        
        # 2. Map intent to our proprietary Graph nodes (Tropes)
        matched_trope_ids = await self._vector_search_tropes(intent.target_tropes + [intent.mood])
        
        db = await get_surreal_db()
        
        if not matched_trope_ids:
            # Fallback if no exact tropes matched
            return {
                "intent": intent.model_dump(),
                "recommendations": [],
                "reasoning": "Could not map query to proprietary graph nodes."
            }

        # 3. Traverse the Graph (Trope -> Movie) to find movies matching multiple tropes
        # In SurrealDB, we query movies that have relations to these tropes.
        # `<-has_trope<-movie` traverses from trope back to movie.
        
        # We want movies that connect to the most matched tropes.
        trope_id_list = ", ".join([f"'{tid}'" for tid in matched_trope_ids])
        
        # A powerful SurrealQL graph traversal:
        # Find movies connected to these tropes, aggregate their confidence, and return the top matches.
        graph_query = f"""
        SELECT 
            in AS movie, 
            count() AS matched_tropes,
            math::sum(confidence) AS total_confidence
        FROM has_trope
        WHERE out IN [{trope_id_list}]
        GROUP BY movie
        ORDER BY matched_tropes DESC, total_confidence DESC
        LIMIT 5;
        """
        
        results = await db.query(graph_query)
        
        if not results or not results[0]['result']:
            return {
                "intent": intent.model_dump(),
                "recommendations": [],
                "reasoning": "Found tropes but no strongly connected movies."
            }
            
        # 4. Hydrate the movie details and explain the reasoning (Self-Explaining UI)
        from backend.services.availability import AvailabilityAgent
        availability_agent = AvailabilityAgent()
        
        recommendations = []
        for r in results[0]['result']:
            movie_id = r['movie']
            
            # Fetch movie details and the specific edges (explanations) that connected it
            movie_data = await db.query(
                f"SELECT title, overview, popularity FROM {movie_id};"
            )
            
            edges_data = await db.query(
                f"SELECT out.name AS trope, explanation FROM has_trope WHERE in = {movie_id} AND out IN [{trope_id_list}];"
            )
            
            if movie_data and movie_data[0]['result']:
                m = movie_data[0]['result'][0]
                reasons = edges_data[0]['result'] if edges_data and edges_data[0]['result'] else []
                
                recommendations.append({
                    "title": m['title'],
                    "overview": m['overview'],
                    "match_score": r['total_confidence'],
                    "why_you_will_like_it": reasons  # The explainability payload
                })
                
        # 5. Agentic Ecosystem Filtering
        # The Moat: We only show movies the user can actually watch *right now* with a zero-click link.
        accessible_recommendations = await availability_agent.filter_accessible_only(recommendations)
        
        # 6. Generative 'Liquid' UI State
        # Determine how the frontend should render the response based on the cognitive load of the query
        ui_state = "comparison_grid"
        if len(query.split()) < 4 or len(accessible_recommendations) == 1:
            ui_state = "single_focus_hero" # User is likely tired or very specific, show them ONE thing to click
        elif len(accessible_recommendations) <= 3:
            ui_state = "detail_cards" # Moderate engagement
                
        return {
            "intent_understood": intent.model_dump(),
            "graph_nodes_activated": matched_trope_ids,
            "ui_state": ui_state,
            "recommendations": accessible_recommendations
        }
