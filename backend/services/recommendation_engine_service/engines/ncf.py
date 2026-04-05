"""
Neural Collaborative Filtering (NCF) Module
============================================
A PyTorch implementation of NCF (GMF + MLP) for advanced recommendations.
Note: This is a production-ready template. To use, you need to train it on real user data.
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset


class MovieDataset(Dataset):
    def __init__(self, users, items, ratings):
        self.users = torch.tensor(users, dtype=torch.long)
        self.items = torch.tensor(items, dtype=torch.long)
        self.ratings = torch.tensor(ratings, dtype=torch.float32)

    def __len__(self):
        return len(self.users)

    def __getitem__(self, idx):
        return self.users[idx], self.items[idx], self.ratings[idx]


class NCF(nn.Module):
    def __init__(self, num_users, num_items, embedding_dim=32, layers=[64, 32, 16]):
        super(NCF, self).__init__()

        # Generalized Matrix Factorization (GMF)
        self.gmf_user_embedding = nn.Embedding(num_users, embedding_dim)
        self.gmf_item_embedding = nn.Embedding(num_items, embedding_dim)

        # Multi-Layer Perceptron (MLP)
        self.mlp_user_embedding = nn.Embedding(num_users, embedding_dim)
        self.mlp_item_embedding = nn.Embedding(num_items, embedding_dim)

        mlp_modules = []
        input_size = embedding_dim * 2
        for layer_size in layers:
            mlp_modules.append(nn.Linear(input_size, layer_size))
            mlp_modules.append(nn.ReLU())
            mlp_modules.append(nn.Dropout(0.2))
            input_size = layer_size
        self.mlp_layers = nn.Sequential(*mlp_modules)

        # Final prediction layer
        self.predict_layer = nn.Linear(embedding_dim + layers[-1], 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, user, item):
        # GMF Path
        gmf_u = self.gmf_user_embedding(user)
        gmf_i = self.gmf_item_embedding(item)
        gmf_vector = gmf_u * gmf_i

        # MLP Path
        mlp_u = self.mlp_user_embedding(user)
        mlp_i = self.mlp_item_embedding(item)
        mlp_vector = torch.cat([mlp_u, mlp_i], dim=-1)
        mlp_vector = self.mlp_layers(mlp_vector)

        # Concatenate and Predict
        vector = torch.cat([gmf_vector, mlp_vector], dim=-1)
        output = self.predict_layer(vector)
        return self.sigmoid(output)


class DeepRecommender:
    def __init__(self, num_users, num_items):
        self.model = NCF(num_users, num_items)
        self.optimizer = optim.Adam(self.model.parameters(), lr=0.001)
        self.criterion = nn.BCELoss()

    def train(self, dataloader, epochs=5):
        self.model.train()
        for epoch in range(epochs):
            total_loss = 0
            for users, items, ratings in dataloader:
                self.optimizer.zero_grad()
                predictions = self.model(users, items).squeeze()
                loss = self.criterion(predictions, ratings)
                loss.backward()
                self.optimizer.step()
                total_loss += loss.item()
            print(f"Epoch {epoch + 1}/{epochs}, Loss: {total_loss:.4f}")

    def predict(self, user_id, item_id):
        self.model.eval()
        with torch.no_grad():
            user = torch.tensor([user_id])
            item = torch.tensor([item_id])
            prediction = self.model(user, item)
            return prediction.item()


# Usage Example:
# recommender = DeepRecommender(num_users=1000, num_items=5000)
# dataset = MovieDataset(users, items, ratings)
# loader = DataLoader(dataset, batch_size=64, shuffle=True)
# recommender.train(loader)
