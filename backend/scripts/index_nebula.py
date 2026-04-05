import pandas as pd
from tqdm import tqdm
from sqlmodel import text
from backend.database import engine
from backend.services.recommendation_engine_service.engines.vector_engine import (
    QdrantVectorEngine,
)

# Configuration
BATCH_SIZE = 32  # Ultra-safe Mode
TOTAL_TARGET = 1_200_000


def fetch_movie_batch(offset: int, limit: int) -> pd.DataFrame:
    """Fetch a batch of movies from Postgres/SQLite."""
    query = text(f"""
        SELECT id, title, overview, genres, imdb_rating 
        FROM movies 
        WHERE title IS NOT NULL
        ORDER BY imdb_votes DESC
        LIMIT {limit} OFFSET {offset}
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def index_nebula():
    print("🚀 Initializing NEBULA Indexing Engine...")

    # Initialize Vector Engine (Qdrant + FastEmbed)
    ve = QdrantVectorEngine()
    ve.initialize_collection()
    model = ve.load_model()

    print(f"🎯 Target: Indexing top {TOTAL_TARGET} movies by popularity...")

    # Check current count
    try:
        current_count = ve.client.count(ve.collection_name).count
        print(f"📊 Current Vector Count: {current_count}")
        if current_count >= TOTAL_TARGET:
            print("✅ Indexing already complete!")
            return
    except Exception as e:
        print(f"⚠️ Could not check current count: {e}")
        current_count = 0

    # Main Indexing Loop
    pbar = tqdm(total=TOTAL_TARGET, initial=current_count, unit="movies")

    offset = current_count

    while offset < TOTAL_TARGET:
        # 1. Fetch Data
        df = fetch_movie_batch(offset, BATCH_SIZE)
        if df.empty:
            print("⚠️ No more movies found in DB.")
            break

        # 2. Prepare Documents for Embedding
        # Format: "Title: <title> Genres: <genres> Overview: <overview>"
        documents = (
            "search_document: "
            + df["title"]
            + " "
            + "Genres: "
            + df["genres"].fillna("")
            + " "
            + df["overview"].fillna("")
        ).tolist()

        # 3. Generate Embeddings (CPU/GPU)
        # FastEmbed is optimized for bulk
        embeddings = list(model.embed(documents, batch_size=BATCH_SIZE))

        # 4. Upsert to Qdrant
        from qdrant_client import models

        points = []
        for i, row in enumerate(df.itertuples()):
            # Safe Int conversion for ID
            try:
                # If ID is integer, use it. If not (unlikely in our schema), hash it.
                idx = int(row.id)
            except ValueError:
                continue

            points.append(
                models.PointStruct(
                    id=idx,
                    vector=embeddings[i].tolist(),
                    payload={
                        "title": row.title,
                        "genres": row.genres,
                        "rating": row.imdb_rating,
                        "id": idx,
                    },
                )
            )

        if points:
            ve.client.upsert(collection_name=ve.collection_name, points=points)

        # 5. Update Progress
        offset += len(df)
        pbar.update(len(df))

    pbar.close()
    print("✅ NEBULA Indexing Complete.")


if __name__ == "__main__":
    index_nebula()
