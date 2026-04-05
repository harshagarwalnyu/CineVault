"""
NEBULA Manager Agent
====================
Orchestrator for the Agent Swarm. Coordinates ingestion and recommendation.
"""

import logging
import numpy as np
from typing import Dict, Any
from backend.agents.ingestion import IngestionAgent
from backend.agents.scouts import ScoutSwarm
from backend.services.recommendation_engine_service.engines.vector_engine import (
    get_vector_engine,
)

logger = logging.getLogger(__name__)


class ManagerAgent:
    def __init__(self):
        self.ingestion_agent = IngestionAgent()
        self.swarm = ScoutSwarm()
        self.vector_engine = get_vector_engine()

    def run_maintenance(self):
        """Triggers periodic ingestion and optimization."""
        logger.info("Manager: Starting maintenance cycle...")
        self.ingestion_agent.process_batch(limit=100)
        logger.info("Manager: Maintenance complete.")

    def get_recommendation(self, user_query: str, user_id: int) -> Dict[str, Any]:
        """
        End-to-end recommendation flow using the Swarm.
        1. Semantic Search for candidates.
        2. Swarm simulation (Active Inference).
        3. Consensus selection.
        """
        logger.info(f"Manager: Generating recommendation for user {user_id}...")

        # Step 1: Get initial candidates from DNA manifold
        # For simplicity, we search the DNA manifold using the text query
        # (In NEBULA, this would involve VAE interpolation)
        collection_name = "nebula_dna_manifold"

        # Map text query to a vector (using standard model for now,
        # later use LRM to map to latent space)
        standard_engine = self.vector_engine
        query_vector = list(
            standard_engine.model.embed([f"search_query: {user_query}"])
        )[0].tolist()

        try:
            hits = standard_engine.client.query_points(
                collection_name=collection_name, query=query_vector, limit=20
            ).points
        except Exception:
            # Fallback if NEBULA collection isn't ready
            logger.warning(
                "NEBULA manifold not ready, falling back to standard search."
            )
            return {"fallback": True, "results": standard_engine.search(user_query)}

        candidates = [
            {
                "id": hit.payload["id"],
                "title": hit.payload["title"],
                "dna_vector": hit.vector,
            }
            for hit in hits
        ]

        # Step 2: Simulate with Swarm
        # Mock user model for now
        user_model = {
            "id": user_id,
            "preference_vector": np.random.rand(len(candidates[0]["dna_vector"]))
            if candidates
            else [],
        }

        winner = self.swarm.get_consensus_recommendation(user_model, candidates)

        return {"recommendation": winner, "method": "NEBULA Agent SwarmConsensus"}


if __name__ == "__main__":
    manager = ManagerAgent()
    # manager.run_maintenance()
