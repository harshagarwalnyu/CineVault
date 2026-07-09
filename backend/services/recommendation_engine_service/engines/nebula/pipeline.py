import torch
import os
from backend.services.recommendation_engine_service.engines.nebula.feature_extractor import (
    CinematographicFeatureExtractor,
)
from backend.services.recommendation_engine_service.engines.nebula.dna_encoder import (
    get_dna_model,
)

import pandas as pd
import json
from typing import Optional


class NebulaIngestPipeline:
    """
    Project NEBULA: Week 1 Orchestrator
    Bridges raw video extraction with the DNA latent space.
    """

    def __init__(self, model_path: str = "backend/nebula/dna_model.pt"):
        self.extractor = CinematographicFeatureExtractor()
        self.encoder = get_dna_model()
        self.model_path = model_path

        if os.path.exists(model_path):
            # CVE-2022-45907: Use weights_only=True for safe loading
            self.encoder.load_state_dict(torch.load(model_path, weights_only=True))
            print(f"Loaded NEBULA DNA Encoder from {model_path}")
        else:
            print("Initialized fresh DNA Encoder. (Note: Should be trained in Week 2)")

        self.encoder.eval()

    def process_movie(self, movie_id: int, video_path: Optional[str] = None):
        """Processes a single movie and returns its DNA vector."""
        print(f"Processing movie ID: {movie_id}...")

        # 1. Extract raw signals
        # If video_path is None, extractor uses mock data automatically
        features_np = self.extractor.extract_features(
            video_path or f"mock_{movie_id}.mp4"
        )

        # 2. Convert to Tensors
        features_torch = {
            k: torch.from_numpy(v).unsqueeze(0) for k, v in features_np.items()
        }

        # 3. Encode to DNA
        with torch.no_grad():
            dna_vector = self.encoder(features_torch)

        return dna_vector.squeeze(0).cpu().numpy()

    def run_ingest(self, limit: int = 10):
        """Runs the pipeline for a set of movies and stores the DNA."""
        from sqlmodel import text
        from backend.database import engine

        query = text("SELECT id, title FROM movies LIMIT :limit")
        with engine.connect() as conn:
            movies = pd.read_sql_query(query, conn, params={"limit": limit})

        results = []
        for _, movie in movies.iterrows():
            dna = self.process_movie(movie["id"])
            results.append(
                {"id": movie["id"], "title": movie["title"], "dna_vector": dna.tolist()}
            )

        # For Week 1, we'll save these to a JSON for verification
        # In Week 2, we'll move these to Qdrant/Postgres
        output_path = "data/dna_results_v1.json"
        with open(output_path, "w") as f:
            json.dump(results, f)

        print(
            f"Completed ingestion for {len(results)} movies. DNA saved to {output_path}"
        )

    def process_batch(self, movie_ids: list):
        """Process multiple movies and store DNA in Qdrant."""
        from sqlmodel import text as sql_text
        from backend.database import engine
        from backend.config import settings

        results = []
        with engine.connect() as conn:
            for movie_id in movie_ids:
                row = conn.execute(
                    sql_text(
                        "SELECT id, title, trailer_youtube_key FROM movies WHERE id = :mid"
                    ),
                    {"mid": movie_id},
                ).fetchone()
                if not row:
                    continue

                trailer_key = row[2] if len(row) > 2 else None
                if trailer_key:
                    features = self.extractor.extract_from_trailer(trailer_key)
                else:
                    features = self.extractor.get_mock_features()

                features_torch = {
                    k: torch.from_numpy(v).unsqueeze(0) for k, v in features.items()
                }
                with torch.no_grad():
                    dna = self.encoder(features_torch).squeeze(0).cpu().numpy()

                results.append({"id": row[0], "title": row[1], "dna": dna.tolist()})

        # Store in Qdrant
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams, PointStruct

            client = QdrantClient(url=settings.QDRANT_URL)
            collection = settings.NEBULA_COLLECTION_NAME

            # Ensure collection exists
            try:
                client.get_collection(collection)
            except Exception:
                client.create_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(size=128, distance=Distance.COSINE),
                )

            points = [
                PointStruct(
                    id=r["id"],
                    vector=r["dna"],
                    payload={"title": r["title"], "movie_id": r["id"]},
                )
                for r in results
            ]
            if points:
                client.upsert(collection_name=collection, points=points)

        except Exception as e:
            print(f"Qdrant storage failed: {e}")

        return results

    def get_dna(self, movie_id: int) -> Optional[dict]:
        """Get stored DNA for a movie from Qdrant."""
        try:
            from qdrant_client import QdrantClient
            from backend.config import settings

            client = QdrantClient(url=settings.QDRANT_URL)
            result = client.retrieve(
                collection_name=settings.NEBULA_COLLECTION_NAME, ids=[movie_id]
            )
            if result:
                return {
                    "movie_id": movie_id,
                    "vector": result[0].vector,
                    "payload": result[0].payload,
                }
        except Exception:
            pass
        return None

    def find_visual_similar(self, movie_id: int, k: int = 10) -> list:
        """Find visually similar movies using DNA vectors."""
        try:
            from qdrant_client import QdrantClient
            from backend.config import settings

            client = QdrantClient(url=settings.QDRANT_URL)
            results = client.recommend(
                collection_name=settings.NEBULA_COLLECTION_NAME,
                positive=[movie_id],
                limit=k,
            )
            return [
                {
                    "movie_id": r.id,
                    "score": r.score,
                    "title": r.payload.get("title", ""),
                }
                for r in results
            ]
        except Exception:
            return []


# Singleton
_pipeline = None


def get_nebula_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = NebulaIngestPipeline()
    return _pipeline


if __name__ == "__main__":
    pipeline = NebulaIngestPipeline()
    pipeline.run_ingest(limit=5)
