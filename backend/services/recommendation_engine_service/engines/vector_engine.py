"""
Qdrant Vector Engine (SOTA FastEmbed Edition)
=============================================
Uses FastEmbed (ONNX Runtime) for ultra-fast CPU/iGPU inference.
Model: Nomic Embed Text v1.5 (Matryoshka / Quantized)
"""

from typing import List, Dict
import pandas as pd
from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models
from tqdm import tqdm
from backend.config import QDRANT_URL
import logging

logger = logging.getLogger(__name__)


class QdrantVectorEngine:
    def __init__(self, collection_name="movies_sota_quantized"):
        self.collection_name = collection_name
        self.model = None
        self._model_load_attempted = False
        self.storage_mode = "remote"

        # Connect to Qdrant (Docker or Memory)
        qdrant_url = QDRANT_URL
        try:
            self.client = QdrantClient(url=qdrant_url)
            self.client.get_collections()  # Check connection
            self.is_connected = True
        except Exception:
            logger.warning(
                "Could not connect to Qdrant. Falling back to in-memory mode."
            )
            self.client = QdrantClient(":memory:")
            self.is_connected = False
            self.storage_mode = "in_memory"

        self.is_ready = False

    def load_model(self):
        if self.model is None and not self._model_load_attempted:
            self._model_load_attempted = True
            # SOTA 2026: BAAI/bge-m3 (Multilingual, 1024d)
            # Automatically uses ONNX Runtime (fast on CPU)
            logger.info("Loading SOTA Quantized Model (BAAI BGE-M3)...")
            try:
                self.model = TextEmbedding(model_name="BAAI/bge-m3")
            except Exception as exc:
                logger.warning(
                    "Vector model unavailable, semantic search will fall back to metadata search: %s",
                    exc,
                )
                self.model = None
        return self.model

    def initialize_collection(self):
        """Create collection if not exists."""
        self.load_model()
        if self.model is None:
            return
        # BGE-M3 is 1024d
        vector_size = 1024

        collections = self.client.get_collections()
        exists = any(c.name == self.collection_name for c in collections.collections)

        if not exists:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size, distance=models.Distance.COSINE
                ),
                quantization_config=models.ScalarQuantization(
                    scalar=models.ScalarQuantizationConfig(
                        type=models.ScalarType.INT8, quantile=0.99, always_ram=True
                    )
                ),
            )
            logger.info(
                f"Created collection '{self.collection_name}' with Scalar Quantization (INT8)"
            )
            self.index_data()
        else:
            count = self.client.count(self.collection_name)
            if count.count == 0:
                self.index_data()

        self.is_ready = True

    def index_data(self, limit: int = 20000, batch_size: int = 100):
        """Read from DB and index into Qdrant using FastEmbed."""
        logger.info(f"Indexing top {limit} movies into Qdrant (FastEmbed)...")
        from sqlmodel import text
        from backend.database import engine

        query = text("""
            SELECT id, title, overview, genres
            FROM movies 
            WHERE overview IS NOT NULL AND overview != ''
            ORDER BY vote_count DESC
            LIMIT :limit
        """)
        with engine.connect() as conn:
            df = pd.read_sql_query(query, conn, params={"limit": limit})

        if df.empty:
            logger.warning("No movies found to index.")
            return

        model = self.load_model()
        if model is None:
            logger.warning("Skipping vector indexing because the embedding model is unavailable.")
            return

        # Prepare text batch
        documents = (
            "search_document: "
            + df["title"]
            + ": "
            + df["overview"].fillna("")
            + " "
            + df["genres"].fillna("")
        ).tolist()

        logger.info(f"Generating embeddings for {len(documents)} docs...")

        # FastEmbed generator with progress bar
        # We process in batches to show progress


        with tqdm(total=len(documents), desc="Embedding", unit="doc") as pbar:
            for i in range(0, len(df), batch_size):
                batch_df = df.iloc[i : i + batch_size]
                batch_docs = documents[i : i + batch_size]

                # Generate embeddings for this batch
                batch_vectors = list(model.embed(batch_docs, batch_size=batch_size))

                points = []
                for idx, vector in enumerate(batch_vectors):
                    row = batch_df.iloc[idx]
                    points.append(
                        models.PointStruct(
                            id=int(row["id"]),
                            vector=vector.tolist(),
                            payload={
                                "id": int(row["id"]),
                                "title": row["title"],
                                "genres": row["genres"],
                                "overview": row["overview"],
                            },
                        )
                    )

                self.client.upsert(collection_name=self.collection_name, points=points)
                pbar.update(len(batch_docs))

        logger.info(f"Successfully indexed {len(df)} movies.")

    def search(self, query: str, k: int = 10, use_reranker: bool = False) -> List[Dict]:
        if not self.is_ready:
            self.initialize_collection()

        model = self.load_model()
        if model is None:
            from backend.services.recommendation_engine_service.engines.recommendation import get_engine

            fallback_engine = get_engine()
            fallback_results, _ = fallback_engine.search_movies(query=query, limit=k)
            for item in fallback_results:
                item.setdefault("score", 0.0)
            return fallback_results
        # BGE-M3 handles queries natively
        query_text = query

        # embed returns a generator, get first item
        query_vector = list(model.embed([query_text]))[0].tolist()

        search_result = self.client.query_points(
            collection_name=self.collection_name, query=query_vector, limit=k * 3
        ).points

        candidates = [
            {
                "id": hit.payload["id"],
                "title": hit.payload["title"],
                "genres": hit.payload["genres"],
                "overview": hit.payload.get("overview", ""),
                "score": hit.score,
            }
            for hit in search_result
        ]

        if not use_reranker:
            return candidates[:k]

        # Apply SOTA Reranking (FlashRank / Cohere)
        from backend.services.recommendation_engine_service.engines.reranker import get_reranker

        reranker = get_reranker()
        reranked_results = reranker.rerank(query, candidates, top_k=k)

        return reranked_results


# Adapter
VectorEngine = QdrantVectorEngine

_vector_engine = None


def get_vector_engine():
    global _vector_engine
    if _vector_engine is None:
        _vector_engine = QdrantVectorEngine()
    return _vector_engine
