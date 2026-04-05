import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict


class CinematographicDNAEncoder(nn.Module):
    """
    Week 1: The Eyes & Ears
    Compresses raw cinematographic signals into a fixed-length DNA vector.
    """

    def __init__(self, color_dim: int = 512, hidden_dim: int = 256, dna_dim: int = 128):
        super(CinematographicDNAEncoder, self).__init__()

        # Color Path: Processes temporal color shifts
        self.color_encoder = nn.Sequential(
            nn.Linear(color_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
        )

        # Pacing Path: Processes shot boundaries and motion
        self.pacing_encoder = nn.Sequential(
            nn.Linear(2, 64),  # Input: [shot_boundary_score, motion_score]
            nn.ReLU(),
            nn.Linear(64, 32),
        )

        # Fusion: Combines both paths
        self.fusion = nn.Sequential(
            nn.Linear((hidden_dim // 2) + 32, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, dna_dim),
        )

    def forward(self, features: Dict[str, torch.Tensor]) -> torch.Tensor:
        """
        Args:
            features: Dictionary containing:
                - 'color_histograms': [Batch, Time, 512]
                - 'shot_boundaries': [Batch, Time]
                - 'motion_complexity': [Batch, Time]
        Returns:
            dna_vector: [Batch, dna_dim]
        """
        color_h = features["color_histograms"]
        shot_b = features["shot_boundaries"].unsqueeze(-1)
        motion_c = features["motion_complexity"].unsqueeze(-1)

        # 1. Process Color (Temporal Average Pooling)
        # In a real SOTA system, we might use a Transformer or GRU here.
        # For the prototype, we use temporal mean.
        color_feat = self.color_encoder(color_h)
        color_pooled = torch.mean(color_feat, dim=1)

        # 2. Process Pacing (Combine shot boundaries and motion)
        pacing_input = torch.cat([shot_b, motion_c], dim=-1)
        pacing_feat = self.pacing_encoder(pacing_input)
        pacing_pooled = torch.mean(pacing_feat, dim=1)

        # 3. Fuse
        combined = torch.cat([color_pooled, pacing_pooled], dim=-1)
        dna_vector = self.fusion(combined)

        # Normalize to unit hypersphere for easier cosine similarity
        return F.normalize(dna_vector, p=2, dim=1)


def get_dna_model(dna_dim: int = 128):
    model = CinematographicDNAEncoder(dna_dim=dna_dim)
    return model


if __name__ == "__main__":
    # Test with dummy data
    model = get_dna_model()
    dummy_input = {
        "color_histograms": torch.randn(1, 100, 512),
        "shot_boundaries": torch.randn(1, 100),
        "motion_complexity": torch.randn(1, 100),
    }
    with torch.no_grad():
        dna = model(dummy_input)
    print(f"Generated DNA vector shape: {dna.shape}")  # Should be [1, 128]
