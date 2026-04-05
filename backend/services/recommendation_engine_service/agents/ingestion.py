"""
NEBULA Ingestion Agent
======================
Handles the mass ingestion and processing of movies into the NEBULA manifold.
"""

import logging
from backend.services.recommendation_engine_service.engines.nebula.pipeline import (
    NebulaIngestPipeline,
)
from backend.services.recommendation_engine_service.engines.vector_engine import (
    get_vector_engine,
)
from backend.database import engine, text
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IngestionAgent:
    def __init__(self):
        self.pipeline = NebulaIngestPipeline()
        self.vector_engine = get_vector_engine()

    def process_batch(self, limit: int = 1000):
        """
        Processes a batch of movies: extract DNA and index into Qdrant.
        """
        logger.info(f"Ingestion Agent: Processing batch of {limit} movies...")

        # 1. Fetch movies from DB that don't have DNA yet (or just top N for now)
        query = text("""
            SELECT id, title, overview, genres 
            FROM movies 
            ORDER BY popularity_score DESC 
            LIMIT :limit
        """)

        with engine.connect() as conn:
            df = pd.read_sql_query(query, conn, params={"limit": limit})

        if df.empty:
            logger.info("No movies found for processing.")
            return

        # 2. Extract DNA vectors
        processed_points = []
        for _, row in df.iterrows():
            try:
                # In a real scenario, this would involve video analysis
                dna = self.pipeline.process_movie(row["id"])

                processed_points.append(
                    {
                        "id": int(row["id"]),
                        "dna_vector": dna.tolist(),
                        "payload": {
                            "id": int(row["id"]),
                            "title": row["title"],
                            "genres": row["genres"],
                        },
                    }
                )
            except Exception as e:
                logger.error(f"Failed to process movie {row['id']}: {e}")

        # 3. Upsert to Qdrant (using a specific NEBULA collection)
        if processed_points:
            logger.info(f"Indexing {len(processed_points)} DNA vectors into Qdrant...")
            # We'd typically use a different collection for DNA vs standard text embeddings
            collection_name = "nebula_dna_manifold"

            # Ensure collection exists
            self._ensure_collection(
                collection_name, vector_size=len(processed_points[0]["dna_vector"])
            )

            # Use Qdrant client directly or extend vector_engine
            from qdrant_client.http import models as rest_models

            points = [
                rest_models.PointStruct(
                    id=p["id"], vector=p["dna_vector"], payload=p["payload"]
                )
                for p in processed_points
            ]

            self.vector_engine.client.upsert(
                collection_name=collection_name, points=points
            )
            logger.info("Batch processing complete.")

    def _ensure_collection(self, name: str, vector_size: int):
        from qdrant_client.http import models as rest_models

        collections = self.vector_engine.client.get_collections()
        exists = any(c.name == name for c in collections.collections)

        if not exists:
            self.vector_engine.client.create_collection(
                collection_name=name,
                vectors_config=rest_models.VectorParams(
                    size=vector_size, distance=rest_models.Distance.COSINE
                ),
            )
            logger.info(f"Created NEBULA collection: {name}")


if __name__ == "__main__":
    agent = IngestionAgent()
    agent.process_batch(limit=10)
