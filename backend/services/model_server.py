"""
Model Server — loads and serves PyTorch models on app startup.
Supports: Two-Tower, LightGCN, Session Transformer.
"""

import logging
from pathlib import Path
from typing import Optional

import torch

logger = logging.getLogger(__name__)

MODEL_DIR = Path("data/models")


class ModelServer:
    """In-process model serving with version tracking and hot-reload."""

    def __init__(self):
        self.models: dict[str, torch.nn.Module] = {}
        self.model_versions: dict[str, float] = {}
        self._loaded = False

    def load_all(self):
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        model_files = {
            "two_tower": MODEL_DIR / "two_tower.pt",
            "lightgcn": MODEL_DIR / "lightgcn.pt",
            "session": MODEL_DIR / "session_transformer.pt",
        }
        for name, path in model_files.items():
            self._load_model(name, path)
        self._loaded = True

    def _load_model(self, name: str, path: Path):
        if not path.exists():
            logger.info("Model %s not found at %s, skipping", name, path)
            return
        try:
            model = torch.load(path, map_location="cpu", weights_only=False)
            self.models[name] = model
            self.model_versions[name] = path.stat().st_mtime
            logger.info("Loaded model %s from %s", name, path)
        except Exception as e:
            logger.warning("Failed to load model %s: %s", name, e)

    def get_model(self, name: str) -> Optional[torch.nn.Module]:
        return self.models.get(name)

    def check_for_updates(self):
        model_files = {
            "two_tower": MODEL_DIR / "two_tower.pt",
            "lightgcn": MODEL_DIR / "lightgcn.pt",
            "session": MODEL_DIR / "session_transformer.pt",
        }
        for name, path in model_files.items():
            if not path.exists():
                continue
            current_mtime = path.stat().st_mtime
            if name not in self.model_versions or current_mtime > self.model_versions[name]:
                logger.info("Detected updated weights for %s, reloading...", name)
                self._load_model(name, path)

    @property
    def is_loaded(self) -> bool:
        return self._loaded


_server: Optional[ModelServer] = None


def get_model_server() -> ModelServer:
    global _server
    if _server is None:
        _server = ModelServer()
        _server.load_all()
    return _server
