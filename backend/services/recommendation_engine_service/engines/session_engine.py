"""
Session-Based Transformer Recommendation Engine
=================================================
2-layer Transformer encoder (4 heads, 128-dim) over movie embedding sequence.
Predicts next-item embedding -> ANN search for candidates.
"""

import logging
import threading
from pathlib import Path
from typing import List, Optional

import numpy as np
import torch
import torch.nn as nn


logger = logging.getLogger(__name__)

EMBEDDING_DIM = 128
MAX_SEQ_LEN = 50
NUM_HEADS = 4
NUM_LAYERS = 2
MODEL_PATH = Path("data/models/session_transformer.pt")


class SessionTransformerModel(nn.Module):
    """Transformer encoder for session-based next-item prediction."""

    def __init__(self, num_items: int, embed_dim: int = EMBEDDING_DIM):
        super().__init__()
        self.item_embedding = nn.Embedding(num_items + 1, embed_dim, padding_idx=0)
        self.pos_embedding = nn.Embedding(MAX_SEQ_LEN, embed_dim)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=embed_dim,
            nhead=NUM_HEADS,
            dim_feedforward=embed_dim * 4,
            dropout=0.1,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=NUM_LAYERS)
        self.output_proj = nn.Linear(embed_dim, embed_dim)

    def forward(self, item_ids: torch.Tensor) -> torch.Tensor:
        batch_size, seq_len = item_ids.shape
        positions = torch.arange(seq_len, device=item_ids.device).unsqueeze(0).expand(batch_size, -1)

        x = self.item_embedding(item_ids) + self.pos_embedding(positions)
        padding_mask = item_ids == 0
        x = self.transformer(x, src_key_padding_mask=padding_mask)

        lengths = (~padding_mask).sum(dim=1).clamp(min=1) - 1
        last_hidden = x[torch.arange(batch_size), lengths]
        return self.output_proj(last_hidden)


class SessionEngine:
    """Session-based recommendation engine using Transformer."""

    def __init__(self):
        self.model: Optional[SessionTransformerModel] = None
        self.item_embeddings: Optional[np.ndarray] = None
        self.movie_id_to_idx: dict = {}
        self.idx_to_movie_id: dict = {}
        self._ready = False

    def load(self, num_items: int, movie_id_mapping: dict):
        self.movie_id_to_idx = movie_id_mapping
        self.idx_to_movie_id = {v: k for k, v in movie_id_mapping.items()}

        try:
            self.model = SessionTransformerModel(num_items)
            if MODEL_PATH.exists():
                state = torch.load(MODEL_PATH, map_location="cpu", weights_only=True)
                self.model.load_state_dict(state)
                logger.info("Session Transformer model loaded from %s", MODEL_PATH)
            else:
                logger.info("No session model weights found, using random init")
            self.model.eval()

            with torch.no_grad():
                all_ids = torch.arange(1, num_items + 1)
                self.item_embeddings = self.model.item_embedding(all_ids).numpy()

            self._ready = True
        except Exception as e:
            logger.warning("Session engine load failed: %s", e)
            self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    def get_candidates(self, session_movie_ids: List[int], k: int = 50) -> List[int]:
        if not self._ready or not session_movie_ids:
            return []

        try:
            indices = []
            for mid in session_movie_ids[-MAX_SEQ_LEN:]:
                idx = self.movie_id_to_idx.get(mid, 0)
                if idx > 0:
                    indices.append(idx)

            if not indices:
                return []

            padded = [0] * (MAX_SEQ_LEN - len(indices)) + indices
            input_tensor = torch.tensor([padded], dtype=torch.long)

            with torch.no_grad():
                pred_embedding = self.model(input_tensor).numpy()[0]

            norms = np.linalg.norm(self.item_embeddings, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)
            normalized_items = self.item_embeddings / norms
            pred_norm = pred_embedding / max(np.linalg.norm(pred_embedding), 1e-8)

            scores = normalized_items @ pred_norm
            top_indices = np.argsort(scores)[::-1][:k + len(indices)]

            seen = set(indices)
            results = []
            for idx in top_indices:
                movie_id = self.idx_to_movie_id.get(int(idx + 1))
                if movie_id and self.movie_id_to_idx.get(movie_id, 0) not in seen:
                    results.append(movie_id)
                    if len(results) >= k:
                        break

            return results
        except Exception as e:
            logger.warning("Session engine prediction failed: %s", e)
            return []


_engine: Optional[SessionEngine] = None
_lock = threading.Lock()


def get_session_engine() -> SessionEngine:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = SessionEngine()
    return _engine
