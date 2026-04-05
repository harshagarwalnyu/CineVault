"""
Visual Search Engine (SOTA FastEmbed Edition)
=============================================
Uses FastEmbed (ONNX) for CLIP inference on CPU.
Supported Model: Qdrant/clip-ViT-B-32-vision
"""

from typing import List, Dict
from fastembed import ImageEmbedding
import numpy as np
import logging

logger = logging.getLogger(__name__)


class VisualSearchEngine:
    def __init__(self):
        self.model = None
        self.is_ready = False

    def load_model(self):
        """Lazy load CLIP ONNX model."""
        if self.model is None:
            logger.info("Loading SOTA Visual Model (CLIP ONNX)...")
            try:
                # Optimized ONNX version of CLIP
                self.model = ImageEmbedding(model_name="Qdrant/clip-ViT-B-32-vision")
                self.is_ready = True
            except Exception as e:
                logger.warning("Failed to load visual model: %s", e)
                self.model = None

    def encode_image(self, image_path: str) -> np.ndarray:
        """Generate embedding for a movie poster."""
        self.load_model()
        if not self.model:
            return np.zeros(512)

        try:
            # FastEmbed accepts file paths or PIL images
            embedding_gen = self.model.embed([image_path])
            return list(embedding_gen)[0]
        except Exception as e:
            logger.warning("Error processing image %s: %s", image_path, e)
            return np.zeros(512)

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Search for visually similar movies using text-to-image search.
        Note: FastEmbed currently supports Image->Embedding.
        For Text->Image retrieval, we rely on the shared latent space property of CLIP.
        """
        logger.info("Processing visual search for: %s", query)

        # The repo does not maintain a separate multimodal image index yet, so use
        # the semantic/vector engine as a truthful visual-style proxy instead of
        # returning hard-coded demo data.
        from backend.services.recommendation_engine_service.engines.vector_engine import (
            get_vector_engine,
        )

        vector_engine = get_vector_engine()
        results = vector_engine.search(query, k=top_k, use_reranker=False)
        for item in results:
            item.setdefault("reason", f'Visual-style proxy match for "{query}"')
        return results


# Singleton
_visual_engine = None


def get_visual_engine():
    global _visual_engine
    if _visual_engine is None:
        _visual_engine = VisualSearchEngine()
    return _visual_engine
