# Project NEBULA: Cognitive Cinema Engine 🌌

This is the **Next-Generation** branch of the Movie Recommender, implementing 2026-tier Neuro-Symbolic AI.

## 🚀 Status: Week 1 Complete (The Eyes & Ears)

### Completed Features:
- **Cinematographic DNA Extraction**: A pipeline that analyzes raw video signals (Shot boundaries, color palettes, and motion complexity).
- **DNA Encoder**: A PyTorch-based neural model that compresses temporal cinematographic signals into a fixed 128-dimensional latent vector.
- **High-Speed Environment**: Switched to `uv` for dependency management and environment isolation.
- **Docker Ready**: `Dockerfile.nebula` provided for containerized "Deep Tech" workloads.

### 🛠 Tech Stack:
- **Engine**: PyTorch (Neural DNA Encoding)
- **Computer Vision**: OpenCV (Frame-level analysis)
- **Environment**: `uv` (Fastest Python package manager)
- **Architecture**: Variational Autoencoders (VAEs) + Active Inference (Coming in Weeks 2-4).

## 🏃 How to Run (Week 1 Pipeline)

### Local (with uv):
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
# Sync environment
uv sync
# Run pipeline (Mock mode)
DATABASE_URL=sqlite:///movies_recommender.db uv run nebula/pipeline.py
```

### Docker:
```bash
docker build -t nebula-engine -f Dockerfile.nebula .
docker run nebula-engine
```

## 📅 Roadmap:
- **Week 2**: The Dreaming Mind (Latent Manifold & VAE Training).
- **Week 3**: The Secret Vault (Fully Homomorphic Encryption for Privacy).
- **Week 4**: The Agent Swarm (Active Inference & Expected Information Gain).
