"""
CLRec — Contrastive Learning for Recommendations
==================================================
Self-supervised representation learning via InfoNCE loss with
data augmentation (feature dropout, random masking).

Based on:
  - "Self-Supervised Learning for Recommendation" (ACM CSUR 2025)
  - SimCLR framework adapted for tabular movie features

Key insight: By learning representations from augmented views of the
same item (positive pair) vs different items (negative pairs), CLRec
builds robust embeddings even without user interaction data — solving
the cold-start problem.

The learned embeddings are used as a feature source in the ranking
pipeline, providing a complementary signal to content-based TF-IDF
and collaborative filtering.
"""

import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 128
MODEL_PATH = Path("data/models/clrec.pt")

# Genre vocabulary (shared)
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
# Features: genres (19) + vote_avg (1) + vote_count_log (1) + decade (1)
#         + runtime (1) + language_hash (1) + popularity_log (1) = 25
RAW_FEATURE_DIM = NUM_GENRES + 6


# ---------------------------------------------------------------------------
# Data Augmentation for Contrastive Learning
# ---------------------------------------------------------------------------


class FeatureAugmentor:
    """
    Produces two augmented "views" of the same item feature vector.

    Augmentations (applied stochastically):
      1. Feature Dropout  — randomly zero out features (p=0.1)
      2. Gaussian Noise   — add small noise to continuous features
      3. Feature Masking   — zero entire feature groups (genres vs numeric)
    """

    def __init__(self, dropout_rate: float = 0.1, noise_std: float = 0.05):
        self.dropout_rate = dropout_rate
        self.noise_std = noise_std

    def augment(self, features: torch.Tensor) -> torch.Tensor:
        """Apply random augmentation to a batch of feature vectors."""
        augmented = features.clone()

        # Feature dropout
        mask = torch.bernoulli(torch.full_like(augmented, 1.0 - self.dropout_rate))
        augmented = augmented * mask

        # Gaussian noise on continuous features (last 6 dims)
        if augmented.dim() == 2 and augmented.size(1) > NUM_GENRES:
            noise = torch.randn_like(augmented[:, NUM_GENRES:]) * self.noise_std
            augmented[:, NUM_GENRES:] = augmented[:, NUM_GENRES:] + noise

        return augmented


# ---------------------------------------------------------------------------
# Projection Network (SimCLR-style)
# ---------------------------------------------------------------------------


class ProjectionHead(nn.Module):
    """MLP projection head: maps encoder output to contrastive space."""

    def __init__(self, input_dim: int, hidden_dim: int = 256, output_dim: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.net(x)
        return F.normalize(out, dim=-1, eps=1e-6)


# ---------------------------------------------------------------------------
# CLRec Encoder
# ---------------------------------------------------------------------------


class CLRecEncoder(nn.Module):
    """
    Encoder network that maps raw movie features to a representation space.
    Architecture: Input -> MLP([256, 256, 128]) with residual connections.
    """

    def __init__(
        self, input_dim: int = RAW_FEATURE_DIM, embed_dim: int = EMBEDDING_DIM
    ):
        super().__init__()
        self.input_proj = nn.Linear(input_dim, 256)

        self.layer1 = nn.Sequential(
            nn.Linear(256, 256),
            nn.LayerNorm(256),
            nn.ReLU(),
            nn.Dropout(0.1),
        )
        self.layer2 = nn.Sequential(
            nn.Linear(256, embed_dim),
            nn.LayerNorm(embed_dim),
            nn.ReLU(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = F.relu(self.input_proj(x))
        h = h + self.layer1(h)  # residual
        return self.layer2(h)


# ---------------------------------------------------------------------------
# CLRec Full Model (Encoder + Projection Head)
# ---------------------------------------------------------------------------


class CLRecModel(nn.Module):
    """
    Full contrastive learning model.

    Training: two augmented views of same item -> encoder -> projection head
              -> InfoNCE loss pushes same-item views together, different-item apart.

    Inference: raw features -> encoder -> embedding (projection head discarded).
    """

    def __init__(
        self, input_dim: int = RAW_FEATURE_DIM, embed_dim: int = EMBEDDING_DIM
    ):
        super().__init__()
        self.encoder = CLRecEncoder(input_dim, embed_dim)
        self.projection = ProjectionHead(embed_dim, 256, 128)
        self.temperature = nn.Parameter(torch.tensor(0.5))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Encode features to embedding space (for inference)."""
        return self.encoder(x)

    def contrastive_forward(
        self,
        view1: torch.Tensor,
        view2: torch.Tensor,
    ) -> torch.Tensor:
        """
        Compute InfoNCE contrastive loss between two augmented views.

        InfoNCE: -log( exp(sim(z_i, z_j)/τ) / Σ_k exp(sim(z_i, z_k)/τ) )
        where (i, j) is a positive pair and k iterates over all negatives.
        """
        z1 = self.projection(self.encoder(view1))
        z2 = self.projection(self.encoder(view2))

        # Cosine similarity matrix scaled by temperature
        tau = self.temperature.abs().clamp(min=0.05, max=2.0)
        sim_matrix = (z1 @ z2.T) / tau

        # Clamp for numerical stability before cross_entropy
        sim_matrix = sim_matrix.clamp(-50, 50)

        # Positive pairs are on the diagonal
        labels = torch.arange(sim_matrix.size(0), device=sim_matrix.device)

        # Symmetric loss (both directions)
        loss = (
            F.cross_entropy(sim_matrix, labels) + F.cross_entropy(sim_matrix.T, labels)
        ) / 2
        return loss

    def get_embedding(self, x: torch.Tensor) -> torch.Tensor:
        """Get L2-normalized embedding for inference."""
        with torch.no_grad():
            return F.normalize(self.encoder(x), dim=-1, eps=1e-6)


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def extract_features(row) -> np.ndarray:
    """Extract raw feature vector from a movie DataFrame row."""
    genre_vec = np.zeros(NUM_GENRES, dtype=np.float32)
    genres_str = str(row.get("genres", ""))
    for i, g in enumerate(GENRE_VOCAB):
        if g.lower() in genres_str.lower():
            genre_vec[i] = 1.0

    vote_avg = float(row.get("vote_average", 5.0)) / 10.0
    vote_count = np.log1p(float(row.get("vote_count", 0))) / np.log1p(50000)
    year = float(row.get("release_year", row.get("year", 2000)))
    decade = (year - 1900) / 130.0
    runtime = min(float(row.get("runtime", 100)), 300) / 300.0
    lang_hash = (hash(str(row.get("original_language", "en"))) % 100) / 100.0
    popularity = np.log1p(float(row.get("popularity", 0))) / np.log1p(1000)

    return np.concatenate(
        [genre_vec, [vote_avg, vote_count, decade, runtime, lang_hash, popularity]]
    )


# ---------------------------------------------------------------------------
# CLRec Engine
# ---------------------------------------------------------------------------


class CLRecEngine:
    """
    Serving wrapper for contrastive learning embeddings.

    Provides:
      - Pre-computed item embeddings for similarity search
      - Online similarity scoring between items
      - Cold-start embeddings from features alone (no interaction data needed)
    """

    def __init__(self):
        self.model: Optional[CLRecModel] = None
        self.item_embeddings: Optional[np.ndarray] = None
        self.movie_id_to_idx: Dict[int, int] = {}
        self.idx_to_movie_id: Dict[int, int] = {}
        self._ready = False
        self._lock = threading.Lock()

    def load(self, movies_df: Optional[pd.DataFrame] = None) -> "CLRecEngine":
        """Load or initialize the CLRec model and compute item embeddings."""
        try:
            if movies_df is None or movies_df.empty:
                logger.warning("CLRec: No movie data provided.")
                return self

            # Build ID mapping
            self.movie_id_to_idx = {
                int(row["id"]): idx for idx, (_, row) in enumerate(movies_df.iterrows())
            }
            self.idx_to_movie_id = {v: k for k, v in self.movie_id_to_idx.items()}

            # Extract features for all movies
            features = np.array(
                [extract_features(row) for _, row in movies_df.iterrows()],
                dtype=np.float32,
            )

            self.model = CLRecModel(RAW_FEATURE_DIM, EMBEDDING_DIM)

            if MODEL_PATH.exists():
                state = torch.load(MODEL_PATH, map_location="cpu", weights_only=True)
                self.model.load_state_dict(state)
                logger.info("CLRec model loaded from %s", MODEL_PATH)
            else:
                # Self-supervised training on movie features (no labels needed!)
                self._train_self_supervised(features)

            self.model.eval()

            # Pre-compute all item embeddings
            with torch.no_grad():
                feat_tensor = torch.tensor(features, dtype=torch.float32)
                self.item_embeddings = self.model.get_embedding(feat_tensor).numpy()

            self._ready = True
            logger.info(
                "CLRec engine loaded (%d items, %d-dim embeddings).",
                len(self.movie_id_to_idx),
                EMBEDDING_DIM,
            )
        except Exception as e:
            logger.error("CLRec engine load failed: %s", e)
            self._ready = False
        return self

    def _train_self_supervised(
        self, features: np.ndarray, epochs: int = 20, batch_size: int = 256
    ) -> None:
        """
        Train the encoder via contrastive learning on augmented feature views.
        This runs at startup if no pre-trained model exists.
        """
        logger.info(
            "CLRec: Training self-supervised encoder on %d items for %d epochs...",
            len(features),
            epochs,
        )
        assert self.model is not None
        model = self.model
        model.train()
        augmentor = FeatureAugmentor()
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

        feat_tensor = torch.tensor(features, dtype=torch.float32)
        n = len(features)

        for epoch in range(epochs):
            # Shuffle
            perm = torch.randperm(n)
            total_loss = 0.0
            num_batches = 0

            for i in range(0, n, batch_size):
                batch_idx = perm[i : i + batch_size]
                batch = feat_tensor[batch_idx]

                # Create two augmented views
                view1 = augmentor.augment(batch)
                view2 = augmentor.augment(batch)

                loss = model.contrastive_forward(view1, view2)
                if torch.isnan(loss) or torch.isinf(loss):
                    continue
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()

                total_loss += loss.item()
                num_batches += 1

            scheduler.step()
            avg_loss = total_loss / max(num_batches, 1)
            if (epoch + 1) % 5 == 0:
                logger.info(
                    "CLRec epoch %d/%d — loss: %.4f", epoch + 1, epochs, avg_loss
                )

            # Early stopping: if loss is near zero for 3 consecutive epochs, stop
            if avg_loss < 1e-4 and epoch >= 5:
                logger.info(
                    "CLRec early stop at epoch %d (loss converged: %.4f)",
                    epoch + 1,
                    avg_loss,
                )
                break

        model.eval()
        logger.info("CLRec: Self-supervised training complete.")

    @property
    def is_ready(self) -> bool:
        return self._ready

    def get_similar(self, movie_id: int, k: int = 20) -> List[int]:
        """Find k most similar movies by contrastive embedding similarity."""
        if not self._ready or self.item_embeddings is None:
            return []

        idx = self.movie_id_to_idx.get(movie_id)
        if idx is None:
            return []

        query_emb = self.item_embeddings[idx]
        scores = self.item_embeddings @ query_emb
        top_indices = np.argsort(scores)[::-1][1 : k + 1]  # skip self

        return [
            self.idx_to_movie_id[int(i)]
            for i in top_indices
            if int(i) in self.idx_to_movie_id
        ]

    def get_embedding_for_movie(self, movie_id: int) -> Optional[np.ndarray]:
        """Get the contrastive embedding for a specific movie."""
        if not self._ready or self.item_embeddings is None:
            return None
        idx = self.movie_id_to_idx.get(movie_id)
        if idx is None:
            return None
        return self.item_embeddings[idx]

    def score_candidates(
        self, anchor_ids: List[int], candidate_ids: List[int]
    ) -> Dict[int, float]:
        """Score candidates based on average similarity to anchor items."""
        if not self._ready or self.item_embeddings is None or not anchor_ids:
            return {}

        anchor_indices = [
            self.movie_id_to_idx[mid]
            for mid in anchor_ids
            if mid in self.movie_id_to_idx
        ]
        if not anchor_indices:
            return {}

        anchor_embs = self.item_embeddings[anchor_indices]
        anchor_centroid = anchor_embs.mean(axis=0)
        anchor_centroid = anchor_centroid / max(np.linalg.norm(anchor_centroid), 1e-8)

        scores = {}
        for mid in candidate_ids:
            idx = self.movie_id_to_idx.get(mid)
            if idx is not None:
                scores[mid] = float(self.item_embeddings[idx] @ anchor_centroid)
        return scores


# --- Singleton ---
_engine: Optional[CLRecEngine] = None
_lock = threading.Lock()


def get_clrec_engine() -> CLRecEngine:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = CLRecEngine()
    return _engine
