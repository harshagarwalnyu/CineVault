import pytest
import torch
from backend.services.recommendation_engine_service.engines.ncf import (
    NCF,
    DeepRecommender,
    MovieDataset,
)
from torch.utils.data import DataLoader


@pytest.mark.unit
def test_ncf_model_architecture():
    num_users = 100
    num_items = 50
    model = NCF(num_users, num_items, embedding_dim=16, layers=[32, 16])

    user = torch.tensor([0, 1])
    item = torch.tensor([0, 1])

    # Test forward pass
    output = model(user, item)
    assert output.shape == (2, 1)
    assert 0 <= output.min() <= 1
    assert 0 <= output.max() <= 1


@pytest.mark.unit
def test_dataset_initialization():
    users = [0, 1, 2]
    items = [10, 11, 12]
    ratings = [5.0, 4.0, 3.0]

    dataset = MovieDataset(users, items, ratings)
    assert len(dataset) == 3
    u, i, r = dataset[0]
    assert u == 0
    assert i == 10
    assert r == 5.0


@pytest.mark.unit
def test_deep_recommender_prediction():
    recommender = DeepRecommender(num_users=10, num_items=10)
    score = recommender.predict(1, 1)
    assert isinstance(score, float)
    assert 0 <= score <= 1


@pytest.mark.unit
def test_deep_recommender_train(mocker):
    # Mock the optimizer and backward pass to speed up test
    recommender = DeepRecommender(num_users=10, num_items=10)

    # Create dummy data
    users = [0, 1]
    items = [0, 1]
    ratings = [1.0, 0.0]
    dataset = MovieDataset(users, items, ratings)
    loader = DataLoader(dataset, batch_size=2)

    # Spy on optimizer step
    optimizer_spy = mocker.spy(recommender.optimizer, "step")

    recommender.train(loader, epochs=1)
    assert optimizer_spy.call_count == 1
