"""
Multi-Objective Ranker — Shared-Bottom Multi-Task Learning
===========================================================
Jointly predicts multiple recommendation objectives:
  1. Watch probability (P(click))
  2. Expected rating
  3. Engagement score (time spent / expected engagement)

Based on:
  - Ma et al. (2018) — "Modeling Task Relationships in Multi-Task Learning
    with Multi-Gate Mixture-of-Experts" (MMoE, Google/YouTube)
  - Zhao et al. (2019) — "Recommending What Video to Watch Next: A
    Multitask Ranking System" (YouTube production paper)
  - Tang et al. (2025) — "Progressive Multi-Task Learning for Recommendation"

Architecture: Shared-Bottom MTL
  Input features → Shared MLP → Task-specific MLP heads → Task outputs

Why MTL over single-objective?
  - Single objective (e.g., click prediction) creates clickbait bias.
  - MTL balances: "will they click?" + "will they enjoy it?" + "will they
    watch the whole thing?" — producing genuinely satisfying recommendations.
  - YouTube, TikTok, and Netflix all use MTL in production (2025).
"""

import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)

MODEL_PATH = Path("data/models/multiobjective.pt")

# Feature dimensions (must match extraction)
GENRE_VOCAB = [
    "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary",
    "Drama", "Family", "Fantasy", "History", "Horror", "Music", "Mystery",
    "Romance", "Science Fiction", "Thriller", "TV Movie", "War", "Western",
]
NUM_GENRES = len(GENRE_VOCAB)
# genres(19) + vote_avg(1) + vote_count_log(1) + popularity_log(1) + decade(1)
# + runtime(1) + lang_hash(1) + budget_log(1) + revenue_log(1) = 27
ITEM_FEATURE_DIM = NUM_GENRES + 8


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def _safe_float(val, default: float = 0.0) -> float:
    """Safely convert value to float, returning default for NaN/None/non-numeric."""
    try:
        f = float(val)
        return f if np.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def extract_item_features(row) -> np.ndarray:
    """Extract feature vector from a movie DataFrame row."""
    genre_vec = np.zeros(NUM_GENRES, dtype=np.float32)
    genres_str = str(row.get("genres", ""))
    for i, g in enumerate(GENRE_VOCAB):
        if g.lower() in genres_str.lower():
            genre_vec[i] = 1.0

    vote_avg = np.clip(_safe_float(row.get("vote_average", 5.0)) / 10.0, 0.0, 1.0)
    vote_count = np.log1p(_safe_float(row.get("vote_count", 0))) / np.log1p(50000)
    popularity = np.log1p(_safe_float(row.get("popularity", 0))) / np.log1p(1000)
    year = _safe_float(row.get("release_year", row.get("year", 2000)), 2000)
    decade = np.clip((year - 1900) / 130.0, 0.0, 1.0)
    runtime = np.clip(min(_safe_float(row.get("runtime", 100), 100), 300) / 300.0, 0.0, 1.0)
    lang_hash = (hash(str(row.get("original_language", "en"))) % 100) / 100.0
    budget = np.log1p(_safe_float(row.get("budget", 0))) / np.log1p(3e8)
    revenue = np.log1p(_safe_float(row.get("revenue", 0))) / np.log1p(3e9)

    feats = np.concatenate([genre_vec, [vote_avg, vote_count, popularity, decade, runtime, lang_hash, budget, revenue]])
    # Ensure no NaN/Inf — replace with 0
    return np.nan_to_num(feats, nan=0.0, posinf=1.0, neginf=0.0).astype(np.float32)


# ---------------------------------------------------------------------------
# Shared-Bottom Multi-Task Model
# ---------------------------------------------------------------------------

class SharedBottomMTL(nn.Module):
    """
    Shared-Bottom Multi-Task Learning architecture.

    Shared layers learn common representations, then task-specific
    towers specialise for each objective.

    This is simpler than MMoE (Mixture of Experts) but works well
    when tasks are positively correlated — which they are for
    watch/rate/engage in movie recommendations.
    """

    def __init__(self, input_dim: int = ITEM_FEATURE_DIM, hidden_dim: int = 256):
        super().__init__()

        # Shared bottom network
        self.shared = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, 128),
            nn.ReLU(),
        )

        # Task 1: Watch probability (binary)
        self.watch_tower = nn.Sequential(
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

        # Task 2: Expected rating (regression, [0, 1] normalised)
        self.rating_tower = nn.Sequential(
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

        # Task 3: Engagement score (regression, [0, 1])
        self.engagement_tower = nn.Sequential(
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Returns (watch_prob, rating_pred, engagement_pred), each (B, 1).
        """
        shared_repr = self.shared(x)
        watch = self.watch_tower(shared_repr)
        rating = self.rating_tower(shared_repr)
        engagement = self.engagement_tower(shared_repr)
        return watch, rating, engagement

    def get_shared_embedding(self, x: torch.Tensor) -> torch.Tensor:
        """Get the shared-bottom representation (for downstream use)."""
        return self.shared(x)


class MTLLoss(nn.Module):
    """
    Uncertainty-weighted multi-task loss (Kendall et al. 2018).

    Instead of hand-tuning task weights, learns them from data via
    homoscedastic uncertainty: L = Σ (1/2σ²_i) L_i + log(σ_i)
    """

    def __init__(self, num_tasks: int = 3):
        super().__init__()
        # log(σ²) initialised to 0 → σ = 1 → equal weights initially
        self.log_vars = nn.Parameter(torch.zeros(num_tasks))

    def forward(self, losses: List[torch.Tensor]) -> torch.Tensor:
        total = torch.tensor(0.0, device=losses[0].device)
        for i, loss in enumerate(losses):
            precision = torch.exp(-self.log_vars[i])
            total = total + precision * loss + self.log_vars[i]
        return total


# ---------------------------------------------------------------------------
# Multi-Objective Engine
# ---------------------------------------------------------------------------

class MultiObjectiveEngine:
    """
    Serving wrapper for the Multi-Task Learning ranker.

    Scores candidate movies on 3 dimensions and combines them into
    a single "expected value" score:

      EV = w_watch × P(watch) + w_rating × E[rating] + w_engage × E[engagement]

    Default weights: 0.3, 0.5, 0.2 (Netflix-style: prioritise satisfaction
    over clicks).
    """

    def __init__(self):
        self.model: Optional[SharedBottomMTL] = None
        self.movie_features: Dict[int, np.ndarray] = {}
        self._ready = False
        self._lock = threading.Lock()

    def load(self, movies_df: Optional[pd.DataFrame] = None) -> "MultiObjectiveEngine":
        """Load model and pre-extract movie features."""
        try:
            if movies_df is None or movies_df.empty:
                logger.warning("Multi-Objective: No movie data.")
                return self

            # Extract features for all movies
            for _, row in movies_df.iterrows():
                movie_id = int(row.get("id", 0))
                self.movie_features[movie_id] = extract_item_features(row)

            self.model = SharedBottomMTL()

            if MODEL_PATH.exists():
                state = torch.load(MODEL_PATH, map_location="cpu", weights_only=True)
                self.model.load_state_dict(state)
                logger.info("Multi-Objective model loaded from %s", MODEL_PATH)
            else:
                # Train on proxy labels derived from movie metadata
                self._train_on_proxy_labels(movies_df)

            self.model.eval()
            self._ready = True
            logger.info("Multi-Objective engine loaded (%d movies).", len(self.movie_features))
        except Exception as e:
            logger.error("Multi-Objective engine load failed: %s", e)
            self._ready = False
        return self

    def _train_on_proxy_labels(self, movies_df: pd.DataFrame, epochs: int = 15, batch_size: int = 256) -> None:
        """
        Train on proxy labels derived from metadata when no real user data exists.

        Proxy labels:
          - watch_prob: f(popularity, vote_count) — popular movies get watched more
          - rating: vote_average / 10
          - engagement: f(runtime, vote_avg, vote_count) — good long movies = high engagement
        """
        logger.info("Multi-Objective: Training on proxy labels for %d movies...", len(movies_df))

        features_list = []
        watch_labels = []
        rating_labels = []
        engagement_labels = []

        for _, row in movies_df.iterrows():
            feat = extract_item_features(row)
            features_list.append(feat)

            pop = _safe_float(row.get("popularity", 0))
            vc = _safe_float(row.get("vote_count", 0))
            va = _safe_float(row.get("vote_average", 5.0), 5.0)
            runtime = _safe_float(row.get("runtime", 100), 100)

            # Proxy watch probability: sigmoid of log(popularity), clamped to (0, 1)
            watch = 1.0 / (1.0 + np.exp(-np.log1p(pop) / 2 + 2))
            watch_labels.append(np.clip(watch, 0.01, 0.99))

            # Proxy rating, clamped to (0, 1)
            rating_labels.append(np.clip(va / 10.0, 0.01, 0.99))

            # Proxy engagement: good + long movies → high engagement
            quality = va / 10.0
            length_factor = min(runtime / 120.0, 1.5) / 1.5
            engagement = quality * 0.7 + length_factor * 0.2 + min(vc / 10000, 1.0) * 0.1
            engagement_labels.append(np.clip(engagement, 0.01, 0.99))

        X = torch.tensor(np.array(features_list), dtype=torch.float32)
        y_watch = torch.tensor(watch_labels, dtype=torch.float32).unsqueeze(1)
        y_rating = torch.tensor(rating_labels, dtype=torch.float32).unsqueeze(1)
        y_engage = torch.tensor(engagement_labels, dtype=torch.float32).unsqueeze(1)

        self.model.train()
        mtl_loss = MTLLoss(num_tasks=3)
        optimizer = torch.optim.AdamW(
            list(self.model.parameters()) + list(mtl_loss.parameters()),
            lr=1e-3, weight_decay=1e-4,
        )
        n = len(features_list)

        for epoch in range(epochs):
            perm = torch.randperm(n)
            total_loss = 0.0
            batches = 0

            for i in range(0, n, batch_size):
                idx = perm[i:i + batch_size]
                pred_w, pred_r, pred_e = self.model(X[idx])

                # Clamp predictions to valid BCE range
                pred_w = pred_w.clamp(1e-6, 1.0 - 1e-6)
                pred_r = pred_r.clamp(1e-6, 1.0 - 1e-6)
                pred_e = pred_e.clamp(1e-6, 1.0 - 1e-6)

                loss_w = F.binary_cross_entropy(pred_w, y_watch[idx])
                loss_r = F.mse_loss(pred_r, y_rating[idx])
                loss_e = F.mse_loss(pred_e, y_engage[idx])

                loss = mtl_loss([loss_w, loss_r, loss_e])

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                total_loss += loss.item()
                batches += 1

            if (epoch + 1) % 5 == 0:
                logger.info("MTL epoch %d/%d — loss: %.4f", epoch + 1, epochs, total_loss / max(batches, 1))

        self.model.eval()
        logger.info("Multi-Objective: Proxy training complete.")

    @property
    def is_ready(self) -> bool:
        return self._ready

    def score(
        self,
        movie_id: int,
        w_watch: float = 0.3,
        w_rating: float = 0.5,
        w_engage: float = 0.2,
    ) -> Dict[str, float]:
        """
        Score a single movie on all 3 objectives.

        Returns dict with watch_prob, rating_pred, engagement_pred, and combined ev_score.
        """
        if not self._ready or self.model is None:
            return {"ev_score": 0.0, "watch_prob": 0.0, "rating_pred": 0.0, "engagement_pred": 0.0}

        feat = self.movie_features.get(movie_id)
        if feat is None:
            return {"ev_score": 0.0, "watch_prob": 0.0, "rating_pred": 0.0, "engagement_pred": 0.0}

        with torch.no_grad():
            x = torch.tensor(feat, dtype=torch.float32).unsqueeze(0)
            watch, rating, engagement = self.model(x)

            wp = float(watch.item())
            rp = float(rating.item())
            ep = float(engagement.item())

            ev = w_watch * wp + w_rating * rp + w_engage * ep

            return {
                "ev_score": round(ev, 4),
                "watch_prob": round(wp, 4),
                "rating_pred": round(rp, 4),
                "engagement_pred": round(ep, 4),
            }

    def score_batch(
        self,
        movie_ids: List[int],
        w_watch: float = 0.3,
        w_rating: float = 0.5,
        w_engage: float = 0.2,
    ) -> Dict[int, Dict[str, float]]:
        """Score a batch of movies efficiently."""
        if not self._ready or self.model is None:
            return {}

        valid_ids = [mid for mid in movie_ids if mid in self.movie_features]
        if not valid_ids:
            return {}

        features = np.array([self.movie_features[mid] for mid in valid_ids], dtype=np.float32)

        with torch.no_grad():
            x = torch.tensor(features, dtype=torch.float32)
            watch, rating, engagement = self.model(x)

            results = {}
            for i, mid in enumerate(valid_ids):
                wp = float(watch[i].item())
                rp = float(rating[i].item())
                ep = float(engagement[i].item())
                ev = w_watch * wp + w_rating * rp + w_engage * ep
                results[mid] = {
                    "ev_score": round(ev, 4),
                    "watch_prob": round(wp, 4),
                    "rating_pred": round(rp, 4),
                    "engagement_pred": round(ep, 4),
                }
            return results


# --- Singleton ---
_engine: Optional[MultiObjectiveEngine] = None
_lock = threading.Lock()


def get_multiobjective_engine() -> MultiObjectiveEngine:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = MultiObjectiveEngine()
    return _engine
