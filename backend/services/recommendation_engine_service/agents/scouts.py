"""
NEBULA Scout Swarm
==================
Autonomous agents that simulate user reactions using Active Inference.
"""

import numpy as np
from typing import Dict, Any, List


class ScoutAgent:
    """Base class for Scout Agents in the Swarm."""

    def __init__(self, name: str):
        self.name = name

    def simulate(self, user_model: Dict[str, Any], movie_dna: np.ndarray) -> float:
        """
        Simulate user reaction and return a score.
        In Project NEBULA, this calculates Expected Information Gain (EIG)
        or predicted reward based on the POMDP state.
        """
        raise NotImplementedError


class ScoutAlpha(ScoutAgent):
    """
    Scout Alpha: Exploitation
    Focuses on safe, high-probability hits based on known preferences.
    """

    def __init__(self):
        super().__init__("Scout Alpha (Exploitation)")

    def simulate(self, user_model: Dict[str, Any], movie_dna: np.ndarray) -> float:
        # Simple dot product between user preference vector and movie DNA
        # In a real scenario, this would involve a complex POMDP belief update
        user_pref = user_model.get("preference_vector", np.zeros_like(movie_dna))
        return float(np.dot(user_pref, movie_dna))


class ScoutBeta(ScoutAgent):
    """
    Scout Beta: Exploration
    Looks for high-entropy (risky) choices to learn more about the user.
    """

    def __init__(self):
        super().__init__("Scout Beta (Exploration)")

    def simulate(self, user_model: Dict[str, Any], movie_dna: np.ndarray) -> float:
        # Higher score for DNA vectors that are "far" from the current user model
        # Maximize Expected Information Gain (EIG)
        user_pref = user_model.get("preference_vector", np.zeros_like(movie_dna))
        distance = np.linalg.norm(user_pref - movie_dna)
        # We want a balance: not too far to be irrelevant, but far enough to be novel
        # Simple novelty score
        return float(distance)


class ScoutSwarm:
    """Coordinates multiple scouts to reach a consensus."""

    def __init__(self):
        self.scouts = [ScoutAlpha(), ScoutBeta()]

    def get_consensus_recommendation(
        self, user_model: Dict[str, Any], candidates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Evaluates candidates across all scouts and returns the winner."""
        scored_candidates = []

        for candidate in candidates:
            dna = np.array(candidate.get("dna_vector", []))
            if dna.size == 0:
                continue

            # Weighted average: Alpha (Exploitation) 0.7, Beta (Exploration) 0.3
            score_a = self.scouts[0].simulate(user_model, dna)
            score_b = self.scouts[1].simulate(user_model, dna)
            total_score = (0.7 * score_a) + (0.3 * score_b)

            candidate.update(
                {
                    "swarm_score": total_score,
                    "scout_breakdown": {"alpha": score_a, "beta": score_b},
                }
            )
            scored_candidates.append(candidate)

        if not scored_candidates:
            return {}

        return max(scored_candidates, key=lambda x: x["swarm_score"])
