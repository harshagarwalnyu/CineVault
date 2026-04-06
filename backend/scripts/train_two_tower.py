"""
Training script for Two-Tower candidate generation model.
Loads ratings, trains user/item towers, indexes embeddings in Qdrant.
"""

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_DIR = Path("data/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)


class RatingDataset(Dataset):
    def __init__(self, user_ids, item_ids, labels):
        self.user_ids = torch.tensor(user_ids, dtype=torch.long)
        self.item_ids = torch.tensor(item_ids, dtype=torch.long)
        self.labels = torch.tensor(labels, dtype=torch.float)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        return self.user_ids[idx], self.item_ids[idx], self.labels[idx]


def main():
    from backend.database import engine as db_engine

    logger.info("Loading ratings from database...")
    with db_engine.connect() as conn:
        ratings_df = pd.read_sql("SELECT user_id, movie_id, rating FROM ratings", conn)

    if ratings_df.empty:
        # Try ML ratings
        try:
            with db_engine.connect() as conn:
                ratings_df = pd.read_sql(
                    "SELECT ml_user_id as user_id, movie_id, rating FROM ml_ratings LIMIT 5000000",
                    conn,
                )
        except Exception:
            pass

    if ratings_df.empty:
        logger.error("No ratings data available for training")
        sys.exit(1)

    logger.info("Loaded %d ratings", len(ratings_df))

    # Map IDs to contiguous indices
    user_ids = ratings_df["user_id"].unique()
    item_ids = ratings_df["movie_id"].unique()
    user_map = {uid: i + 1 for i, uid in enumerate(user_ids)}
    item_map = {iid: i + 1 for i, iid in enumerate(item_ids)}

    num_users = len(user_ids)
    num_items = len(item_ids)
    logger.info("Users: %d, Items: %d", num_users, num_items)

    # Positive = rated >= 3.5, negative = random unrated
    positive = ratings_df[ratings_df["rating"] >= 3.5]
    pos_users = [user_map[u] for u in positive["user_id"]]
    pos_items = [item_map[i] for i in positive["movie_id"]]
    pos_labels = [1.0] * len(pos_users)

    # Sample negatives
    neg_users, neg_items, neg_labels = [], [], []
    rng = np.random.default_rng(42)
    all_items = list(item_map.values())
    user_items = ratings_df.groupby("user_id")["movie_id"].apply(set).to_dict()

    for uid, rated in user_items.items():
        mapped_uid = user_map[uid]
        rated_mapped = {item_map[i] for i in rated if i in item_map}
        n_neg = min(len(rated), 5)
        for _ in range(n_neg):
            neg_item = rng.choice(all_items)
            while neg_item in rated_mapped:
                neg_item = rng.choice(all_items)
            neg_users.append(mapped_uid)
            neg_items.append(neg_item)
            neg_labels.append(0.0)

    all_users = pos_users + neg_users
    all_items_list = pos_items + neg_items
    all_labels = pos_labels + neg_labels

    dataset = RatingDataset(all_users, all_items_list, all_labels)
    loader = DataLoader(dataset, batch_size=4096, shuffle=True)

    from backend.services.recommendation_engine_service.engines.two_tower import TwoTowerModel

    model = TwoTowerModel(num_users + 1, num_items + 1)
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.BCEWithLogitsLoss()

    logger.info("Training Two-Tower model...")
    model.train()
    for epoch in range(10):
        total_loss = 0
        for batch_users, batch_items, batch_labels in loader:
            user_emb = model.user_tower(batch_users)
            item_emb = model.item_tower(batch_items)
            logits = (user_emb * item_emb).sum(dim=1)
            loss = loss_fn(logits, batch_labels)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        logger.info("Epoch %d: loss=%.4f", epoch + 1, total_loss / len(loader))

    # Save model
    save_path = MODEL_DIR / "two_tower.pt"
    torch.save(model.state_dict(), save_path)
    logger.info("Model saved to %s", save_path)

    # Index item embeddings in Qdrant
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams, PointStruct
        from backend.config import settings

        client = QdrantClient(url=settings.QDRANT_URL)
        collection = "movie_twotower"

        client.recreate_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=128, distance=Distance.COSINE),
        )

        model.eval()
        with torch.no_grad():
            all_item_ids = torch.arange(1, num_items + 1)
            embeddings = model.item_tower(all_item_ids).numpy()

        idx_to_movie = {v: k for k, v in item_map.items()}
        points = [
            PointStruct(
                id=int(idx_to_movie.get(i + 1, i)),
                vector=embeddings[i].tolist(),
                payload={"movie_id": int(idx_to_movie.get(i + 1, i))},
            )
            for i in range(num_items)
        ]

        # Batch upload
        batch_size = 1000
        for i in range(0, len(points), batch_size):
            client.upsert(collection_name=collection, points=points[i:i + batch_size])

        logger.info("Indexed %d item embeddings in Qdrant", num_items)
    except Exception as e:
        logger.warning("Qdrant indexing skipped: %s", e)


if __name__ == "__main__":
    main()
