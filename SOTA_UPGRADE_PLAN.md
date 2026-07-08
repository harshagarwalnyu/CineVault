# SOTA Movie Recommender Upgrade Plan

## Context

The Movies-Recommender project has a solid foundation — hybrid TF-IDF/SVD recommendation engine, Qdrant vector search, NetworkX knowledge graph, CLIP visual search, LangGraph agent, and a premium Next.js 16 frontend. However, the recommendation engine relies on synthetic ratings (~100 fake users), the collaborative filtering is basic SVD with no real user data, the NEBULA video DNA system produces mock data, and several SOTA techniques from 2025-2026 are missing: LLM-powered explainability, mood/emotion-based recommendations, session-based modeling, GNN collaborative filtering, and proper two-tower candidate generation.

**Goal**: Transform this into a genuinely useful, SOTA recommendation system by (1) ingesting real-world MovieLens 32M data for proper collaborative filtering, (2) upgrading to a multi-stage ranking pipeline with neural models, (3) making the LLM agent truly conversational with RAG and memory, and (4) adding novel features like mood playlists, taste fingerprints, and cinematographic DNA.

---

## Phase 0: Backend Structural Refactor (M)

**Why**: `main.py` is 810 lines with all endpoints inline. `recommendation.py` is 1445 lines. Both must be modular before adding ~15 new endpoints and ~8 new engines.

### Files to Create
| File | Purpose |
|---|---|
| `backend/app/routers/__init__.py` | Router package |
| `backend/app/routers/health.py` | `/health`, `/admin/*` endpoints |
| `backend/app/routers/movies.py` | `/movies/*`, `/genres`, `/trending`, `/latest` |
| `backend/app/routers/recommendations.py` | `/recommendations/*` |
| `backend/app/routers/search.py` | `/movies/semantic-search`, `/movies/visual/*` |
| `backend/app/routers/users.py` | `/users/login`, ratings, favorites |
| `backend/app/routers/agent.py` | `/agent/chat`, `/api/v1/discovery/agentic` |
| `backend/app/routers/graph.py` | `/movies/graph/*` |
| `backend/app/dependencies.py` | Shared deps: `get_rec_engine`, `get_db_session` |

### Files to Modify
- **`backend/app/main.py`** -> Slim to ~80 lines: app creation, middleware, router includes, lifespan
- **`backend/services/recommendation_engine_service/engines/recommendation.py`** -> Extract `RedisRecommendationCache` to `cache.py`, scoring helpers to `scoring.py`

### Verification
- All existing tests pass (`uv run python -m pytest backend/tests/`)
- Every existing endpoint returns identical responses (smoke test)

---

## Phase 1: MovieLens 32M Dataset Integration (XL)

**Why**: The system has ~44K movies but zero real collaborative filtering signal. MovieLens 32M provides 32M real ratings from 200K+ users across 87K movies — the gold standard benchmark for recommendation systems.

### 1.1 Database Schema (Alembic migration)

New migration: `alembic/versions/20260405_0002_movielens_expansion.py`

```sql
-- MovieLens ratings (32M rows)
CREATE TABLE ml_ratings (
    id BIGINT PRIMARY KEY,
    ml_user_id INTEGER NOT NULL,
    movie_id INTEGER REFERENCES movies(id),
    rating REAL NOT NULL,          -- 0.5-5.0 scale
    timestamp BIGINT
);
-- Indices: (ml_user_id), (movie_id), (ml_user_id, movie_id)

-- MovieLens <-> internal ID mapping
CREATE TABLE movie_id_mapping (
    id INTEGER PRIMARY KEY,
    ml_movie_id INTEGER UNIQUE NOT NULL,
    tmdb_id INTEGER,
    imdb_id TEXT,
    internal_movie_id INTEGER REFERENCES movies(id)
);

-- User-generated tags (1M+ rows)
CREATE TABLE ml_tags (
    id BIGINT PRIMARY KEY,
    ml_user_id INTEGER NOT NULL,
    movie_id INTEGER REFERENCES movies(id),
    tag TEXT NOT NULL,
    timestamp BIGINT
);

-- Extended movie metadata
ALTER TABLE movies ADD COLUMN metacritic_score INTEGER;
ALTER TABLE movies ADD COLUMN box_office_worldwide BIGINT;
ALTER TABLE movies ADD COLUMN awards_text TEXT;
ALTER TABLE movies ADD COLUMN trailer_youtube_key TEXT;
ALTER TABLE movies ADD COLUMN streaming_providers TEXT;  -- JSON
ALTER TABLE movies ADD COLUMN certification TEXT;
```

### 1.2 New Files

| File | Purpose |
|---|---|
| `backend/scripts/ingest_movielens.py` | Download ML-32M, parse CSVs, map IDs via `links.csv`, batch-insert ratings/tags |
| `backend/scripts/enrich_metadata.py` | Fetch trailers, streaming providers, certifications from TMDB API per movie |
| `backend/scripts/validate_movielens.py` | Count validation: ratings imported, movies matched, distribution check |

### 1.3 Files to Modify
- **`backend/models.py`** -> Add `MLRating`, `MovieIdMapping`, `MLTag` SQLModel classes; add new columns to `Movie`
- **`backend/config.py`** -> Add `MOVIELENS_DATA_PATH`, `MOVIELENS_BATCH_SIZE`, `TMDB_RATE_LIMIT_PER_SEC`
- **`backend/services/.../engines/recommendation.py`** -> `_load_ratings()` loads from `ml_ratings` + normalizes 0.5-5.0 to 0-10 scale

### 1.4 Data Pipeline
1. `python -m backend.scripts.ingest_movielens` — downloads ML-32M zip, parses `links.csv` -> `movie_id_mapping`, matches by tmdb_id/imdb_id, inserts `ml_ratings` (batch 50K), inserts `ml_tags`
2. For unmatched ML movies with tmdb_id: fetch from TMDB API and insert into `movies`
3. `python -m backend.scripts.enrich_metadata` — for each movie with tmdb_id, fetch videos (trailer), watch/providers (streaming), release_dates (certification)

### Verification
- `validate_movielens.py` reports: "Matched X of 87,585 ML movies. 32M ratings imported."
- Recommendation engine trains successfully on expanded dataset
- Collaborative filtering returns differentiated scores (not flat defaults)

---

## Phase 2: SOTA Recommendation Engine (XL)

**Why**: Replace basic SVD with a proper multi-stage neural ranking pipeline. The SOTA pattern (Two-Tower -> L1 -> L2 -> Post-processing) is the production standard at Netflix, YouTube, and Spotify as of 2026.

### 2.1 Two-Tower Model (replaces SVD for candidate generation)

New file: `backend/services/recommendation_engine_service/engines/two_tower.py`

- **User Tower**: `Embedding(user_id, 128) + MLP([256, 128]) -> 128-dim`
- **Item Tower**: `Embedding(movie_id, 128) + MLP(genre_onehot + decade + language + vote_avg + runtime -> [256, 128]) -> 128-dim`
- **Training**: Sampled softmax loss on ML-32M. Positive = rated >= 3.5, negative = random unrated
- **Serving**: Pre-compute all item embeddings -> Qdrant collection `movie_twotower` (128-dim, cosine). At query time: compute user embedding -> ANN search top-200

New training script: `backend/scripts/train_two_tower.py`

### 2.2 LightGCN (graph-based collaborative filtering)

New file: `backend/services/recommendation_engine_service/engines/lightgcn.py`

- Bipartite user-item graph from ML-32M ratings (200K users x 87K items, ~32M edges)
- 3-layer LightGCN, 64-dim embeddings, sum aggregation (no feature transform per paper)
- BPR loss training
- Pre-compute embeddings for L2 scoring

New training script: `backend/scripts/train_lightgcn.py`
New dependency: `torch-geometric>=2.5.0`

### 2.3 Session-Based Transformer

New file: `backend/services/recommendation_engine_service/engines/session_engine.py`

- Input: last N movie IDs from current session
- 2-layer Transformer encoder (4 heads, 128-dim) over movie embedding sequence
- Predicts next-item embedding -> ANN search for candidates
- Fallback to user history if session is empty

New migration: `alembic/versions/20260405_0003_sessions_and_agent.py`
```sql
CREATE TABLE user_sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    movie_interactions TEXT,  -- JSON: [{movie_id, action, timestamp}]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

New endpoints:
- `POST /api/v1/sessions/track` — record interaction
- `GET /api/v1/recommendations/session/{session_id}` — session-based recs

### 2.4 Mood/Emotion Engine

New file: `backend/services/recommendation_engine_service/engines/mood_engine.py`

- Parse natural language text via Gemini API (already configured) -> structured output: `{primary_mood, secondary_mood, energy_level, valence}`
- 12-mood taxonomy mapped to genre affinity vectors:
  - happy -> Comedy +0.4, Romance +0.2, Animation +0.2
  - melancholic -> Drama +0.4, Art House +0.3
  - tense -> Thriller +0.4, Horror +0.2, Mystery +0.2
  - adventurous -> Adventure +0.4, Sci-Fi +0.3
  - nostalgic -> Drama +0.3, Romance +0.2
  - angry -> Action +0.4, Crime +0.3
  - romantic -> Romance +0.5, Drama +0.2
  - intellectual -> Documentary +0.3, Mystery +0.3
  - cozy -> Comedy +0.3, Family +0.3
  - dark -> Horror +0.3, Thriller +0.3
  - inspired -> Biography +0.3, Sports +0.3
  - whimsical -> Fantasy +0.3, Animation +0.3
- Mood weights become scoring multipliers in the ranking pipeline

New endpoint: `POST /api/v1/recommendations/mood`

### 2.5 Serendipity Injection

New file: `backend/services/recommendation_engine_service/engines/serendipity.py`

- `novelty_score` = 1 - log(popularity_rank) / log(max_rank)
- `unexpectedness_score` = 1 - max_similarity(candidate, user's rated movies)
- `serendipity_score` = novelty * 0.4 + unexpectedness * 0.4 + quality * 0.2
- Replace bottom 20% of ranked list with top serendipity picks (min quality threshold: 6.5)
- Configurable via `serendipity_factor` parameter (0-1)

### 2.6 Multi-Stage Ranking Pipeline

New file: `backend/services/recommendation_engine_service/engines/ranking_pipeline.py`

Orchestrates the full pipeline replacing the monolithic `discover_movies`:

```
L0 Candidate Generation (parallel):
  - Two-Tower ANN: top 200
  - Content TF-IDF: top 100
  - Session Transformer: top 50
  - LightGCN: top 100
  - Mood-filtered: (if mood provided)

L1 Merge & Deduplicate (~300-400 unique)

L2 Feature Scoring (per candidate):
  - two_tower_score, lightgcn_score, content_score
  - semantic_score (Qdrant BGE-M3), session_score
  - quality_score, popularity_score, mood_affinity
  - collaborative_score (SVD fallback)
  Final = hand-tuned weights dot feature_vector
  (Later: train XGBoost/LightGBM ranker on click data)

L3 Post-Processing:
  - Diversity (MMR, existing)
  - Serendipity injection
  - Business rules (boost new releases)
  - Explanation generation
```

### 2.7 Explainability Engine

New file: `backend/services/recommendation_engine_service/engines/explainability.py`

- For each recommendation, identify dominant signal(s) from L2 scoring
- Template + LLM polish via Gemini:
  - "Because you loved [movie] — shares its [narrative structure / visual style / director]"
  - "Users with your taste profile rate this 4.2/5"
  - "Matches your [mood] mood with its [genre/setting]"
  - "Hidden gem: only 2,300 ratings but 8.1 average from cinephiles like you"

### 2.8 New Dependencies
```
torch-geometric>=2.5.0
xgboost>=2.1.0  # for learned ranking later
```

### Verification
- Unit test each engine independently with synthetic data
- Integration test: `test_ranking_pipeline.py` end-to-end with ML data
- Latency benchmark: full L0->L3 < 500ms for top-10
- Compare recommendation quality: SVD-only vs full pipeline on held-out ML-32M test set

---

## Phase 3: LLM Agent Upgrade (L)

**Why**: The current agent has 3 tools (semantic search, metadata filter, trending). Users need a full conversational recommender with RAG, memory, mood detection, and comparison capabilities.

### 3.1 RAG Layer

New file: `backend/services/recommendation_engine_service/agents/rag.py`

- On each user query, retrieve top-10 relevant movies from Qdrant BGE-M3 index
- Construct prompt: system message + retrieved context + conversation history + user query
- Use existing `get_vector_engine()` — no new infrastructure needed

### 3.2 Enhanced Tool Set

Modify: `backend/services/recommendation_engine_service/agents/concierge.py`

Add new tools (reuse existing engine methods):
| Tool | Backed By |
|---|---|
| `get_movie_details(title_or_id)` | `recommendation.py` -> `_search_by_title` |
| `get_recommendations_for_movie(title)` | `recommendation.py` -> `get_similar_movies` |
| `compare_movies(movie1, movie2)` | New: side-by-side stats from DB |
| `detect_mood_and_recommend(text)` | `mood_engine.py` -> `analyze_and_recommend` |
| `get_user_taste_profile(user_id)` | New: computed from ratings/history |
| `find_movie_connections(movie1, movie2)` | `knowledge_graph.py` -> `find_path` |
| `create_mood_playlist(mood, duration)` | New: sequenced mood-arc recs |

### 3.3 Conversation Memory

New table in migration `20260405_0003_sessions_and_agent.py`:
```sql
CREATE TABLE agent_conversations (
    id TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    messages TEXT,               -- JSON [{role, content, timestamp}]
    extracted_preferences TEXT,  -- JSON {liked_genres, disliked, mood_history, mentioned_movies}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

New file: `backend/services/recommendation_engine_service/agents/memory.py`
- After each turn, LLM extracts preference signals ("hates horror", "loves Nolan")
- Persisted in `agent_conversations` table
- Loaded on session resume for returning users

### 3.4 API Changes
- Modify `POST /agent/chat` schema to accept `session_id` and `user_id`
- New endpoint: `GET /agent/conversations/{user_id}`

### Verification
- Test each tool in isolation
- Test 5-turn conversation maintaining context
- Test memory persistence across sessions
- Test mood detection on 20 sample inputs

---

## Phase 4: Frontend Enhancement (XL)

**Why**: The UI needs to surface all new capabilities — mood selection, explanations, session awareness, onboarding for cold start, and richer movie details.

### 4.1 New Dependencies (via `bun add`)
```
recharts               # radar charts for taste fingerprint
react-player           # YouTube trailer embeds
react-force-graph-2d   # interactive knowledge graph visualization
```

### 4.2 New Components

| Component | Purpose |
|---|---|
| `components/MoodSelector.tsx` | 12-mood pill grid + free-text input. Calls `POST /api/v1/recommendations/mood` |
| `components/ExplanationCard.tsx` | "Because you watched X" — reason text, score breakdown, signal badges |
| `components/TasteFingerprint.tsx` | Recharts radar chart: genres, decades, moods, directors |
| `components/MovieConnections.tsx` | react-force-graph-2d: interactive actor/director/genre graph |
| `components/OnboardingFlow.tsx` | Rate 10 movies to bootstrap preferences (cold start solution) |
| `components/SessionRail.tsx` | "Continue Your Vibe" rail from session-based recs |
| `components/TrailerEmbed.tsx` | react-player YouTube embed from `trailer_youtube_key` |
| `components/MoodPlaylist.tsx` | Evening/weekend movie sequence with emotional arc |
| `components/DirectorJourney.tsx` | Timeline of filmmaker's career with rating trends |
| `components/TimeMachine.tsx` | Decade selector with era-specific recommendations |
| `components/WatchTimeline.tsx` | Visual timeline of user's watch history |

### 4.3 New Pages

| Route | Purpose |
|---|---|
| `app/onboarding/page.tsx` | Cold start flow — redirect here if user has < 10 ratings |
| `app/taste/page.tsx` | Taste Fingerprint dashboard |
| `app/connections/page.tsx` | Movie Connections interactive graph |
| `app/mood/page.tsx` | Full mood-based discovery page |
| `app/director/[name]/page.tsx` | Director's Journey |
| `app/time-machine/page.tsx` | Era-based recommendations |

### 4.4 Enhance Existing Pages

**Home** (`components/HomeExperience.tsx`):
- Add `<MoodSelector />` above search bar
- Add `<SessionRail />` if session history exists
- Wrap recommendation items with `<ExplanationCard />`
- Add "Serendipity Picks" rail

**Movie Detail** (`app/movie/[id]/page.tsx`):
- Add `<TrailerEmbed />` if trailer exists
- Add box office, awards, streaming badges, Metacritic score
- Replace flat "Related" with `<MovieConnections />` graph

**Search** (`app/search/page.tsx`):
- Add "Mood" as 4th search mode
- Show `<MoodSelector />` when mood mode active

**My List** (`app/my-list/page.tsx`):
- Add `<TasteFingerprint />` sidebar
- Add `<WatchTimeline />`

### 4.5 API Client Updates (`frontend/api.ts`)
```typescript
getMoodRecommendations(text: string, userId?: number): Promise<Movie[]>
getSessionRecommendations(sessionId: string): Promise<Movie[]>
trackSessionInteraction(sessionId: string, movieId: number, action: string): Promise<void>
getUserTasteProfile(userId: number): Promise<TasteProfile>
getMovieConnections(movieId: number): Promise<GraphData>
getDirectorFilmography(name: string): Promise<Movie[]>
getMoviesByDecade(decade: string, limit: number): Promise<Movie[]>
submitOnboardingRatings(userId: number, ratings: Rating[]): Promise<void>
```

### 4.6 Session Tracking
- Generate session ID in localStorage on first visit
- Track clicks on `MovieCard` and page views on movie detail
- `POST /api/v1/sessions/track` on each interaction

### Verification
- All new components render without errors
- E2E: onboarding flow -> rate 10 movies -> personalized recs appear
- E2E: mood selection -> mood-based recommendations returned
- Mobile responsive check on all new components
- Playwright tests for critical flows

---

## Phase 5: Novel Differentiating Features (L)

**Why**: These features don't exist in any public movie recommender. They're the unique selling points.

### 5.1 Cinematographic DNA (Activate NEBULA)

The existing NEBULA pipeline (`engines/nebula/`) has a working encoder but produces mock data.

Modify: `engines/nebula/feature_extractor.py`
- Use `yt-dlp` to download trailers via `trailer_youtube_key` (from Phase 1 enrichment)
- Extract real color histograms (OpenCV), shot boundaries (scene detect), motion complexity (optical flow)
- Process through existing `CinematographicDNAEncoder` -> 128-dim vector

Modify: `engines/nebula/pipeline.py`
- Store DNA vectors in Qdrant collection `nebula_dna_manifold`
- Process top 5,000 movies with trailers

New endpoints:
- `GET /api/v1/movies/{movie_id}/visual-dna` — DNA breakdown + similar-by-DNA
- `GET /api/v1/recommendations/visual-similar/{movie_id}` — cinematographic siblings

New dependency: `yt-dlp>=2024.1.0`

### 5.2 Taste Fingerprint

New endpoint: `GET /api/v1/users/{user_id}/taste-profile`

Computed from user's ratings + watch history + favorites:
```json
{
  "genres": [{"name": "Sci-Fi", "affinity": 0.92}],
  "decades": [{"decade": "2010s", "count": 45}],
  "moods": [{"mood": "intellectual", "affinity": 0.85}],
  "pacing_preference": 0.65,
  "directors": [{"name": "Nolan", "movies_rated": 7, "avg_rating": 8.9}],
  "novelty_appetite": 0.45
}
```

### 5.3 Mood Playlist Generator

New endpoint: `POST /api/v1/playlists/mood`
```json
{"duration": "evening", "starting_mood": "relaxed", "ending_mood": "inspired", "user_id": 42}
```
- Define emotional arc: relaxed -> engaged -> tense -> catharsis -> inspired
- Select movies matching each arc position AND user preferences
- Generate connecting narrative via Gemini

### 5.4 Time Machine

New endpoint: `GET /api/v1/recommendations/era/{decade}`
- Filter movies by decade + apply quality/popularity ranking
- Gemini generates era context: "The 1970s was the era of New Hollywood..."

### 5.5 Director's Journey

New endpoint: `GET /api/v1/directors/{name}/journey`
- All movies by director, chronological
- Rating trajectory, genre evolution, thematic shifts

### Verification
- NEBULA: extract features from 1 real trailer (integration test)
- Taste Fingerprint: verify computation on known user ratings
- Mood Playlist: verify arc produces correctly sequenced moods

---

## Phase 6: Infrastructure Hardening (M)

### 6.1 Docker Compose Pin Versions
```yaml
surrealdb:
  image: surrealdb/surrealdb:v2.2.1   # was :latest
redis:
  image: redis:7.4-alpine              # was :alpine
# Add Qdrant to compose (currently external)
qdrant:
  image: qdrant/qdrant:v1.12.1
  ports: ["6333:6333"]
  volumes: [qdrant_data:/qdrant/storage]
```

### 6.2 Model Serving
New file: `backend/services/model_server.py`
- Load PyTorch models (Two-Tower, LightGCN, Session) on app startup
- In-process inference (no separate serving container at this scale)
- Version tracking + hot-reload on file change

### 6.3 Background Training
New file: `backend/scripts/retrain_models.py`
- Incremental retraining on new ratings data
- Atomic model weight swap

### 6.4 Monitoring
- Add structured logging for: rec latency by stage, cache hit rate, model inference time
- Add Prometheus metrics endpoint

### Verification
- Docker compose builds and starts all services
- Models load on startup without error
- Health endpoint reports all services healthy

---

## Phase Dependency Graph

```
Phase 0 (Refactor) ──> All subsequent phases
         |
Phase 1 (MovieLens) ──> Phase 2 (needs real ratings data)
         |
Phase 2 (Engine) ──> Phase 3 (agent needs mood/pipeline tools)
    |         |
    |    Phase 4 (Frontend, can overlap with Phase 3)
    |
Phase 5 (Novel Features) ──> needs Phase 1 (trailers) + Phase 2 (engines) + Phase 4 (UI)
    |
Phase 6 (Infrastructure) ──> can run alongside Phase 4/5
```

---

## Critical Files Reference

| File | Lines | Role in Plan |
|---|---|---|
| `backend/app/main.py` | 810 | Split into routers (Phase 0) |
| `backend/services/.../engines/recommendation.py` | 1445 | Extract sub-engines, integrate ranking pipeline (Phase 0, 2) |
| `backend/models.py` | 158 | Add ML tables, movie metadata columns (Phase 1) |
| `backend/config.py` | 103 | Add new config params (Phase 1, 2) |
| `backend/database.py` | ~450 | Update data loading for ML ratings (Phase 1) |
| `backend/services/.../agents/concierge.py` | ~100 | Add 7 new tools, RAG, memory (Phase 3) |
| `backend/services/.../engines/ncf.py` | ~70 | Template exists, replaced by Two-Tower (Phase 2) |
| `backend/services/.../engines/nebula/` | ~300 | Activate with real data (Phase 5) |
| `frontend/components/HomeExperience.tsx` | ~600 | Add mood selector, session rail, explanations (Phase 4) |
| `frontend/app/movie/[id]/page.tsx` | ~200 | Add trailer, streaming, connections (Phase 4) |
| `frontend/api.ts` | ~150 | Add ~8 new API methods (Phase 4) |

## Existing Code to Reuse
- `RedisRecommendationCache` in `recommendation.py:40-82` — reuse for all new engines
- `get_vector_engine()` in `vector_engine.py` — reuse for RAG retrieval
- `get_knowledge_graph()` in `knowledge_graph.py` — reuse for connections/paths
- `NCF` in `ncf.py` — partial template for Two-Tower (embedding patterns)
- `CinematographicFeatureExtractor` in `nebula/feature_extractor.py` — activate, don't rewrite
- `CinematographicDNAEncoder` in `nebula/dna_encoder.py` — activate, don't rewrite
- `QdrantVectorEngine` in `vector_engine.py` — extend for Two-Tower collection
- Gemini client pattern in `graphrag.py` — reuse for mood analysis, explainability
- `_get_quality_score()`, `_get_popularity_score()` in `recommendation.py` — reuse in ranking pipeline
