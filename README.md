<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Next.js_16-000000?style=for-the-badge&logo=nextdotjs&logoColor=white" alt="Next.js" />
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/React_19-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React 19" />
  <img src="https://img.shields.io/badge/PyTorch-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white" alt="PyTorch" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
</p>

# CineVault -- AI Movie Discovery Engine

> A production-grade movie recommendation system that combines **14 specialized ML engines**, a **knowledge graph**, an **LLM-powered conversational agent**, and a **Netflix-inspired frontend** into a single deployable stack. Not a notebook. Not a prototype. A real application.

---

## Why This Exists

Every movie recommendation project on GitHub falls into one of two categories:

1. **Academic notebooks** -- great theory, zero usability. You download a dataset, run cells, read a confusion matrix, and close the tab.
2. **Simple web apps** -- a search bar, a poster grid, and content-based filtering that recommends "The Dark Knight" if you liked "Batman Begins."

Neither reflects how modern recommendation systems actually work at companies like Netflix, Spotify, or YouTube. Those systems use **ensembles of specialized engines** (collaborative filtering, neural embeddings, knowledge graphs, mood analysis) orchestrated through a **ranking pipeline** with **reranking** and **serendipity injection**.

CineVault bridges this gap. It implements the full production recommendation stack -- from candidate generation through ranking to explanation -- with a real UI, real API, and real infrastructure. One command to start. No manual dataset downloads.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Recommendation Engines](#recommendation-engines)
- [Frontend Pages](#frontend-pages)
- [API Reference](#api-reference)
- [Quick Start](#quick-start)
- [Local Development](#local-development)
- [Configuration](#configuration)
- [Data Pipeline](#data-pipeline)
- [Tech Stack](#tech-stack)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Operations](#operations)
- [License](#license)

---

## Features

### Core Recommendation Intelligence

- **14 specialized ML engines** running in ensemble (content-based, collaborative, neural, graph-based, visual, mood, serendipity)
- **Hybrid ranking pipeline** that fuses scores from all engines with learned weights
- **Cross-encoder reranking** using FlashRank (ms-marco-TinyBERT) for final result quality
- **Knowledge graph** with Louvain community detection for entity-relationship discovery
- **Mood-based discovery** powered by Gemini LLM -- describe how you feel, get movie recommendations
- **Serendipity injection** -- deliberately introduces high-quality surprises into ranked lists to prevent filter bubbles
- **Session intelligence** -- Transformer-based session continuation predicts what you want to watch next based on browsing patterns (not just last-click fallback)
- **NEBULA Visual DNA** -- extracts cinematographic features (color palettes, shot composition, motion profiles) from movie trailers to build a visual latent space for cinema-aware similarity
- **Mood arc playlists** -- creates time-evolving movie sequences (e.g., evening: relaxed -> tense -> melancholic -> inspired) for narrative viewing experiences

### AI & Search

- **Conversational AI agent** (LangGraph + GROQ) that can discuss movies, take user preferences, and generate personalized recommendations through natural dialogue
- **Agentic discovery** via GraphRAG -- an LLM navigates the knowledge graph to answer complex queries ("movies that connect Tarantino to Kurosawa")
- **Semantic vector search** using Qdrant with sentence-transformers embeddings
- **Full-text search** with advanced filtering (genre, director, actor, year range, rating range, sort order)
- **Visual search** using CLIP (ViT-B/32) via FastEmbed -- find movies by poster similarity

### Frontend Experience

- **Netflix-inspired UI** with cinematic design, smooth animations (Framer Motion), and responsive poster grids
- **Taste Fingerprint** -- visual radar chart showing a user's preference profile across genres and decades
- **Time Machine** -- browse cinema history decade by decade with contextual recommendations
- **Movie Connections** -- interactive graph visualization (react-force-graph-2d) showing how movies relate through shared actors, directors, and genres
- **Director filmography** pages with deep-linked navigation
- **User onboarding flow** to cold-start the recommendation engine with initial preferences

### Infrastructure

- **L1/L2 caching** -- in-process LRU cache (sub-microsecond) backed by Redis (sub-millisecond)
- **Rate limiting** via SlowAPI (100 req/15 min per IP)
- **Security headers** -- CSP, HSTS, X-Frame-Options, Referrer-Policy
- **Graceful degradation** -- every engine and external service (Qdrant, Redis, Elasticsearch, Gemini) fails gracefully; the API never crashes due to an optional dependency being down
- **Health endpoint** with SLO tracking (error rate, p95 latency, request counts)
- **GZip compression** for API responses
- **Docker Compose** with 5 services, health checks, named volumes, and development watch mode

---

## Architecture

```
                                   +-------------------+
                                   |   Next.js 16 UI   |
                                   |   (Turbopack)      |
                                   +--------+----------+
                                            |
                                   HTTP (localhost:3002)
                                            |
                                            v
+------------------+            +------------------------+            +----------------+
|   SurrealDB      |<---------->|    FastAPI Backend     |<---------->|    Qdrant       |
|   (Graph DB)     |            |    (Python 3.12)       |            |  (Vector DB)    |
+------------------+            +-----+------+-----------+            +----------------+
                                      |      |
                          +-----------+      +-----------+
                          |                              |
                          v                              v
                   +-------------+              +---------------+
                   |   SQLite    |              |    Redis      |
                   |  (7,880     |              |  (L2 Cache    |
                   |   movies)   |              |   + Sessions) |
                   +-------------+              +---------------+
```

### Request Flow

1. **Frontend** server-renders pages via Next.js App Router, calling the backend API server-side
2. **API** receives request, checks L1 cache (in-process) -> L2 cache (Redis) -> computes if miss
3. **Recommendation Pipeline**: candidate generation (multiple engines) -> score fusion -> reranking -> serendipity injection -> response
4. **Caching**: result stored in both L1 and L2 with configurable TTL and `Cache-Control` headers

---

## Recommendation Engines

CineVault runs **10 specialized engines** in parallel, each excelling at a different aspect of recommendation:

| Engine | Algorithm | What It Does |
|--------|-----------|-------------|
| **Content-Based** | TF-IDF + cosine similarity | Recommends movies with similar genres, keywords, cast, and director |
| **Collaborative Filtering** | User-item matrix factorization | "Users who liked X also liked Y" based on rating patterns |
| **Neural Collaborative Filtering (NCF)** | GMF + MLP (PyTorch) | Deep learning version of collaborative filtering with nonlinear feature interactions |
| **Two-Tower** | Dual encoder (user + item towers) | Generates 128-dim embeddings for users and items, retrieves candidates via ANN search |
| **LightGCN** | 3-layer Graph Neural Network (PyTorch) | Graph-based collaborative filtering using message passing on the user-item bipartite graph |
| **Knowledge Graph** | NetworkX + Louvain communities | Discovers hidden connections between movies through shared entities (actors, directors, genres) |
| **Mood Engine** | Gemini LLM + genre affinity vectors | Translates natural language mood descriptions into a 12-mood taxonomy mapped to genre weights |
| **Vector Engine** | Sentence-Transformers + Qdrant | Dense embedding similarity search for semantic understanding of movie descriptions |
| **Visual Engine** | CLIP ViT-B/32 (FastEmbed) | Poster-based visual similarity search using OpenAI's CLIP model |
| **Serendipity Engine** | Inverse popularity + novelty scoring | Injects unexpected but high-quality recommendations to break filter bubbles |
| **Session Transformer** | 2-layer Transformer encoder (4 heads, 128-dim) | Next-item prediction from browsing session history (MAX_SEQ_LEN=50) |
| **NEBULA Visual DNA** | Cinematographic feature extraction | Extracts color palettes, shot types, motion, and composition from trailers into a visual DNA latent space |
| **Ranking Pipeline** | Multi-stage L0-L3 pipeline | L0: parallel candidate generation, L1: merge/dedup, L2: CTR + diversity + serendipity scoring, L3: post-processing |
| **Reranker** | Cohere API / FlashRank fallback | Gold-standard Cohere cross-encoder with automatic local FlashRank (ms-marco-TinyBERT) fallback |

### How They Work Together

```
User Request
     |
     v
+----+----+----+----+----+----+
| Content | Collab | NCF | KG |  ... (all 10 engines)
+----+----+----+----+----+----+
     |         |       |    |
     +----+----+----+--+----+
          |
   Score Fusion (weighted ensemble)
          |
          v
   FlashRank Cross-Encoder Reranking
          |
          v
   Serendipity Injection
          |
          v
   Final Ranked Results + Explanations
```

The **ranking pipeline** (`ranking_pipeline.py`) fuses scores from all engines using configurable weights. The **reranker** (`reranker.py`) applies a cross-encoder model (ms-marco-TinyBERT-L-2-v2) to re-score the top candidates for maximum relevance. Finally, the **serendipity engine** injects novel picks that score high on quality but low on predictability.

---

## Frontend Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Home | Hero banner with trending, action, and latest movie carousels |
| `/search` | Search | Full-text search with genre, director, actor, year, and rating filters |
| `/movie/[id]` | Movie Detail | Full movie info, cast, similar recommendations, trailer (react-player) |
| `/agentic` | AI Concierge | Chat with an LLM agent that gives personalized movie recommendations |
| `/mood` | Mood Discovery | Select or describe your mood, get emotion-matched recommendations |
| `/connections` | Movie Connections | Interactive force-directed graph showing how movies connect through shared entities |
| `/time-machine` | Time Machine | Browse cinema history by decade with period-specific recommendations |
| `/taste` | Taste Fingerprint | Radar chart visualization of your preference profile |
| `/director/[name]` | Director Page | Filmography and related directors |
| `/onboarding` | Onboarding | New user preference selection to cold-start recommendations |
| `/my-list` | My List | Personal watchlist and favorites |
| `/login` | Auth | NextAuth v5 authentication flow |

---

## API Reference

### Movies

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/movies/search?q=&genre=&director=&actor=&min_rating=&max_rating=&year_from=&year_to=&sort_by=&sort_order=&page=&per_page=` | Advanced movie search with filtering and pagination |
| `GET` | `/movies/{movie_id}` | Get full movie details by ID |
| `GET` | `/movies/genre/{genre}` | Browse movies by genre |
| `GET` | `/movies/find?title=` | Find a movie by exact title match |
| `GET` | `/genres` | List all genres with counts and average ratings |
| `GET` | `/trending` | Trending movies (by popularity score) |
| `GET` | `/latest` | Recently released movies |

### Recommendations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/recommendations/similar/{movie_id}` | Content-based similar movies |
| `POST` | `/recommendations/discover` | Advanced hybrid discovery with mood, diversity, and content weight controls |
| `GET` | `/search/semantic?q=` | Semantic vector search using sentence-transformers |

### Knowledge Graph

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/movies/graph/related/{title}` | Find entities related to a movie in the knowledge graph |
| `GET` | `/movies/graph/path?movie1=&movie2=` | Find connection paths between two movies |

### AI Agent

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/agent/chat` | Conversational recommendation agent (LangGraph + GROQ) |
| `POST` | `/api/v1/discovery/agentic` | GraphRAG-powered agentic discovery |
| `GET` | `/agent/conversations/{user_id}` | Retrieve conversation history |

### Sessions & User Insights

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/sessions/track` | Log user interaction events for session intelligence |
| `GET` | `/api/v1/recommendations/session/{session_id}` | Session-aware recommendations via Transformer encoder |
| `GET` | `/api/v1/users/{user_id}/taste-profile` | Computed taste fingerprint (genre affinity, decade patterns, director loyalty) |
| `POST` | `/api/v1/recommendations/mood` | Mood-to-genre recommendation mapping |
| `POST` | `/api/v1/playlists/mood` | Emotional arc playlist generation |

### Visual DNA

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/movies/{movie_id}/visual-dna` | NEBULA cinematographic feature breakdown |
| `GET` | `/api/v1/recommendations/visual-similar/{movie_id}` | Movies with similar visual DNA |
| `POST` | `/movies/visual/search` | CLIP-based visual similarity search |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check with SLO metrics (error rate, p95 latency) |
| `GET` | `/docs` | Interactive Swagger UI |
| `GET` | `/redoc` | ReDoc API documentation |

<details>
<summary><strong>Example: Search for Inception</strong></summary>

```bash
curl -s "http://localhost:8001/movies/search?q=inception&per_page=1" | python3 -m json.tool
```

```json
{
  "items": [
    {
      "title": "Inception",
      "genres": "Action Thriller Science Fiction Mystery Adventure",
      "director": "Christopher Nolan",
      "cast": "Leonardo DiCaprio Joseph Gordon-Levitt Ellen Page Tom Hardy",
      "vote_average": 8.1,
      "vote_count": 13752,
      "overview": "Cobb, a skilled thief who commits corporate espionage by infiltrating the subconscious...",
      "poster_path": "/xlaY2zyzMfkhk0HSC5VUwzoZPU1.jpg"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 1,
  "total_pages": 1
}
```

</details>

<details>
<summary><strong>Example: Get Similar Movies</strong></summary>

```bash
curl -s "http://localhost:8001/recommendations/similar/27205?limit=3" | python3 -m json.tool
```

```json
{
  "movie": "Inception",
  "recommendations": [
    { "title": "Interstellar", "content_score": 42.3 },
    { "title": "The Prestige", "content_score": 38.1 },
    { "title": "Shutter Island", "content_score": 35.7 }
  ]
}
```

</details>

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (v20+) and Docker Compose v2

### One Command

```bash
make docker
```

This runs the [`start.sh`](start.sh) script which:

1. Creates `.env` from `.env.example` if missing
2. Builds and starts all 5 services (API, Frontend, SurrealDB, Redis, Qdrant)
3. Waits for the API to report `ready=true` (database initialized, engine trained)
4. Waits for the frontend to be reachable
5. Prints access URLs

Once ready:

| Service | URL |
|---------|-----|
| **Frontend** | [http://localhost:3002](http://localhost:3002) |
| **API Docs** | [http://localhost:8001/docs](http://localhost:8001/docs) |
| **Health** | [http://localhost:8001/health](http://localhost:8001/health) |

### Watch Mode (Hot Reload)

For development with live code syncing:

```bash
make watch
```

File changes in `backend/` and `frontend/` sync into the running containers automatically.

---

## Local Development

For running without Docker (useful for debugging):

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [bun](https://bun.sh/) (JavaScript runtime)
- Python 3.12+

### Setup

```bash
# Copy environment config
cp .env.example .env

# Start backend + frontend with auto-seeding
make dev
```

This installs Python/JS dependencies, seeds the SQLite database with ~7,880 movies and sample users/ratings, and starts both servers:

- Backend: `http://localhost:8001` (uvicorn with hot reload)
- Frontend: `http://localhost:3002` (Next.js Turbopack)

### Individual Services

```bash
make run            # Backend only
make frontend-dev   # Frontend only
```

---

## Configuration

All configuration is managed through environment variables (`.env` file), validated by Pydantic Settings.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///data/movies_recommender.db` | Database connection string |
| `REDIS_URL` | `redis://localhost:6379` | Redis cache connection |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant vector database |
| `GROQ_API_KEY` | -- | Required for AI agent (LangGraph chat) |
| `GEMINI_API_KEY` | -- | Required for mood engine (emotion parsing) |
| `TMDB_API_KEY` | -- | Required for large-scale data ingestion |
| `AUTO_INIT_DB` | `false` | Auto-create tables and seed on startup |
| `USE_MOCK_DATA` | `false` | Seed sample users and ratings |
| `ENABLE_STARTUP_WARMUP` | `true` | Pre-train engines on startup |
| `CORS_ALLOW_ORIGINS` | `http://localhost:3002` | Comma-separated allowed origins |

---

## Data Pipeline

### Included Data

The repository ships with `data/movies.csv` containing **7,880 movies** from TMDB. On first startup with `AUTO_INIT_DB=true`, the API:

1. Creates the database schema (movies, users, ratings, watch_history, favorites)
2. Imports all movies from CSV
3. Generates 100 sample users with realistic rating distributions
4. Trains all recommendation engines in the background (~30 seconds)

### Large-Scale Ingestion (1.2M+ Records)

For production-scale testing with the full IMDb dataset:

```bash
make deploy-1m
```

This runs the IMDb ingestion pipeline which:
- Fetches movie metadata from TMDB API (rate-limited at 40 req/sec)
- Imports poster images and metadata
- Builds vector embeddings for semantic search
- Requires a valid `TMDB_API_KEY` in `.env`

---

## Tech Stack

### Backend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API Framework | FastAPI 0.115+ | Async API with auto-docs, dependency injection |
| ORM | SQLModel + SQLAlchemy 2.0 | Type-safe database access |
| ML Framework | PyTorch 2.6 | Neural recommendation models (NCF, Two-Tower, LightGCN) |
| NLP | sentence-transformers 3.4 | Dense text embeddings for semantic search |
| Vision | FastEmbed (CLIP ViT-B/32) | Poster visual similarity |
| Reranking | FlashRank (ms-marco-TinyBERT-L-2) | Cross-encoder reranking |
| Graph | NetworkX + python-louvain | Knowledge graph with community detection |
| LLM Agent | LangGraph + GROQ | Conversational recommendation agent |
| LLM (Mood) | Google Gemini (google-genai) | Natural language mood parsing |
| Gradient Boosting | XGBoost | Ranking model training |

### Frontend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | Next.js 16.2 (App Router) | Server-rendered React with Turbopack |
| UI | React 19 + Tailwind CSS 4 | Component-driven UI with utility classes |
| Auth | NextAuth v5 (beta.30) | Session-based authentication |
| Animation | Framer Motion 12 | Cinematic page transitions and micro-interactions |
| Charts | Recharts 3 | Taste fingerprint radar charts |
| Graphs | react-force-graph-2d | Interactive knowledge graph visualization |
| Video | react-player | Embedded movie trailers |

### Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Containers | Docker Compose | 5-service orchestration |
| Vector DB | Qdrant 1.13 | ANN search for embeddings |
| Cache | Redis 7.4 (alpine) | L2 cache with LRU eviction (256MB) |
| Graph DB | SurrealDB 2.2 | Heterogeneous graph storage |
| DB | SQLite (dev) / PostgreSQL (prod) | Primary relational storage |

---

## Testing

### Backend

```bash
uv run python -m pytest                    # Run all tests
uv run python -m pytest -m unit            # Unit tests only
uv run python -m pytest -m integration     # Integration tests only
uv run ruff check                          # Linting
uv run ruff format --check                 # Format check
```

### Frontend

```bash
cd frontend
bun run lint       # ESLint
bun run build      # Type check + build
```

---

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py                          # FastAPI app with lifespan, middleware, security
│   │   ├── routers/                         # Modular API routes
│   │   │   ├── health.py                    # Health + SLO metrics
│   │   │   ├── movies.py                    # Movie CRUD + browsing
│   │   │   ├── search.py                    # Full-text + semantic search
│   │   │   ├── recommendations.py           # Hybrid recommendations
│   │   │   ├── graph.py                     # Knowledge graph queries
│   │   │   ├── agent.py                     # AI chat + agentic discovery
│   │   │   └── users.py                     # Auth + user management
│   │   ├── schemas.py                       # Pydantic v2 models
│   │   └── dependencies.py                  # FastAPI dependency injection
│   ├── services/
│   │   └── recommendation_engine_service/
│   │       ├── engines/
│   │       │   ├── recommendation.py        # Main engine (content + collab + hybrid)
│   │       │   ├── ncf.py                   # Neural Collaborative Filtering
│   │       │   ├── two_tower.py             # Two-Tower candidate generation
│   │       │   ├── lightgcn.py              # LightGCN graph collaborative filtering
│   │       │   ├── knowledge_graph.py       # NetworkX knowledge graph
│   │       │   ├── vector_engine.py         # Qdrant semantic search
│   │       │   ├── visual_engine.py         # CLIP visual search
│   │       │   ├── mood_engine.py           # Gemini-powered mood analysis
│   │       │   ├── serendipity.py           # Novelty injection
│   │       │   ├── ranking_pipeline.py      # Score fusion orchestrator
│   │       │   ├── reranker.py              # FlashRank cross-encoder
│   │       │   ├── explainability.py        # Recommendation explanations
│   │       │   ├── session_engine.py        # Transformer-based session continuation
│   │       │   └── nebula/                  # NEBULA Visual DNA pipeline (color, composition, motion)
│   │       └── agents/
│   │           ├── concierge.py             # LangGraph conversational agent
│   │           └── memory.py                # Conversation memory
│   ├── cache.py                             # L1 (in-process) + L2 (Redis) cache
│   ├── config.py                            # Pydantic Settings configuration
│   └── database.py                          # SQLModel engine, schema, seeding
├── frontend/
│   ├── app/                                 # Next.js App Router pages
│   │   ├── page.tsx                         # Home (trending + genre carousels)
│   │   ├── search/page.tsx                  # Advanced search
│   │   ├── movie/[id]/page.tsx              # Movie detail
│   │   ├── agentic/page.tsx                 # AI concierge chat
│   │   ├── mood/page.tsx                    # Mood-based discovery
│   │   ├── connections/page.tsx             # Knowledge graph visualization
│   │   ├── time-machine/page.tsx            # Decade browsing
│   │   ├── taste/page.tsx                   # Taste fingerprint radar chart
│   │   ├── director/[name]/page.tsx         # Director filmography
│   │   ├── onboarding/page.tsx              # New user preference setup
│   │   └── my-list/page.tsx                 # Personal watchlist
│   ├── components/                          # Shared React components
│   ├── server-api.ts                        # Server-side API client
│   └── api.ts                               # Client-side API client
├── data/
│   ├── movies.csv                           # 7,880 movie dataset (ships with repo)
│   └── movies_recommender.db                # SQLite database (auto-created)
├── docker-compose.yml                       # 5-service stack definition
├── Makefile                                 # Build commands
├── start.sh                                 # Startup orchestration script
└── pyproject.toml                           # Python dependencies (uv)
```

---

## Operations

### Monitoring

The `/health` endpoint returns real-time SLO metrics:

```json
{
  "status": "healthy",
  "ready": true,
  "movies_loaded": 7880,
  "engine_trained": true,
  "slo": {
    "total_requests": 1523,
    "total_errors": 2,
    "error_rate": 0.001,
    "avg_latency_ms": 45.2,
    "p95_latency_ms": 180.3
  }
}
```

### Database Migrations

```bash
uv run python -m alembic -c alembic.ini upgrade head
```

### Runbooks

| Document | Purpose |
|----------|---------|
| `docs/runbooks/incident-response.md` | Production incident playbook |
| `docs/runbooks/oncall-handoff.md` | Shift handoff checklist |
| `docs/runbooks/db-migration-rollback.md` | Migration rollback procedures |
| `docs/operations/production-readiness-checklist.md` | Pre-deploy verification |

---

## License

This project is for educational and portfolio purposes.
