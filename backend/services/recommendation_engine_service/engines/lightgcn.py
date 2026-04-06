"""
LightGCN Graph Collaborative Filtering Engine
===============================================
3-layer LightGCN with 64-dim embeddings, sum aggregation, BPR loss.
Pure PyTorch implementation (no torch-geometric dependency).
"""

import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from backend.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 64
NUM_LAYERS = 3
MODEL_PATH = Path("data/models/lightgcn.pt")


def build_norm_adj(
    num_users: int,
    num_items: int,
    user_indices: np.ndarray,
    item_indices: np.ndarray,
) -> torch.sparse.FloatTensor:
    """
    Build the normalised bipartite adjacency matrix as a sparse tensor.

    The full adjacency is:
        A = [[0, R], [R^T, 0]]
    Normalised: D^{-1/2} A D^{-1/2}

    Parameters
    ----------
    num_users, num_items : int
    user_indices, item_indices : arrays of interactions (same length)

    Returns
    -------
    Sparse (num_users + num_items) x (num_users + num_items) tensor.
    """
    n = num_users + num_items
    # Offset item indices into the combined space
    item_offset = item_indices + num_users

    # Build symmetric edges: user->item and item->user
    rows = np.concatenate([user_indices, item_offset])
    cols = np.concatenate([item_offset, user_indices])

    # Degree vector
    degree = np.zeros(n, dtype=np.float32)
    np.add.at(degree, rows, 1)
    # D^{-1/2}
    d_inv_sqrt = np.where(degree > 0, np.power(degree, -0.5), 0.0)

    # Normalised values
    values = d_inv_sqrt[rows] * d_inv_sqrt[cols]

    indices = torch.tensor(np.stack([rows, cols]), dtype=torch.long)
    values = torch.tensor(values, dtype=torch.float32)
    return torch.sparse_coo_tensor(indices, values, (n, n)).coalesce()


class LightGCNModel(nn.Module):
    """
    LightGCN: Simplifying and Powering Graph Convolution Network for Recommendation (He et al. 2020).

    - No feature transformation per layer (per paper).
    - Final embedding = mean of layer-0..layer-K embeddings.
    """

    def __init__(self, num_users: int, num_items: int, embed_dim: int = EMBEDDING_DIM, num_layers: int = NUM_LAYERS):
        super().__init__()
        self.num_users = num_users
        self.num_items = num_items
        self.num_layers = num_layers

        self.user_embedding = nn.Embedding(num_users, embed_dim)
        self.item_embedding = nn.Embedding(num_items, embed_dim)

        nn.init.xavier_uniform_(self.user_embedding.weight)
        nn.init.xavier_uniform_(self.item_embedding.weight)

    def forward(self, adj: torch.sparse.FloatTensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Propagate and return final user/item embeddings.

        Returns (user_embeddings, item_embeddings), each shape (N, embed_dim).
        """
        ego = torch.cat([self.user_embedding.weight, self.item_embedding.weight], dim=0)
        all_embs = [ego]
        x = ego
        for _ in range(self.num_layers):
            x = torch.sparse.mm(adj, x)
            all_embs.append(x)

        stacked = torch.stack(all_embs, dim=0)
        final = stacked.mean(dim=0)
        user_embs = final[: self.num_users]
        item_embs = final[self.num_users:]
        return user_embs, item_embs

    def bpr_loss(
        self,
        adj: torch.sparse.FloatTensor,
        user_ids: torch.Tensor,
        pos_ids: torch.Tensor,
        neg_ids: torch.Tensor,
        reg_weight: float = 1e-4,
    ) -> torch.Tensor:
        """Bayesian Personalised Ranking loss with L2 regularisation."""
        user_embs, item_embs = self.forward(adj)

        u = user_embs[user_ids]
        pos = item_embs[pos_ids]
        neg = item_embs[neg_ids]

        pos_scores = (u * pos).sum(dim=-1)
        neg_scores = (u * neg).sum(dim=-1)
        bpr = -F.logsigmoid(pos_scores - neg_scores).mean()

        # L2 reg on the ego embeddings only
        reg = reg_weight * (
            self.user_embedding(user_ids).pow(2).sum()
            + self.item_embedding(pos_ids).pow(2).sum()
            + self.item_embedding(neg_ids).pow(2).sum()
        ) / user_ids.size(0)

        return bpr + reg


class LightGCNEngine:
    """Serving wrapper for LightGCN collaborative filtering."""

    def __init__(self):
        self.model: Optional[LightGCNModel] = None
        self.adj: Optional[torch.sparse.FloatTensor] = None
        self.is_ready = False
        self.user_id_map: Dict[int, int] = {}
        self.movie_id_map: Dict[int, int] = {}
        self.reverse_movie_map: Dict[int, int] = {}
        self._user_embs: Optional[torch.Tensor] = None
        self._item_embs: Optional[torch.Tensor] = None
        self._lock = threading.Lock()

    def load(self) -> "LightGCNEngine":
        """Load trained LightGCN model."""
        try:
            if not MODEL_PATH.exists():
                logger.warning("LightGCN model not found at %s. Engine not ready.", MODEL_PATH)
                return self

            checkpoint = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
            self.user_id_map = checkpoint.get("user_id_map", {})
            self.movie_id_map = checkpoint.get("movie_id_map", {})
            self.reverse_movie_map = {v: k for k, v in self.movie_id_map.items()}

            num_users = checkpoint.get("num_users", len(self.user_id_map))
            num_items = checkpoint.get("num_items", len(self.movie_id_map))

            self.model = LightGCNModel(num_users, num_items)
            self.model.load_state_dict(checkpoint["model_state_dict"])
            self.model.eval()

            # Rebuild adjacency from saved interaction data
            if "adj_indices" in checkpoint and "adj_values" in checkpoint:
                n = num_users + num_items
                self.adj = torch.sparse_coo_tensor(
                    checkpoint["adj_indices"],
                    checkpoint["adj_values"],
                    (n, n),
                ).coalesce()
            elif "user_indices" in checkpoint and "item_indices" in checkpoint:
                self.adj = build_norm_adj(
                    num_users, num_items,
                    checkpoint["user_indices"],
                    checkpoint["item_indices"],
                )

            # Pre-compute embeddings
            if self.adj is not None:
                with torch.no_grad():
                    self._user_embs, self._item_embs = self.model(self.adj)

            self.is_ready = True
            logger.info("LightGCN engine loaded (%d users, %d items, %d layers).", num_users, num_items, NUM_LAYERS)
        except Exception as e:
            logger.error("Failed to load LightGCN engine: %s", e)
            self.is_ready = False
        return self

    def _refresh_embeddings(self) -> None:
        """Recompute cached embeddings (e.g., after fine-tuning)."""
        if self.model is not None and self.adj is not None:
            with torch.no_grad():
                self._user_embs, self._item_embs = self.model(self.adj)

    def get_candidates(self, user_id: int, k: int = 100) -> List[int]:
        """Return top-k movie IDs for a user by dot-product scoring."""
        if not self.is_ready or self._user_embs is None or self._item_embs is None:
            return []
        try:
            internal_uid = self.user_id_map.get(user_id)
            if internal_uid is None:
                return []

            user_emb = self._user_embs[internal_uid]  # (64,)
            scores = (self._item_embs @ user_emb).numpy()  # (num_items,)
            top_indices = np.argsort(scores)[::-1][:k]
            return [
                self.reverse_movie_map[int(idx)]
                for idx in top_indices
                if int(idx) in self.reverse_movie_map
            ]
        except Exception as e:
            logger.error("LightGCN candidate generation failed: %s", e)
            return []

    def get_score(self, user_id: int, movie_id: int) -> float:
        """Score a single (user, movie) pair."""
        if not self.is_ready or self._user_embs is None or self._item_embs is None:
            return 0.0
        try:
            internal_uid = self.user_id_map.get(user_id)
            internal_mid = self.movie_id_map.get(movie_id)
            if internal_uid is None or internal_mid is None:
                return 0.0
            score = float(torch.dot(self._user_embs[internal_uid], self._item_embs[internal_mid]).item())
            return score
        except Exception as e:
            logger.error("LightGCN scoring failed: %s", e)
            return 0.0


# --- Singleton ---

_lightgcn_engine: Optional[LightGCNEngine] = None
_lightgcn_lock = threading.Lock()


def get_lightgcn_engine() -> LightGCNEngine:
    """Get or lazily initialise the LightGCN engine singleton."""
    global _lightgcn_engine
    if _lightgcn_engine is None:
        with _lightgcn_lock:
            if _lightgcn_engine is None:
                _lightgcn_engine = LightGCNEngine()
                _lightgcn_engine.load()
    return _lightgcn_engine
