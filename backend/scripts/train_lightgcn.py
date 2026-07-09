"""
Training script for LightGCN collaborative filtering model.
Loads ratings, builds bipartite graph, trains with BPR loss.
"""

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.optim as optim

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_DIR = Path("data/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def main():
    from backend.database import engine as db_engine

    logger.info("Loading ratings...")
    with db_engine.connect() as conn:
        ratings_df = pd.read_sql("SELECT user_id, movie_id, rating FROM ratings", conn)

    if ratings_df.empty:
        try:
            with db_engine.connect() as conn:
                ratings_df = pd.read_sql(
                    "SELECT ml_user_id as user_id, movie_id, rating FROM ml_ratings LIMIT 5000000",
                    conn,
                )
        except Exception:
            pass

    if ratings_df.empty:
        logger.error("No ratings data")
        sys.exit(1)

    # Filter positive interactions (>= 3.5)
    positive = ratings_df[ratings_df["rating"] >= 3.5].copy()
    logger.info("Positive interactions: %d", len(positive))

    user_ids = positive["user_id"].unique()
    item_ids = positive["movie_id"].unique()
    user_map = {uid: i for i, uid in enumerate(user_ids)}
    item_map = {iid: i for i, iid in enumerate(item_ids)}

    num_users = len(user_ids)
    num_items = len(item_ids)
    logger.info("Users: %d, Items: %d", num_users, num_items)

    user_indices = np.array([user_map[u] for u in positive["user_id"]])
    item_indices = np.array([item_map[i] for i in positive["movie_id"]])

    from backend.services.recommendation_engine_service.engines.lightgcn import (
        LightGCNModel,
        build_norm_adj,
    )

    norm_adj = build_norm_adj(num_users, num_items, user_indices, item_indices)

    model = LightGCNModel(num_users, num_items, norm_adj)
    optimizer = optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)

    # BPR training
    rng = np.random.default_rng(42)
    user_items = {}
    for u, i in zip(user_indices, item_indices):
        user_items.setdefault(u, set()).add(i)

    logger.info("Training LightGCN...")
    model.train()
    for epoch in range(20):
        total_loss = 0
        perm = rng.permutation(len(user_indices))

        batch_size = 4096
        for start in range(0, len(perm), batch_size):
            batch_idx = perm[start : start + batch_size]
            batch_users = torch.tensor(user_indices[batch_idx], dtype=torch.long)
            batch_pos = torch.tensor(item_indices[batch_idx], dtype=torch.long)

            # Sample negatives
            neg_items = []
            for u in user_indices[batch_idx]:
                neg = rng.integers(0, num_items)
                while neg in user_items.get(u, set()):
                    neg = rng.integers(0, num_items)
                neg_items.append(neg)
            batch_neg = torch.tensor(neg_items, dtype=torch.long)

            user_emb, item_emb = model()
            u_emb = user_emb[batch_users]
            pos_emb = item_emb[batch_pos]
            neg_emb = item_emb[batch_neg]

            pos_scores = (u_emb * pos_emb).sum(dim=1)
            neg_scores = (u_emb * neg_emb).sum(dim=1)

            loss = -torch.log(torch.sigmoid(pos_scores - neg_scores) + 1e-8).mean()
            reg_loss = (
                1e-5
                * (
                    u_emb.norm(2).pow(2)
                    + pos_emb.norm(2).pow(2)
                    + neg_emb.norm(2).pow(2)
                )
                / len(batch_idx)
            )
            total = loss + reg_loss

            optimizer.zero_grad()
            total.backward()
            optimizer.step()
            total_loss += total.item()

        logger.info("Epoch %d: loss=%.4f", epoch + 1, total_loss)

    save_path = MODEL_DIR / "lightgcn.pt"
    torch.save(model.state_dict(), save_path)
    logger.info("Model saved to %s", save_path)


if __name__ == "__main__":
    main()
