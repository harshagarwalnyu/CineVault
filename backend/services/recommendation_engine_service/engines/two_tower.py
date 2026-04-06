"""
Two-Tower Candidate Generation Engine
======================================
User Tower + Item Tower -> 128-dim embeddings.
Candidate retrieval via Qdrant ANN search on pre-computed item embeddings.
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

from backend.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 128
MODEL_PATH = Path("data/models/two_tower.pt")
QDRANT_COLLECTION = "movie_twotower"

# Genre vocabulary for one-hot encoding
GENRE_VOCAB = [
    "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary",
    "Drama", "Family", "Fantasy", "History", "Horror", "Music", "Mystery",
    "Romance", "Science Fiction", "Thriller", "TV Movie", "War", "Western",
]
NUM_GENRES = len(GENRE_VOCAB)
# decade (1 float), language_id (1), vote_avg (1), runtime (1) + genres
ITEM_FEATURE_DIM = NUM_GENRES + 4


class UserTower(nn.Module):
    """User embedding: Embedding(user_id) -> MLP([256, 128]) -> 128-dim."""

    def __init__(self, num_users: int, embed_dim: int = EMBEDDING_DIM):
        super().__init__()
        self.embedding = nn.Embedding(num_users, embed_dim)
        self.mlp = nn.Sequential(
            nn.Linear(embed_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, 128),
        )

    def forward(self, user_ids: torch.Tensor) -> torch.Tensor:
        x = self.embedding(user_ids)
        return F.normalize(self.mlp(x), dim=-1)


class ItemTower(nn.Module):
    """Item embedding: Embedding(movie_id) + features -> MLP([256, 128]) -> 128-dim."""

    def __init__(self, num_items: int, feature_dim: int = ITEM_FEATURE_DIM, embed_dim: int = EMBEDDING_DIM):
        super().__init__()
        self.embedding = nn.Embedding(num_items, embed_dim)
        self.mlp = nn.Sequential(
            nn.Linear(embed_dim + feature_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, 128),
        )

    def forward(self, item_ids: torch.Tensor, features: torch.Tensor) -> torch.Tensor:
        x = self.embedding(item_ids)
        x = torch.cat([x, features], dim=-1)
        return F.normalize(self.mlp(x), dim=-1)


class TwoTowerModel(nn.Module):
    """Two-Tower retrieval model with sampled softmax loss."""

    def __init__(self, num_users: int, num_items: int, feature_dim: int = ITEM_FEATURE_DIM):
        super().__init__()
        self.user_tower = UserTower(num_users)
        self.item_tower = ItemTower(num_items, feature_dim)
        self.temperature = nn.Parameter(torch.tensor(0.07))

    def forward(
        self,
        user_ids: torch.Tensor,
        pos_item_ids: torch.Tensor,
        pos_features: torch.Tensor,
        neg_item_ids: torch.Tensor,
        neg_features: torch.Tensor,
    ) -> torch.Tensor:
        """Sampled softmax loss: positive pairs scored higher than negatives."""
        user_emb = self.user_tower(user_ids)  # (B, 128)
        pos_emb = self.item_tower(pos_item_ids, pos_features)  # (B, 128)
        neg_emb = self.item_tower(neg_item_ids, neg_features)  # (B, 128)

        pos_score = (user_emb * pos_emb).sum(dim=-1) / self.temperature.abs().clamp(min=0.01)
        neg_score = (user_emb * neg_emb).sum(dim=-1) / self.temperature.abs().clamp(min=0.01)

        logits = torch.stack([pos_score, neg_score], dim=-1)  # (B, 2)
        labels = torch.zeros(logits.size(0), dtype=torch.long, device=logits.device)
        return F.cross_entropy(logits, labels)

    def get_user_embedding(self, user_ids: torch.Tensor) -> torch.Tensor:
        return self.user_tower(user_ids)

    def get_item_embedding(self, item_ids: torch.Tensor, features: torch.Tensor) -> torch.Tensor:
        return self.item_tower(item_ids, features)


def encode_item_features(row: pd.Series) -> np.ndarray:
    """Encode a movie row into the item feature vector."""
    genre_vec = np.zeros(NUM_GENRES, dtype=np.float32)
    genres_str = str(row.get("genres", ""))
    for i, g in enumerate(GENRE_VOCAB):
        if g.lower() in genres_str.lower():
            genre_vec[i] = 1.0

    year = float(row.get("release_year", row.get("year", 2000)))
    decade = (year - 1900) / 130.0  # normalize roughly to [0, 1]

    lang = hash(str(row.get("original_language", "en"))) % 100 / 100.0
    vote_avg = float(row.get("vote_average", 5.0)) / 10.0
    runtime = min(float(row.get("runtime", 100)), 300) / 300.0

    return np.concatenate([genre_vec, [decade, lang, vote_avg, runtime]])


class TwoTowerEngine:
    """Serving wrapper: loads model, pre-computes item embeddings, queries Qdrant for ANN."""

    def __init__(self):
        self.model: Optional[TwoTowerModel] = None
        self.qdrant_client = None
        self.is_ready = False
        self.user_id_map: Dict[int, int] = {}
        self.movie_id_map: Dict[int, int] = {}
        self.reverse_movie_map: Dict[int, int] = {}
        self.item_features: Optional[torch.Tensor] = None
        self._lock = threading.Lock()

    def load(self, movies_df: Optional[pd.DataFrame] = None) -> "TwoTowerEngine":
        """Load trained model and connect to Qdrant."""
        try:
            if not MODEL_PATH.exists():
                logger.warning("Two-Tower model not found at %s. Engine will not be ready.", MODEL_PATH)
                return self

            checkpoint = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
            self.user_id_map = checkpoint.get("user_id_map", {})
            self.movie_id_map = checkpoint.get("movie_id_map", {})
            self.reverse_movie_map = {v: k for k, v in self.movie_id_map.items()}

            num_users = checkpoint.get("num_users", len(self.user_id_map))
            num_items = checkpoint.get("num_items", len(self.movie_id_map))

            self.model = TwoTowerModel(num_users, num_items)
            self.model.load_state_dict(checkpoint["model_state_dict"])
            self.model.eval()

            # Connect to Qdrant
            try:
                from qdrant_client import QdrantClient
                self.qdrant_client = QdrantClient(url=settings.QDRANT_URL)
                self.qdrant_client.get_collections()
            except Exception as e:
                logger.warning("Qdrant not available for Two-Tower ANN: %s", e)
                self.qdrant_client = None

            self.is_ready = True
            logger.info("Two-Tower engine loaded successfully (%d users, %d items).", num_users, num_items)
        except Exception as e:
            logger.error("Failed to load Two-Tower engine: %s", e)
            self.is_ready = False
        return self

    def get_candidates(self, user_id: int, k: int = 200) -> List[int]:
        """Retrieve top-k candidate movie IDs via ANN search."""
        if not self.is_ready or self.model is None:
            return []
        try:
            internal_uid = self.user_id_map.get(user_id)
            if internal_uid is None:
                logger.debug("User %d not in Two-Tower id map.", user_id)
                return []

            with torch.no_grad():
                user_tensor = torch.tensor([internal_uid], dtype=torch.long)
                user_emb = self.model.get_user_embedding(user_tensor).squeeze(0).numpy()

            # Prefer Qdrant ANN if available
            if self.qdrant_client is not None:
                return self._ann_search(user_emb, k)

            # Fallback: brute-force dot product (slower, for dev/testing)
            return self._brute_force_search(user_emb, k)
        except Exception as e:
            logger.error("Two-Tower candidate generation failed: %s", e)
            return []

    def _ann_search(self, user_emb: np.ndarray, k: int) -> List[int]:
        """ANN search via Qdrant."""
        try:
            from qdrant_client.models import NamedVector
            results = self.qdrant_client.query_points(
                collection_name=QDRANT_COLLECTION,
                query=user_emb.tolist(),
                limit=k,
            )
            return [int(hit.id) for hit in results.points]
        except Exception as e:
            logger.warning("Qdrant ANN search failed, falling back to brute-force: %s", e)
            return self._brute_force_search(user_emb, k)

    def _brute_force_search(self, user_emb: np.ndarray, k: int) -> List[int]:
        """Fallback brute-force search over all item embeddings."""
        if self.item_features is None or self.model is None:
            return []
        try:
            with torch.no_grad():
                num_items = len(self.movie_id_map)
                item_ids = torch.arange(num_items, dtype=torch.long)
                item_embs = self.model.get_item_embedding(item_ids, self.item_features).numpy()
                scores = item_embs @ user_emb
                top_indices = np.argsort(scores)[::-1][:k]
                return [self.reverse_movie_map[idx] for idx in top_indices if idx in self.reverse_movie_map]
        except Exception as e:
            logger.error("Brute-force search failed: %s", e)
            return []

    def index_items_to_qdrant(self, movies_df: pd.DataFrame) -> None:
        """Pre-compute item embeddings and index them in Qdrant."""
        if not self.is_ready or self.model is None or self.qdrant_client is None:
            logger.warning("Cannot index items: engine or Qdrant not ready.")
            return
        try:
            from qdrant_client.models import Distance, VectorParams, PointStruct

            # Create / recreate collection
            self.qdrant_client.recreate_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )

            batch_size = 512
            points = []
            for _, row in movies_df.iterrows():
                movie_id = int(row.get("movie_id", row.get("id", 0)))
                internal_id = self.movie_id_map.get(movie_id)
                if internal_id is None:
                    continue
                feat = torch.tensor(encode_item_features(row), dtype=torch.float32).unsqueeze(0)
                item_tensor = torch.tensor([internal_id], dtype=torch.long)
                with torch.no_grad():
                    emb = self.model.get_item_embedding(item_tensor, feat).squeeze(0).numpy()
                points.append(PointStruct(id=movie_id, vector=emb.tolist(), payload={"movie_id": movie_id}))

                if len(points) >= batch_size:
                    self.qdrant_client.upsert(collection_name=QDRANT_COLLECTION, points=points)
                    points = []

            if points:
                self.qdrant_client.upsert(collection_name=QDRANT_COLLECTION, points=points)
            logger.info("Indexed %d items to Qdrant collection '%s'.", len(self.movie_id_map), QDRANT_COLLECTION)
        except Exception as e:
            logger.error("Failed to index items to Qdrant: %s", e)


# --- Singleton ---

_two_tower_engine: Optional[TwoTowerEngine] = None
_two_tower_lock = threading.Lock()


def get_two_tower_engine() -> TwoTowerEngine:
    """Get or lazily initialise the Two-Tower engine singleton."""
    global _two_tower_engine
    if _two_tower_engine is None:
        with _two_tower_lock:
            if _two_tower_engine is None:
                _two_tower_engine = TwoTowerEngine()
                _two_tower_engine.load()
    return _two_tower_engine
