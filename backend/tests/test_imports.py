import unittest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


class TestImports(unittest.TestCase):
    def test_app_imports(self):
        """Test that the main app module can be imported."""
        try:
            from backend.app import main

            self.assertIsNotNone(main.app)
        except ImportError as e:
            self.fail(f"Failed to import backend.app.main: {e}")

    def test_engine_imports(self):
        """Test that engines can be imported."""
        try:
            from backend.services.recommendation_engine_service.engines import (
                recommendation,  # noqa: F401
            )
            from backend.services.recommendation_engine_service.engines import (
                vector_engine,  # noqa: F401
            )
            from backend.services.recommendation_engine_service.engines import (
                visual_engine,  # noqa: F401
            )
            from backend.services.recommendation_engine_service.engines import (
                knowledge_graph,  # noqa: F401
            )
            from backend.services.recommendation_engine_service.engines import reranker  # noqa: F401
        except ImportError as e:
            self.fail(f"Failed to import engines: {e}")

    def test_nebula_imports(self):
        """Test that nebula modules can be imported."""
        try:
            from backend.services.recommendation_engine_service.engines.nebula import (
                pipeline,  # noqa: F401
            )
            from backend.services.recommendation_engine_service.engines.nebula import (
                feature_extractor,  # noqa: F401
            )
            from backend.services.recommendation_engine_service.engines.nebula import (
                dna_encoder,  # noqa: F401
            )
        except ImportError as e:
            self.fail(f"Failed to import nebula: {e}")


if __name__ == "__main__":
    unittest.main()
