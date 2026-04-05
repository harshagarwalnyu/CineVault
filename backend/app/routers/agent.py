"""AI Agent / Chat endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.schemas import AgentInput

router = APIRouter()


class AgenticDiscoveryInput(BaseModel):
    query: str


@router.post("/agent/chat", tags=["AI Agent"])
async def chat_with_agent(payload: AgentInput):
    from backend.services.recommendation_engine_service.agents.concierge import get_agent

    agent = get_agent()
    response = agent.run(payload.input, payload.chat_history)
    return {
        "response": response.get("output", "Sorry, I couldn't generate a response."),
        "metadata": response.get("intermediate_steps", []),
    }


@router.post("/api/v1/discovery/agentic", tags=["AI Agent"])
async def agentic_discovery_endpoint(payload: AgenticDiscoveryInput):
    from backend.services.graphrag import GraphRAGService

    service = GraphRAGService()
    return await service.agentic_discovery(payload.query)
