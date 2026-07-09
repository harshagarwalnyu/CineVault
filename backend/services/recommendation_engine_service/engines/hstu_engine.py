"""
HSTU — Hierarchical Sequential Transduction Unit
==================================================
Adapted from Meta's "Actions Speak Louder than Words: Trillion-Parameter
Sequential Transducers for Generative Recommendations" (2024).

Key innovations over vanilla Transformers:
  1. Pointwise normalization (not softmax) — handles non-stationary,
     high-cardinality streaming vocabularies.
  2. Collapsed architecture — feature extraction, spatial aggregation,
     and pointwise transformation in a single repeatable block.
  3. Causal masking for autoregressive next-item prediction.

This implementation works with the existing CSV-based movie data: it
encodes user interaction sequences (movie IDs + metadata features) and
predicts the next-item embedding via ANN search.
"""

import logging
import math
import threading
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 128
MAX_SEQ_LEN = 64
NUM_HEADS = 4
NUM_LAYERS = 3
MODEL_PATH = Path("data/models/hstu.pt")

# ---------------------------------------------------------------------------
# Genre vocabulary (shared with other engines)
# ---------------------------------------------------------------------------
GENRE_VOCAB = [
    "Action",
    "Adventure",
    "Animation",
    "Comedy",
    "Crime",
    "Documentary",
    "Drama",
    "Family",
    "Fantasy",
    "History",
    "Horror",
    "Music",
    "Mystery",
    "Romance",
    "Science Fiction",
    "Thriller",
    "TV Movie",
    "War",
    "Western",
]
NUM_GENRES = len(GENRE_VOCAB)
# Metadata features: genres (19) + decade (1) + vote_avg (1) + runtime (1) = 22
ITEM_META_DIM = NUM_GENRES + 3


# ---------------------------------------------------------------------------
# Pointwise-normalised multi-head attention (the core HSTU innovation)
# ---------------------------------------------------------------------------


class PointwiseNormAttention(nn.Module):
    """
    Instead of softmax over the full sequence, HSTU applies per-element
    normalization (L2 on queries/keys) and scales by a learnable temperature.
    This avoids the softmax bottleneck for non-stationary vocabularies and
    is 5-15× faster than FlashAttention2 on long sequences.
    """

    def __init__(self, d_model: int, num_heads: int, dropout: float = 0.1):
        super().__init__()
        assert d_model % num_heads == 0
        self.d_model = d_model
        self.num_heads = num_heads
        self.head_dim = d_model // num_heads

        self.qkv = nn.Linear(d_model, 3 * d_model)
        self.out_proj = nn.Linear(d_model, d_model)
        self.temperature = nn.Parameter(
            torch.tensor(math.sqrt(self.head_dim), dtype=torch.float32)
        )
        self.dropout = nn.Dropout(dropout)

    def forward(
        self, x: torch.Tensor, mask: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        B, T, _ = x.shape
        qkv = self.qkv(x).reshape(B, T, 3, self.num_heads, self.head_dim)
        qkv = qkv.permute(2, 0, 3, 1, 4)  # (3, B, H, T, D)
        q, k, v = qkv[0], qkv[1], qkv[2]

        # L2-normalise queries and keys (pointwise normalization)
        q = F.normalize(q, dim=-1)
        k = F.normalize(k, dim=-1)

        # Scaled dot-product with learnable temperature
        attn = (q @ k.transpose(-2, -1)) * self.temperature.abs().clamp(min=0.1)

        # Causal mask
        if mask is None:
            mask = torch.triu(
                torch.ones(T, T, device=x.device, dtype=torch.bool), diagonal=1
            )
        attn = attn.masked_fill(mask.unsqueeze(0).unsqueeze(0), float("-inf"))

        # ReLU activation instead of softmax (another HSTU departure)
        # The paper shows ReLU attention matches softmax quality while being faster
        attn = F.relu(attn)
        attn = self.dropout(attn)

        out = (attn @ v).transpose(1, 2).reshape(B, T, self.d_model)
        return self.out_proj(out)


# ---------------------------------------------------------------------------
# HSTU Block: collapsed feature-extraction + spatial-aggregation + transform
# ---------------------------------------------------------------------------


class HSTUBlock(nn.Module):
    """
    Single HSTU block that collapses three sub-layers:
      1. Pointwise Projection  — linear transform of input features
      2. Spatial Aggregation   — pointwise-normalised attention
      3. Pointwise Transform   — FFN with gated activation (SwiGLU)
    """

    def __init__(self, d_model: int, num_heads: int, dropout: float = 0.1):
        super().__init__()
        self.norm1 = nn.LayerNorm(d_model)
        self.attention = PointwiseNormAttention(d_model, num_heads, dropout)
        self.norm2 = nn.LayerNorm(d_model)

        # SwiGLU-style gated FFN (modern best-practice, used in LLaMA/Gemini)
        ffn_hidden = d_model * 4
        self.gate_proj = nn.Linear(d_model, ffn_hidden, bias=False)
        self.up_proj = nn.Linear(d_model, ffn_hidden, bias=False)
        self.down_proj = nn.Linear(ffn_hidden, d_model, bias=False)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self, x: torch.Tensor, mask: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        # Sub-layer 1+2: Normalise -> Attention -> Residual
        h = self.norm1(x)
        h = self.attention(h, mask)
        x = x + self.dropout(h)

        # Sub-layer 3: SwiGLU FFN -> Residual
        h = self.norm2(x)
        gate = F.silu(self.gate_proj(h))
        h = gate * self.up_proj(h)
        h = self.down_proj(h)
        x = x + self.dropout(h)
        return x


# ---------------------------------------------------------------------------
# Full HSTU Model
# ---------------------------------------------------------------------------


class HSTUModel(nn.Module):
    """
    Hierarchical Sequential Transduction Unit for next-item prediction.

    Input: sequence of (item_id, metadata_features) pairs
    Output: predicted embedding for the next item
    """

    def __init__(
        self,
        num_items: int,
        embed_dim: int = EMBEDDING_DIM,
        meta_dim: int = ITEM_META_DIM,
        num_heads: int = NUM_HEADS,
        num_layers: int = NUM_LAYERS,
        max_seq_len: int = MAX_SEQ_LEN,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.num_items = num_items
        self.embed_dim = embed_dim

        # Item embedding + metadata projection
        self.item_embedding = nn.Embedding(num_items + 1, embed_dim, padding_idx=0)
        self.meta_proj = nn.Linear(meta_dim, embed_dim)
        self.combine = nn.Linear(embed_dim * 2, embed_dim)

        # Learnable positional encoding (not sinusoidal — better for short sequences)
        self.pos_embedding = nn.Embedding(max_seq_len, embed_dim)

        # Stacked HSTU blocks
        self.blocks = nn.ModuleList(
            [HSTUBlock(embed_dim, num_heads, dropout) for _ in range(num_layers)]
        )

        self.final_norm = nn.LayerNorm(embed_dim)
        self.output_proj = nn.Linear(embed_dim, embed_dim)

    def forward(
        self,
        item_ids: torch.Tensor,
        meta_features: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Parameters
        ----------
        item_ids : (B, T) — padded sequence of internal item IDs
        meta_features : (B, T, meta_dim) — optional metadata per item

        Returns
        -------
        (B, embed_dim) — predicted next-item embedding
        """
        B, T = item_ids.shape
        positions = torch.arange(T, device=item_ids.device).unsqueeze(0).expand(B, -1)

        # Build input representation
        x = self.item_embedding(item_ids) + self.pos_embedding(positions)

        if meta_features is not None:
            meta_emb = self.meta_proj(meta_features)
            x = self.combine(torch.cat([x, meta_emb], dim=-1))

        # Causal mask
        causal_mask = torch.triu(
            torch.ones(T, T, device=item_ids.device, dtype=torch.bool),
            diagonal=1,
        )

        # Pass through HSTU blocks
        for block in self.blocks:
            x = block(x, causal_mask)

        x = self.final_norm(x)

        # Extract last non-padding position
        padding_mask = item_ids == 0
        lengths = (~padding_mask).sum(dim=1).clamp(min=1) - 1
        last_hidden = x[torch.arange(B, device=x.device), lengths]

        return F.normalize(self.output_proj(last_hidden), dim=-1)


# ---------------------------------------------------------------------------
# HSTU Engine (serving wrapper)
# ---------------------------------------------------------------------------


def encode_item_meta(row) -> np.ndarray:
    """Encode a movie row into the HSTU metadata feature vector."""
    genre_vec = np.zeros(NUM_GENRES, dtype=np.float32)
    genres_str = str(row.get("genres", ""))
    for i, g in enumerate(GENRE_VOCAB):
        if g.lower() in genres_str.lower():
            genre_vec[i] = 1.0

    year = float(row.get("release_year", row.get("year", 2000)))
    decade = (year - 1900) / 130.0

    vote_avg = float(row.get("vote_average", 5.0)) / 10.0
    runtime = min(float(row.get("runtime", 100)), 300) / 300.0

    return np.concatenate([genre_vec, [decade, vote_avg, runtime]])


class HSTUEngine:
    """Serving wrapper: loads trained HSTU, predicts next items from session."""

    def __init__(self):
        self.model: Optional[HSTUModel] = None
        self.item_embeddings: Optional[np.ndarray] = None
        self.movie_id_to_idx: Dict[int, int] = {}
        self.idx_to_movie_id: Dict[int, int] = {}
        self.movies_df = None
        self._ready = False
        self._lock = threading.Lock()

    def load(
        self, movies_df=None, movie_id_mapping: Optional[Dict[int, int]] = None
    ) -> "HSTUEngine":
        """Load trained HSTU model or initialise from movie data."""
        try:
            if movies_df is not None:
                self.movies_df = movies_df

            if movie_id_mapping:
                self.movie_id_to_idx = movie_id_mapping
            elif movies_df is not None:
                self.movie_id_to_idx = {
                    int(row["id"]): idx + 1
                    for idx, (_, row) in enumerate(movies_df.iterrows())
                }
            self.idx_to_movie_id = {v: k for k, v in self.movie_id_to_idx.items()}

            num_items = len(self.movie_id_to_idx)
            if num_items == 0:
                logger.warning("HSTU: No items to index.")
                return self

            self.model = HSTUModel(num_items)

            if MODEL_PATH.exists():
                state = torch.load(MODEL_PATH, map_location="cpu", weights_only=True)
                self.model.load_state_dict(state)
                logger.info("HSTU model loaded from %s", MODEL_PATH)
            else:
                logger.info(
                    "HSTU: No pretrained weights, using random init (will learn from interactions)"
                )

            self.model.eval()

            # Pre-compute item embeddings for ANN search
            with torch.no_grad():
                all_ids = torch.arange(1, num_items + 1)
                self.item_embeddings = self.model.item_embedding(all_ids).numpy()

            self._ready = True
            logger.info(
                "HSTU engine loaded (%d items, %d-dim, %d layers).",
                num_items,
                EMBEDDING_DIM,
                NUM_LAYERS,
            )
        except Exception as e:
            logger.error("HSTU engine load failed: %s", e)
            self._ready = False
        return self

    @property
    def is_ready(self) -> bool:
        return self._ready

    def get_candidates(self, session_movie_ids: List[int], k: int = 50) -> List[int]:
        """Predict next items given a session of movie IDs."""
        if not self._ready or not session_movie_ids or self.model is None:
            return []

        try:
            # Map movie IDs to internal indices
            indices = []
            meta_list = []
            for mid in session_movie_ids[-MAX_SEQ_LEN:]:
                idx = self.movie_id_to_idx.get(mid, 0)
                if idx > 0:
                    indices.append(idx)
                    # Build metadata features if movies_df available
                    if self.movies_df is not None:
                        mask = self.movies_df["id"] == mid
                        if mask.any():
                            row = self.movies_df[mask].iloc[0]
                            meta_list.append(encode_item_meta(row))
                        else:
                            meta_list.append(np.zeros(ITEM_META_DIM, dtype=np.float32))
                    else:
                        meta_list.append(np.zeros(ITEM_META_DIM, dtype=np.float32))

            if not indices:
                return []

            # Pad to MAX_SEQ_LEN (left-padding)
            pad_len = MAX_SEQ_LEN - len(indices)
            padded_ids = [0] * pad_len + indices
            padded_meta = [
                np.zeros(ITEM_META_DIM, dtype=np.float32)
            ] * pad_len + meta_list

            input_ids = torch.tensor([padded_ids], dtype=torch.long)
            input_meta = torch.tensor([padded_meta], dtype=torch.float32)

            with torch.no_grad():
                pred_embedding = self.model(input_ids, input_meta).numpy()[0]

            # ANN search via cosine similarity against item embeddings
            norms = np.linalg.norm(self.item_embeddings, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)
            normalized_items = self.item_embeddings / norms
            pred_norm = pred_embedding / max(np.linalg.norm(pred_embedding), 1e-8)

            scores = normalized_items @ pred_norm
            top_indices = np.argsort(scores)[::-1][: k + len(indices)]

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
            logger.warning("HSTU prediction failed: %s", e)
            return []


# --- Singleton ---
_engine: Optional[HSTUEngine] = None
_lock = threading.Lock()


def get_hstu_engine() -> HSTUEngine:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = HSTUEngine()
    return _engine
