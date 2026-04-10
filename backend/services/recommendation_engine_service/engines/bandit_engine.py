"""
Multi-Armed Bandit Engine — Thompson Sampling
===============================================
Exploration-exploitation engine that prevents filter bubbles by
maintaining Beta posterior distributions over item "arm" rewards
and sampling from them to balance showing known-good items vs
discovering potentially-good unseen items.

Based on:
  - Thompson (1933) — "On the Likelihood that One Unknown Probability
    Exceeds Another"
  - Chapelle & Li (2011) — "An Empirical Evaluation of Thompson Sampling"
  - Production best practice at Netflix, Spotify, YouTube (2025)

Why Thompson Sampling over ε-greedy or UCB?
  - ε-greedy wastes exploration budget uniformly on all arms, including
    clearly bad ones.
  - UCB is deterministic and can get stuck in adversarial settings.
  - Thompson Sampling is Bayesian, naturally calibrated, and empirically
    outperforms both in non-stationary environments like recommendation.
"""

import logging
import threading
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class BanditArm:
    """
    Represents a single arm (movie) with Beta(α, β) posterior.

    - α = number of successes (clicks, watches, high ratings) + prior
    - β = number of failures (skips, low ratings) + prior

    Prior: Beta(1, 1) = Uniform, meaning no initial bias.
    """

    __slots__ = ("alpha", "beta", "total_pulls")

    def __init__(self, alpha: float = 1.0, beta: float = 1.0):
        self.alpha = alpha
        self.beta = beta
        self.total_pulls = 0

    def sample(self) -> float:
        """Draw from the posterior Beta(α, β)."""
        return float(np.random.beta(self.alpha, self.beta))

    def update(self, reward: float) -> None:
        """Update posterior with observed reward ∈ [0, 1]."""
        self.alpha += reward
        self.beta += (1.0 - reward)
        self.total_pulls += 1

    @property
    def mean(self) -> float:
        """Posterior mean = α / (α + β)."""
        return self.alpha / (self.alpha + self.beta)

    @property
    def uncertainty(self) -> float:
        """Posterior standard deviation — high = more to explore."""
        ab = self.alpha + self.beta
        return float(np.sqrt(self.alpha * self.beta / (ab * ab * (ab + 1))))


class ThompsonSamplingEngine:
    """
    Thompson Sampling bandit for recommendation exploration.

    Each movie is an "arm" with a Beta posterior. When selecting
    candidates for a user, we sample from each arm's posterior
    and rank by sampled value. This naturally:
      - Exploits high-reward items (high α)
      - Explores uncertain items (high uncertainty)
      - Stops exploring clearly bad items (high β)

    Contextual features (genre match, quality) are used as prior
    boosts to warm-start the posteriors.
    """

    def __init__(self):
        self.arms: Dict[int, BanditArm] = {}
        self.user_arms: Dict[int, Dict[int, BanditArm]] = {}
        self._ready = False
        self._lock = threading.Lock()

    def load(self, movies_df=None) -> "ThompsonSamplingEngine":
        """Initialize arms for all movies with quality-informed priors."""
        try:
            if movies_df is None or movies_df.empty:
                logger.warning("Bandit: No movie data.")
                return self

            for _, row in movies_df.iterrows():
                movie_id = int(row.get("id", 0))
                vote_avg = float(row.get("vote_average", 5.0))
                vote_count = int(row.get("vote_count", 0))

                # Warm-start priors from movie quality
                # A movie with 8.0 avg gets Alpha=3.2, Beta=0.8 → mean=0.8
                # A movie with 5.0 avg gets Alpha=2.0, Beta=2.0 → mean=0.5
                quality_ratio = vote_avg / 10.0
                # Scale prior strength by log(vote_count) — more votes = more confident
                prior_strength = min(4.0, 1.0 + np.log1p(vote_count) / np.log1p(10000) * 3.0)

                alpha = 1.0 + quality_ratio * prior_strength
                beta = 1.0 + (1.0 - quality_ratio) * prior_strength

                self.arms[movie_id] = BanditArm(alpha, beta)

            self._ready = True
            logger.info("Bandit engine loaded (%d arms).", len(self.arms))
        except Exception as e:
            logger.error("Bandit engine load failed: %s", e)
            self._ready = False
        return self

    @property
    def is_ready(self) -> bool:
        return self._ready

    def select_arms(
        self,
        candidate_ids: List[int],
        user_id: Optional[int] = None,
        k: int = 50,
        exploration_boost: float = 1.0,
    ) -> List[Tuple[int, float]]:
        """
        Select top-k arms via Thompson Sampling.

        Returns list of (movie_id, sampled_value) sorted by sampled value.
        exploration_boost > 1.0 increases exploration (wider sampling).
        """
        if not self._ready or not candidate_ids:
            return []

        # Use per-user arms if available, else global
        user_specific = self.user_arms.get(user_id, {}) if user_id else {}

        sampled = []
        for mid in candidate_ids:
            arm = user_specific.get(mid) or self.arms.get(mid)
            if arm is None:
                # Unknown movie — use optimistic prior (encourages exploration)
                sample = float(np.random.beta(1.5, 1.0))
            else:
                # Apply exploration boost by widening the distribution
                if exploration_boost != 1.0:
                    boosted_alpha = max(1.0, arm.alpha / exploration_boost)
                    boosted_beta = max(1.0, arm.beta / exploration_boost)
                    sample = float(np.random.beta(boosted_alpha, boosted_beta))
                else:
                    sample = arm.sample()
            sampled.append((mid, sample))

        sampled.sort(key=lambda x: x[1], reverse=True)
        return sampled[:k]

    def update_reward(
        self,
        movie_id: int,
        reward: float,
        user_id: Optional[int] = None,
    ) -> None:
        """
        Update arm with observed reward.

        reward should be in [0, 1]:
          - 1.0 = user clicked/watched/rated highly
          - 0.5 = user saw but didn't engage
          - 0.0 = user actively dismissed
        """
        reward = max(0.0, min(1.0, reward))

        # Update global arm
        if movie_id in self.arms:
            self.arms[movie_id].update(reward)

        # Update per-user arm
        if user_id is not None:
            if user_id not in self.user_arms:
                self.user_arms[user_id] = {}
            if movie_id not in self.user_arms[user_id]:
                # Copy from global prior
                global_arm = self.arms.get(movie_id, BanditArm())
                self.user_arms[user_id][movie_id] = BanditArm(global_arm.alpha, global_arm.beta)
            self.user_arms[user_id][movie_id].update(reward)

    def get_exploration_candidates(
        self,
        exclude_ids: Set[int],
        k: int = 10,
        min_uncertainty: float = 0.1,
    ) -> List[int]:
        """
        Get movies that the bandit is most uncertain about (high exploration value).
        These are good candidates for "you might also like" slots.
        """
        if not self._ready:
            return []

        uncertain = [
            (mid, arm.uncertainty)
            for mid, arm in self.arms.items()
            if mid not in exclude_ids and arm.uncertainty >= min_uncertainty
        ]
        uncertain.sort(key=lambda x: x[1], reverse=True)
        return [mid for mid, _ in uncertain[:k]]

    def get_scores_for_candidates(self, candidate_ids: List[int]) -> Dict[int, float]:
        """Return posterior mean scores for candidates (deterministic scoring)."""
        if not self._ready:
            return {}
        return {
            mid: self.arms[mid].mean
            for mid in candidate_ids
            if mid in self.arms
        }


# --- Singleton ---
_engine: Optional[ThompsonSamplingEngine] = None
_lock = threading.Lock()


def get_bandit_engine() -> ThompsonSamplingEngine:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = ThompsonSamplingEngine()
    return _engine
