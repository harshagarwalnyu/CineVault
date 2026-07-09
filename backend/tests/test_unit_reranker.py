import pytest
from unittest.mock import MagicMock, patch
from backend.services.recommendation_engine_service.engines.reranker import Reranker


@pytest.mark.unit
def test_reranker_init_no_api_key(monkeypatch):
    monkeypatch.delenv("COHERE_API_KEY", raising=False)

    # Mock FlashRank to avoid downloading model
    with patch(
        "backend.services.recommendation_engine_service.engines.reranker.Ranker"
    ):
        reranker = Reranker()
        assert reranker.cohere_client is None
        assert reranker.flash_ranker is not None


@pytest.mark.unit
def test_reranker_cohere_strategy(monkeypatch):
    monkeypatch.setenv("COHERE_API_KEY", "test_key")

    with (
        patch("cohere.Client") as mock_cohere_cls,
        patch("backend.services.recommendation_engine_service.engines.reranker.Ranker"),
        patch(
            "backend.services.recommendation_engine_service.engines.reranker.COHERE_API_KEY",
            "test_key",
        ),
    ):
        mock_client = MagicMock()
        mock_cohere_cls.return_value = mock_client

        # Mock response
        mock_hit = MagicMock()
        mock_hit.index = 0
        mock_hit.relevance_score = 0.99
        mock_client.rerank.return_value.results = [mock_hit]

        reranker = Reranker()
        candidates = [{"title": "Test Movie", "id": 1}]

        results = reranker.rerank("query", candidates)

        assert len(results) == 1
        assert results[0]["rerank_score"] == 0.99
        mock_client.rerank.assert_called_once()


@pytest.mark.unit
def test_reranker_fallback_logic(monkeypatch):
    # Case 1: Cohere fails, fallback to FlashRank
    monkeypatch.setenv("COHERE_API_KEY", "test_key")

    with (
        patch("cohere.Client") as mock_cohere_cls,
        patch(
            "backend.services.recommendation_engine_service.engines.reranker.Ranker"
        ) as mock_flashrank_cls,
    ):
        mock_cohere = MagicMock()
        mock_cohere.rerank.side_effect = Exception("API Error")
        mock_cohere_cls.return_value = mock_cohere

        mock_flashrank = MagicMock()
        mock_flashrank.rerank.return_value = [
            {"meta": {"id": 1, "title": "Test"}, "score": 0.8}
        ]
        mock_flashrank_cls.return_value = mock_flashrank

        reranker = Reranker()
        candidates = [{"id": 1, "title": "Test"}]

        results = reranker.rerank("query", candidates)

        assert len(results) == 1
        assert results[0]["rerank_score"] == 0.8  # From FlashRank
