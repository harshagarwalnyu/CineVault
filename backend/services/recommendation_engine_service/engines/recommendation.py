"""
Enhanced Recommendation Engine v3.0
====================================
Production-grade recommendation engine with:
- Improved hybrid scoring with tunable parameters
- Diversity-aware recommendations
- Session-based recommendations
- Personalized user recommendations
- Caching for performance
- Explanation generation
"""

import difflib
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import hashlib
import json

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity, linear_kernel
from sklearn.preprocessing import normalize
from scipy.sparse.linalg import svds
from scipy.sparse import csr_matrix
import redis
import logging
import threading
from sqlmodel import text

from backend.database import get_connection, engine as db_engine
from backend.utils import safe_float, safe_int, safe_str
from backend.config import settings

logger = logging.getLogger(__name__)

# ─── Known TMDB multi-word genres (longest first for greedy matching) ────
_TMDB_GENRES = [
    "Science Fiction", "TV Movie",  # multi-word — must match before single words
    "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary",
    "Drama", "Family", "Fantasy", "History", "Horror", "Music", "Mystery",
    "Romance", "Thriller", "War", "Western",
]

GENRE_SEPARATOR = "|"


def normalize_genres(raw: str) -> str:
    """Convert any genre format (JSON array, space-delimited, pipe-delimited) to pipe-delimited.

    Handles three input formats:
    1. JSON array: '["Action", "Science Fiction"]' → 'Action|Science Fiction'
    2. Pipe-delimited: 'Action|Science Fiction' → 'Action|Science Fiction' (passthrough)
    3. Space-delimited legacy: 'Action Science Fiction' → 'Action|Science Fiction'
       (greedy matching against known TMDB genre names)
    """
    if not raw or not raw.strip():
        return ""
    raw = raw.strip()

    # Format 1: JSON array string
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return GENRE_SEPARATOR.join(str(g).strip() for g in parsed if str(g).strip())
        except (json.JSONDecodeError, TypeError):
            pass  # Fall through to other formats

    # Format 2: Already pipe-delimited
    if GENRE_SEPARATOR in raw:
        return raw

    # Format 3: Space-delimited legacy — greedy match against known TMDB genres
    remaining = raw
    genres = []
    while remaining:
        remaining = remaining.strip()
        if not remaining:
            break
        matched = False
        for genre in _TMDB_GENRES:
            if remaining.lower().startswith(genre.lower()):
                genres.append(genre)
                remaining = remaining[len(genre):]
                matched = True
                break
        if not matched:
            # Unknown token — take the first word
            parts = remaining.split(None, 1)
            if parts:
                genres.append(parts[0])
                remaining = parts[1] if len(parts) > 1 else ""
            else:
                break
    return GENRE_SEPARATOR.join(genres)


def split_genres(genre_str: str) -> list[str]:
    """Split a genre string (pipe-delimited) into a list of genre names."""
    if not genre_str:
        return []
    return [g.strip() for g in genre_str.split(GENRE_SEPARATOR) if g.strip()]


class RedisRecommendationCache:
    """Redis-backed cache for recommendations (PERFORMANCE_PROTOCOL.md)."""

    def __init__(self, ttl_seconds: int = 300):
        try:
            self.client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            self.ttl = ttl_seconds
            self.is_active = True
        except Exception as e:
            logger.warning(f"Redis not available for caching: {e}")
            self.is_active = False

    @staticmethod
    def _generate_cache_key(*args, **kwargs) -> str:
        data = json.dumps((args, kwargs), sort_keys=True, default=str)
        return f"rec_cache:{hashlib.sha256(data.encode()).hexdigest()}"

    def get(self, key: str) -> Optional[Any]:
        if not self.is_active:
            return None
        try:
            cached = self.client.get(key)
            return json.loads(cached) if cached else None
        except Exception:
            return None

    def set(self, key: str, value: Any):
        if not self.is_active:
            return
        try:
            self.client.setex(key, self.ttl, json.dumps(value, default=str))
        except Exception:
            pass

    def clear(self):
        if not self.is_active:
            return
        try:
            keys = self.client.keys("rec_cache:*")
            if keys:
                self.client.delete(*keys)
        except Exception:
            pass


class EnhancedRecommendationEngine:
    """
    Production-grade recommendation engine with multiple strategies.
    """

    def __init__(self):
        self.movies_df: Optional[pd.DataFrame] = None
        self.ratings_df: Optional[pd.DataFrame] = None
        self.similarity_matrix: Optional[np.ndarray] = None
        self.content_matrix: Optional[csr_matrix] = None
        self.collab_predictions: Optional[pd.DataFrame] = None
        self.vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
        self.cache = RedisRecommendationCache(ttl_seconds=settings.REC_CACHE_TTL)
        self.is_trained = False
        self.genre_list_detailed: List[Dict] = []
        self.genre_list: List[str] = []
        self._movie_index_by_id: Dict[int, int] = {}
        self._normalized_titles: List[str] = []
        self._title_lookup: Dict[str, str] = {}

    def load_data(self) -> "EnhancedRecommendationEngine":
        """Load and preprocess data from database."""
        conn = get_connection()
        try:
            self._load_movies(conn)
            self._load_ratings(conn)
        finally:
            conn.close()
        return self

    @staticmethod
    def _repeat_text(series: pd.Series, times: int) -> pd.Series:
        cleaned = (
            series.astype(str)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
        )
        if times <= 1:
            return cleaned
        return cleaned.map(lambda value: " ".join([value] * times) if value else "")

    @staticmethod
    def _build_temporal_tokens(series: pd.Series) -> pd.Series:
        years = (
            series.astype(str)
            .str.extract(r"(?P<year>(?:19|20)\d{2})")["year"]
            .fillna("")
        )
        decades = years.map(
            lambda year: f"decade_{year[:3]}0" if isinstance(year, str) and year else ""
        )
        return years.map(
            lambda year: f"year_{year}" if isinstance(year, str) and year else ""
        ) + " " + decades

    def _load_movies(self, conn):
        """Fetch and preprocess movie data."""
        try:
            self.movies_df = pd.read_sql_query(
                'SELECT id, title, genres, keywords, tagline, "cast", director, '
                "vote_average, vote_count, poster_path, overview, release_date, runtime, original_language "
                "FROM movies",
                conn,
            )
        except Exception as e:
            logger.error(f"Error loading movies: {e}")
            self.movies_df = pd.DataFrame()

        if self.movies_df.empty:
            logger.warning("Movies table is empty. Running in degraded mode.")
            self.movies_df = pd.DataFrame(
                columns=[
                    "id",
                    "title",
                    "genres",
                    "keywords",
                    "tagline",
                    "cast",
                    "director",
                    "vote_average",
                    "vote_count",
                    "poster_path",
                    "overview",
                    "release_date",
                    "runtime",
                ]
            )
            self.movies_df["combined_features"] = ""
            return

        # Preprocess text and numeric columns
        text_cols = [
            "title",
            "genres",
            "keywords",
            "tagline",
            "cast",
            "director",
            "overview",
            "original_language",
            "release_date",
        ]
        self.movies_df[text_cols] = self.movies_df[text_cols].fillna("")

        # Normalize genres from space-delimited to pipe-delimited so multi-word
        # genres like "Science Fiction" are preserved as single tokens.
        self.movies_df["genres"] = self.movies_df["genres"].map(normalize_genres)

        for col in ["vote_average", "vote_count"]:
            self.movies_df[col] = pd.to_numeric(
                self.movies_df[col], errors="coerce"
            ).fillna(0)

        # Feature engineering: duplicate key metadata so TF-IDF captures title/genre
        # intent more strongly than long plot text.
        feature_parts = [
            self._repeat_text(self.movies_df["title"], 3),
            self._repeat_text(self.movies_df["genres"], 3),
            self._repeat_text(self.movies_df["keywords"], 2),
            self._repeat_text(self.movies_df["director"], 2),
            self._repeat_text(self.movies_df["cast"], 2),
            self._repeat_text(self.movies_df["tagline"], 1),
            self._repeat_text(self.movies_df["overview"], 1),
            self._repeat_text(self.movies_df["original_language"], 1),
            self._build_temporal_tokens(self.movies_df["release_date"]),
        ]
        combined_features = feature_parts[0]
        for part in feature_parts[1:]:
            combined_features = (combined_features + " " + part).str.strip()
        self.movies_df["combined_features"] = combined_features
        self.movies_df["title_normalized"] = self.movies_df["title"].astype(str).str.casefold()
        self.movies_df["genres_normalized"] = self.movies_df["genres"].astype(str).str.casefold()
        self.movies_df["director_normalized"] = self.movies_df["director"].astype(str).str.casefold()
        self.movies_df["cast_normalized"] = self.movies_df["cast"].astype(str).str.casefold()

        self._movie_index_by_id = {
            safe_int(movie_id): int(idx)
            for idx, movie_id in self.movies_df["id"].items()
        }
        self._normalized_titles = self.movies_df["title_normalized"].tolist()
        self._title_lookup = dict(
            zip(self._normalized_titles, self.movies_df["title"].astype(str).tolist())
        )

        # Extract and cache unique genres immediately (PERFORMANCE_PROTOCOL.md 6.1)
        self._precompute_genres()

    def _precompute_genres(self):
        """Precompute genre statistics to avoid repetitive loops."""
        if self.movies_df is None or self.movies_df.empty:
            return

        genre_counts = Counter()
        genre_ratings = {}

        for row in self.movies_df.itertuples(index=False):
            genres = split_genres(str(row.genres))
            for g in genres:
                if g:
                    genre_counts[g] += 1
                    if g not in genre_ratings:
                        genre_ratings[g] = []
                    genre_ratings[g].append(row.vote_average)

        self.genre_list_detailed = []
        for genre, count in genre_counts.most_common():
            avg_rating = np.mean(genre_ratings[genre]) if genre_ratings[genre] else 0
            self.genre_list_detailed.append(
                {
                    "name": genre,
                    "movie_count": count,
                    "average_rating": round(float(avg_rating), 2),
                }
            )
        self.genre_list = [g["name"] for g in self.genre_list_detailed]

    def _load_ratings(self, conn):
        """Fetch rating data, with MovieLens fallback."""
        try:
            self.ratings_df = pd.read_sql_query(
                "SELECT user_id, movie_id, rating FROM ratings", conn
            )
        except Exception as e:
            logger.error(f"Error loading ratings: {e}")
            self.ratings_df = pd.DataFrame()

        # Fallback: load MovieLens ratings if regular ratings are sparse
        if self.ratings_df is None or len(self.ratings_df) < 100:
            try:
                ml_ratings = pd.read_sql_query(
                    "SELECT ml_user_id as user_id, movie_id, rating * 2 as rating FROM ml_ratings LIMIT 5000000",
                    conn,
                )
                if not ml_ratings.empty:
                    if self.ratings_df is not None and not self.ratings_df.empty:
                        self.ratings_df = pd.concat([self.ratings_df, ml_ratings], ignore_index=True)
                    else:
                        self.ratings_df = ml_ratings
                    logger.info(f"Loaded {len(ml_ratings)} MovieLens ratings (normalized 0.5-5.0 -> 1-10 scale)")
            except Exception as e:
                logger.warning(f"MovieLens ratings not available: {e}")

    def train(self) -> "EnhancedRecommendationEngine":
        """Train all recommendation models."""
        if self.movies_df is None:
            self.load_data()

        # Train content-based model
        self._train_content_model()

        # Train collaborative model
        self._train_collaborative_model()

        # Initialize advanced ML engines (graceful degradation if any fail)
        self._init_advanced_engines()

        self.is_trained = True
        return self

    def _init_advanced_engines(self) -> None:
        """Initialise HSTU, CLRec, Bandit, Temporal, and Multi-Objective engines.

        All engines are independent — they share only the read-only movies_df.
        We run them in parallel via ThreadPoolExecutor for ~2-3x startup speedup.
        """
        if self.movies_df is None or self.movies_df.empty:
            return

        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time

        t0 = time.monotonic()
        movies_df = self.movies_df
        ratings_df = self.ratings_df
        movie_id_mapping = self._movie_index_by_id

        def _init_hstu():
            from backend.services.recommendation_engine_service.engines.hstu_engine import get_hstu_engine
            eng = get_hstu_engine()
            if not eng.is_ready:
                eng.load(movies_df=movies_df, movie_id_mapping=movie_id_mapping)
            return "HSTU"

        def _init_clrec():
            from backend.services.recommendation_engine_service.engines.clrec_engine import get_clrec_engine
            eng = get_clrec_engine()
            if not eng.is_ready:
                eng.load(movies_df=movies_df)
            return "CLRec"

        def _init_bandit():
            from backend.services.recommendation_engine_service.engines.bandit_engine import get_bandit_engine
            eng = get_bandit_engine()
            if not eng.is_ready:
                eng.load(movies_df=movies_df)
            return "Bandit"

        def _init_temporal():
            from backend.services.recommendation_engine_service.engines.temporal_engine import get_temporal_engine
            eng = get_temporal_engine()
            if not eng.is_ready and ratings_df is not None and not ratings_df.empty:
                eng.load(ratings_df=ratings_df, movies_df=movies_df)
            return "Temporal"

        def _init_mtl():
            from backend.services.recommendation_engine_service.engines.multiobjective_engine import get_multiobjective_engine
            eng = get_multiobjective_engine()
            if not eng.is_ready:
                eng.load(movies_df=movies_df)
            return "MTL"

        tasks = [_init_hstu, _init_clrec, _init_bandit, _init_temporal, _init_mtl]

        with ThreadPoolExecutor(max_workers=5, thread_name_prefix="engine-init") as pool:
            futures = {pool.submit(fn): fn.__name__ for fn in tasks}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    result = future.result()
                    logger.debug("Advanced engine %s ready.", result)
                except Exception as e:
                    logger.warning("%s init skipped: %s", name, e)

        elapsed = time.monotonic() - t0
        logger.info("Advanced engines initialized in %.1fs (parallel).", elapsed)

    def _train_content_model(self):
        """Train TF-IDF content-based model."""
        if self.movies_df is None or self.movies_df.empty:
            return

        try:
            vectors = self.vectorizer.fit_transform(self.movies_df["combined_features"])
            self.content_matrix = vectors.tocsr()

            # Memory safety: don't allocate NxN matrix if N is too large
            # 10,000 movies = 10,000 * 10,000 * 8 bytes = 800 MB
            if len(self.movies_df) > 10000:
                logger.info(
                    f"Large dataset ({len(self.movies_df)} movies). Similarity matrix disabled to save memory."
                )
                self.similarity_matrix = None
                return

            self.similarity_matrix = cosine_similarity(self.content_matrix)
        except (ValueError, MemoryError) as e:
            logger.warning(f"Could not train content model: {e}")
            self.content_matrix = None
            self.similarity_matrix = None
        except Exception as e:
            logger.error(f"Unexpected error training content model: {e}")
            self.content_matrix = None
            self.similarity_matrix = None

    def _train_collaborative_model(self, n_factors: int = 50):
        """Train SVD collaborative filtering model."""
        if self.ratings_df is None or len(self.ratings_df) == 0:
            return

        try:
            # Ensure numeric types
            for col in ["user_id", "movie_id", "rating"]:
                self.ratings_df[col] = pd.to_numeric(
                    self.ratings_df[col], errors="coerce"
                )
            self.ratings_df = self.ratings_df.dropna()

            pivot = self.ratings_df.pivot_table(
                index="user_id", columns="movie_id", values="rating", fill_value=0
            )

            user_means = pivot.mean(axis=1)
            pivot_normalized = pivot.sub(user_means, axis=0)

            matrix = csr_matrix(pivot_normalized.values)
            n_factors = min(n_factors, min(matrix.shape) - 1)

            if n_factors < 1:
                return

            U, sigma, Vt = svds(matrix, k=n_factors)
            sigma = np.diag(sigma)

            self.collab_predictions = np.dot(np.dot(U, sigma), Vt)
            self.collab_predictions = pd.DataFrame(
                self.collab_predictions + user_means.values.reshape(-1, 1),
                columns=pivot.columns,
            )
        except Exception as e:
            logger.warning(f"Could not train collaborative model: {e}")

    def find_movie(self, query: str) -> Optional[Dict]:
        """Find a movie by title using fuzzy matching."""
        if self.movies_df is None or self.movies_df.empty:
            return None

        normalized_query = query.casefold()
        matches = difflib.get_close_matches(
            normalized_query, self._normalized_titles, n=1, cutoff=0.4
        )

        if matches:
            matched_title = self._title_lookup[matches[0]]
            row = self.movies_df[self.movies_df.title == matched_title].iloc[0]
            return self._movie_to_dict(row)
        return None

    def get_movie_by_id(self, movie_id: int) -> Optional[Dict]:
        """Get movie by ID."""
        if self.movies_df is None or self.movies_df.empty:
            return None
        movie_idx = self._movie_index_by_id.get(movie_id)
        if movie_idx is not None:
            return self._movie_to_dict(self.movies_df.iloc[movie_idx])
        return None

    def get_movies_by_ids(self, movie_ids: List[int]) -> Dict[int, Dict]:
        """Batch-fetch movies by IDs. Returns {movie_id: movie_dict} for found movies."""
        if self.movies_df is None or self.movies_df.empty or not movie_ids:
            return {}
        result = {}
        for mid in movie_ids:
            idx = self._movie_index_by_id.get(mid)
            if idx is not None:
                result[mid] = self._movie_to_dict(self.movies_df.iloc[idx])
        return result

    def _resolve_movie_id(
        self, movie_id: Optional[int], movie_title: Optional[str]
    ) -> Optional[int]:
        """Helper to resolve movie_id from ID or Title."""
        if movie_id is not None:
            return movie_id
        if movie_title:
            movie = self.find_movie(movie_title)
            return movie["id"] if movie else None
        return None

    def _movie_to_dict(self, row: pd.Series) -> Dict:
        """Convert DataFrame row to dictionary with new metadata."""
        return {
            "id": safe_int(row["id"]),
            "title": safe_str(row["title"]),
            "genres": split_genres(safe_str(row.get("genres", ""))),
            "director": safe_str(row.get("director", "")),
            "cast": safe_str(row.get("cast", "")),
            "vote_average": safe_float(row.get("vote_average", 0)),
            "vote_count": safe_int(row.get("vote_count", 0)),
            "imdb_rating": safe_float(row.get("imdb_rating", 0)),
            "rt_critic_score": safe_int(row.get("rt_critic_score", 0)),
            "rt_audience_score": safe_int(row.get("rt_audience_score", 0)),
            "reddit_sentiment": safe_float(row.get("reddit_sentiment", 0)),
            "tagline": safe_str(row.get("tagline", "")),
            "keywords": safe_str(row.get("keywords", "")),
            "overview": safe_str(row.get("overview", "")),
            "poster_path": safe_str(row.get("poster_path", "")),
            "backdrop_path": safe_str(row.get("backdrop_path", "")),
            "release_date": safe_str(row.get("release_date", "")),
            "runtime": safe_int(row.get("runtime", 0)),
            "budget": safe_int(row.get("budget", 0)),
            "revenue": safe_int(row.get("revenue", 0)),
            "homepage": safe_str(row.get("homepage", "")),
            "imdb_id": safe_str(row.get("imdb_id", "")),
            "tmdb_id": safe_int(row.get("tmdb_id", 0)) or safe_int(row.get("id", 0)),
            "original_language": safe_str(row.get("original_language", "en")),
            "cinevault_qualities": ["720p.WEB", "1080p.WEB"],
        }

    def _get_quality_score(self, row: pd.Series) -> float:
        """Calculate quality score (0-1) based on multiple critics and metrics."""
        vote_avg = safe_float(row.get("vote_average", 0)) / 10
        critic_score = (
            safe_int(row.get("rt_critic_score", 0)) / 100
            if row.get("rt_critic_score")
            else vote_avg
        )
        audience_score = (
            safe_int(row.get("rt_audience_score", 0)) / 100
            if row.get("rt_audience_score")
            else vote_avg
        )
        sentiment = min(1.0, safe_float(row.get("reddit_sentiment", 0)) / 50)

        return critic_score * 0.4 + audience_score * 0.4 + sentiment * 0.2

    def _get_popularity_score(self, row: pd.Series) -> float:
        """Calculate popularity score (0-1) using logarithmic scaling."""
        vote_count = safe_int(row.get("vote_count", 0))
        return min(1.0, np.log1p(vote_count) / np.log1p(10000))

    def _get_diversity_penalty(self, movie_genres: set, seen_genres: Counter) -> float:
        """Calculate diversity penalty if genres are repeated."""
        primary_genre = list(movie_genres)[0] if movie_genres else "unknown"
        if seen_genres[primary_genre] > 1:
            return 0.15 * (seen_genres[primary_genre] - 1)
        return 0.0

    @staticmethod
    def _split_terms(value: str) -> set[str]:
        return {
            part.strip().casefold()
            for part in re.split(r"[\s,/|]+", value)
            if part.strip()
        }

    @staticmethod
    def _scale_scores(scores: np.ndarray) -> np.ndarray:
        values = np.nan_to_num(np.asarray(scores, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        if values.size == 0:
            return values
        min_score = float(values.min())
        max_score = float(values.max())
        if abs(max_score - min_score) < 1e-9:
            if max_score <= 0:
                return np.zeros_like(values)
            return np.clip(values / max_score, 0.0, 1.0)
        return (values - min_score) / (max_score - min_score)

    @staticmethod
    def _ensure_sparse_vector(vector: Any) -> Optional[csr_matrix]:
        if vector is None:
            return None
        sparse_vector = vector if isinstance(vector, csr_matrix) else csr_matrix(vector)
        if sparse_vector.nnz == 0:
            return None
        return normalize(sparse_vector, norm="l2")

    def _resolve_movie_ids_from_titles(self, titles: Optional[List[str]]) -> set[int]:
        resolved_ids: set[int] = set()
        for title in titles or []:
            movie = self.find_movie(title)
            if movie:
                resolved_ids.add(safe_int(movie["id"]))
        return resolved_ids

    def _fetch_user_feedback(self, user_id: int) -> Tuple[set[int], set[int]]:
        positive_ids: set[int] = set()
        negative_ids: set[int] = set()

        try:
            with db_engine.connect() as conn:
                liked_rows = conn.execute(
                    text(
                        """
                        SELECT movie_id
                        FROM ratings
                        WHERE user_id = :user_id AND rating >= 7
                        """
                    ),
                    {"user_id": user_id},
                ).fetchall()
                disliked_rows = conn.execute(
                    text(
                        """
                        SELECT movie_id
                        FROM ratings
                        WHERE user_id = :user_id AND rating <= 4
                        """
                    ),
                    {"user_id": user_id},
                ).fetchall()
                favorite_rows = conn.execute(
                    text(
                        """
                        SELECT movie_id
                        FROM user_favorites
                        WHERE user_id = :user_id
                        """
                    ),
                    {"user_id": user_id},
                ).fetchall()
        except Exception as exc:
            logger.warning("Could not load user feedback for discovery mode: %s", exc)
            return positive_ids, negative_ids

        positive_ids.update(safe_int(row[0]) for row in liked_rows)
        positive_ids.update(safe_int(row[0]) for row in favorite_rows)
        negative_ids.update(safe_int(row[0]) for row in disliked_rows)
        negative_ids.difference_update(positive_ids)
        return positive_ids, negative_ids

    # Language names → ISO 639-1 codes used in original_language column
    _LANGUAGE_MAP: Dict[str, str] = {
        "hindi": "hi", "bollywood": "hi",
        "tamil": "ta", "kollywood": "ta",
        "telugu": "te", "tollywood": "te",
        "malayalam": "ml", "mollywood": "ml",
        "kannada": "kn", "sandalwood": "kn",
        "bengali": "bn", "bangla": "bn",
        "marathi": "mr",
        "punjabi": "pa",
        "gujarati": "gu",
        "english": "en", "hollywood": "en",
        "korean": "ko", "k-drama": "ko",
        "japanese": "ja", "anime": "ja",
        "french": "fr",
        "spanish": "es",
        "italian": "it",
        "chinese": "zh", "mandarin": "zh",
        "russian": "ru",
        "turkish": "tr",
        "german": "de",
        "portuguese": "pt",
        "thai": "th",
        "filipino": "tl", "tagalog": "tl",
    }

    # Common genre aliases → canonical genre names
    _GENRE_ALIASES: Dict[str, str] = {
        "sci-fi": "science fiction", "scifi": "science fiction",
        "rom-com": "romance", "romcom": "romance",
        "biopic": "history", "biographical": "history",
        "superhero": "action", "martial-arts": "action",
        "animated": "animation", "anime": "animation",
        "scary": "horror", "slasher": "horror", "ghost": "horror",
        "whodunit": "mystery", "detective": "mystery",
        "spy": "thriller", "espionage": "thriller",
        "heist": "crime", "gangster": "crime",
        "musical": "music", "war-film": "war",
        "rom": "romance", "romantic": "romance",
        "funny": "comedy", "humour": "comedy", "humor": "comedy",
        "suspense": "thriller", "suspenseful": "thriller",
        "kids": "family", "children": "family",
        "period": "history", "historical": "history",
        "fantasy-adventure": "fantasy",
        "space": "science fiction", "aliens": "science fiction",
        "robots": "science fiction", "dystopian": "science fiction",
    }

    def _build_query_context(self, query: str) -> Dict[str, Any]:
        normalized_query = re.sub(r"\s+", " ", safe_str(query).casefold()).strip()
        query_words = set(normalized_query.split())

        # Expand genre aliases before matching
        expanded_genres: set = set()
        alias_terms: set = set()
        for word in query_words:
            if word in self._GENRE_ALIASES:
                expanded_genres.add(self._GENRE_ALIASES[word])
                alias_terms.add(word)
        # Also check hyphenated terms in the raw query
        for alias, canonical in self._GENRE_ALIASES.items():
            if alias in normalized_query:
                expanded_genres.add(canonical)
                alias_terms.add(alias)

        genres = set()
        for genre in self.genre_list:
            if not genre:
                continue
            gc = genre.casefold()
            # Single-word genres match against word set; multi-word match as substring
            if " " in gc:
                if gc in normalized_query:
                    genres.add(gc)
            else:
                if gc in query_words:
                    genres.add(gc)
        genres.update(expanded_genres)
        years = set(re.findall(r"\b(?:19|20)\d{2}\b", normalized_query))

        # Extract language filter from query
        language = None
        language_term = None
        for lang_name, lang_code in self._LANGUAGE_MAP.items():
            if lang_name in query_words:
                language = lang_code
                language_term = lang_name
                break

        # Extract non-genre, non-language keywords for subgenre/keyword boosting
        # (e.g. "spy", "heist", "zombie", "war", "space")
        stopwords = {"movie", "movies", "film", "films", "good", "best", "top", "new", "old", "like", "with", "the", "and", "a", "an"}
        # Include individual words from multi-word genres (e.g., "science", "fiction")
        # so they get excluded from keyword extraction
        genre_words: set[str] = set()
        for g in self.genre_list:
            gc = g.casefold()
            genre_words.add(gc)
            genre_words.update(gc.split())
        lang_words = set(self._LANGUAGE_MAP.keys())
        alias_words = set(self._GENRE_ALIASES.keys())
        keywords = query_words - genres - genre_words - lang_words - alias_words - stopwords - set(years)

        # Remove language, alias, and generic stopwords from the TF-IDF query to
        # prevent irrelevant matches (e.g., "hindi" matching "Hindi Medium",
        # "best movies" matching everything).
        tfidf_query = normalized_query
        terms_to_remove = (
            ([language_term] if language_term else [])
            + list(alias_terms)
            + [w for w in stopwords if w in tfidf_query.split()]
        )
        for term in terms_to_remove:
            if term:
                tfidf_query = re.sub(rf"\b{re.escape(term)}\b", "", tfidf_query).strip()
        tfidf_query = re.sub(r"\s+", " ", tfidf_query).strip()

        return {
            "normalized_query": tfidf_query,
            "original_query": normalized_query,
            "genres": genres,
            "years": years,
            "language": language,
            "keywords": keywords,
        }

    def _build_preference_profile(
        self,
        user_id: Optional[int] = None,
        liked_movie_ids: Optional[List[int]] = None,
        liked_titles: Optional[List[str]] = None,
        excluded_movie_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        positive_ids = {safe_int(movie_id) for movie_id in liked_movie_ids or [] if movie_id is not None}
        positive_ids.update(self._resolve_movie_ids_from_titles(liked_titles))
        negative_ids = {safe_int(movie_id) for movie_id in excluded_movie_ids or [] if movie_id is not None}

        if user_id is not None:
            db_positive_ids, db_negative_ids = self._fetch_user_feedback(user_id)
            positive_ids.update(db_positive_ids)
            negative_ids.update(db_negative_ids)

        negative_ids.difference_update(positive_ids)

        positive_indices = [
            self._movie_index_by_id[movie_id]
            for movie_id in positive_ids
            if movie_id in self._movie_index_by_id
        ]
        negative_indices = [
            self._movie_index_by_id[movie_id]
            for movie_id in negative_ids
            if movie_id in self._movie_index_by_id
        ]

        genre_counter: Counter[str] = Counter()
        director_counter: Counter[str] = Counter()
        cast_counter: Counter[str] = Counter()

        for movie_idx in positive_indices:
            row = self.movies_df.iloc[movie_idx]
            genre_counter.update(g.casefold() for g in split_genres(safe_str(row.get("genres", ""))))

            director = safe_str(row.get("director", "")).casefold()
            if director:
                director_counter.update([director])

            cast_counter.update(self._split_terms(safe_str(row.get("cast", ""))))

        positive_vector = None
        negative_vector = None
        if self.content_matrix is not None and positive_indices:
            positive_vector = self._ensure_sparse_vector(
                self.content_matrix[positive_indices].mean(axis=0)
            )
        if self.content_matrix is not None and negative_indices:
            negative_vector = self._ensure_sparse_vector(
                self.content_matrix[negative_indices].mean(axis=0)
            )

        taste_vector = positive_vector
        if positive_vector is not None and negative_vector is not None:
            # Rocchio-style relevance feedback:
            # keep what the user likes and explicitly push away low-rated items.
            taste_vector = self._ensure_sparse_vector(positive_vector - (0.35 * negative_vector))

        return {
            "positive_ids": positive_ids,
            "negative_ids": negative_ids,
            "positive_indices": positive_indices,
            "genre_counter": genre_counter,
            "director_counter": director_counter,
            "cast_counter": cast_counter,
            "taste_vector": taste_vector,
        }

    def _profile_affinity_score(self, row: pd.Series, profile: Dict[str, Any]) -> float:
        score = 0.0
        movie_genres = {g.casefold() for g in split_genres(safe_str(row.get("genres", "")))}
        score += sum(profile["genre_counter"].get(genre, 0) for genre in movie_genres)

        director = safe_str(row.get("director", "")).casefold()
        if director:
            score += profile["director_counter"].get(director, 0) * 2.5

        cast_terms = self._split_terms(safe_str(row.get("cast", "")))
        score += 0.2 * sum(profile["cast_counter"].get(actor, 0) for actor in cast_terms)
        return float(score)

    def _semantic_boost_lookup(
        self, semantic_candidates: Optional[List[Dict]]
    ) -> Dict[int, float]:
        if not semantic_candidates:
            return {}

        raw_scores = np.array(
            [
                safe_float(
                    candidate.get("rerank_score", candidate.get("score", 0.0))
                )
                for candidate in semantic_candidates
            ],
            dtype=float,
        )
        scaled_scores = self._scale_scores(raw_scores)
        total_candidates = max(len(semantic_candidates), 1)
        boosts: Dict[int, float] = {}

        for rank, (candidate, scaled_score) in enumerate(
            zip(semantic_candidates, scaled_scores), start=1
        ):
            movie_id = safe_int(candidate.get("id"))
            rank_bonus = 1 - ((rank - 1) / total_candidates)
            boosts[movie_id] = max(
                boosts.get(movie_id, 0.0),
                float(0.65 * scaled_score + 0.35 * rank_bonus),
            )

        return boosts

    def _pairwise_similarity(self, left_idx: int, right_idx: int) -> float:
        if self.similarity_matrix is not None:
            return float(self.similarity_matrix[left_idx, right_idx])

        if self.content_matrix is None:
            return 0.0

        return float(
            linear_kernel(
                self.content_matrix[left_idx], self.content_matrix[right_idx]
            ).ravel()[0]
        )

    def _diversify_candidates(
        self,
        candidate_indices: List[int],
        candidate_payloads: List[Dict],
        base_scores: np.ndarray,
        limit: int,
        diversity_factor: float,
    ) -> List[Dict]:
        if not candidate_indices or not candidate_payloads:
            return []

        diversity_weight = min(max(diversity_factor, 0.0), 0.85)
        remaining = list(range(len(candidate_indices)))
        selected_positions: List[int] = []

        while remaining and len(selected_positions) < limit:
            best_position = remaining[0]
            best_score = float("-inf")

            for position in remaining:
                similarity_penalty = 0.0
                if selected_positions:
                    similarity_penalty = max(
                        self._pairwise_similarity(
                            candidate_indices[position], candidate_indices[selected]
                        )
                        for selected in selected_positions
                    )

                mmr_score = (
                    (1 - diversity_weight) * safe_float(base_scores[position])
                    - diversity_weight * similarity_penalty
                )
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_position = position

            selected_positions.append(best_position)
            remaining.remove(best_position)

        return [candidate_payloads[position] for position in selected_positions]

    def _generate_discovery_reason(
        self,
        row: pd.Series,
        query_context: Dict[str, Any],
        profile: Dict[str, Any],
        semantic_score: float,
        profile_score: float,
        collaborative_score: float,
    ) -> str:
        reasons: List[str] = []
        movie_genres = {g.casefold() for g in split_genres(safe_str(row.get("genres", "")))}
        matched_query_genres = movie_genres & query_context.get("genres", set())

        if matched_query_genres:
            genres = ", ".join(sorted(matched_query_genres)[:2]).title()
            reasons.append(f"Matches your {genres} brief")
        elif semantic_score >= 0.6:
            reasons.append("Strong match for your described vibe")

        director = safe_str(row.get("director", ""))
        if director and profile["director_counter"].get(director.casefold(), 0):
            reasons.append(f"Fits your preference for {director} films")
        else:
            matched_taste_genres = movie_genres & set(profile["genre_counter"].keys())
            if matched_taste_genres and profile_score >= 0.35:
                genres = ", ".join(sorted(matched_taste_genres)[:2]).title()
                reasons.append(f"Aligned with your taste in {genres}")

        if collaborative_score >= 0.72:
            reasons.append("Users with similar taste rate it highly")
        elif safe_float(row.get("vote_average", 0)) >= 8:
            reasons.append("Strong audience reception")

        return "; ".join(reasons[:2]) if reasons else "Recommended from your taste profile"

    def get_content_recommendations(
        self, movie_id: int, limit: int = 10
    ) -> List[Dict]:
        """Get content-based recommendations."""
        if self.content_matrix is None and self.similarity_matrix is None:
            return self.get_hybrid_recommendations(movie_id=movie_id, limit=limit)

        matches = self.movies_df[self.movies_df.id == movie_id]
        if len(matches) == 0:
            return []

        movie_idx = matches.index[0]
        source_movie = self._movie_to_dict(self.movies_df.iloc[movie_idx])
        if self.similarity_matrix is not None:
            scores = list(enumerate(self.similarity_matrix[movie_idx]))
        else:
            similarity_scores = linear_kernel(
                self.content_matrix, self.content_matrix[movie_idx]
            ).ravel()
            scores = list(enumerate(similarity_scores))
        sorted_scores = sorted(scores, key=lambda x: x[1], reverse=True)[1 : limit + 1]

        results = []
        for idx, score in sorted_scores:
            movie = self._movie_to_dict(self.movies_df.iloc[idx])
            results.append(
                {
                    **movie,
                    "score": round(float(score), 4),
                    "content_score": round(float(score) * 100, 1),
                    "collaborative_score": 0.0,
                    "hybrid_score": round(float(score) * 100, 1),
                    "reason": self._generate_reason(
                        source_movie, movie, float(score), same_director=False
                    ),
                }
            )

        return results

    def get_collaborative_score(self, user_id: int, movie_id: int) -> float:
        """Get collaborative filtering predicted rating."""
        if self.collab_predictions is None:
            return 5.0

        try:
            if (
                movie_id in self.collab_predictions.columns
                and user_id in self.collab_predictions.index
            ):
                return float(self.collab_predictions.loc[user_id, movie_id])
        except (ValueError, KeyError, TypeError, AttributeError):
            # Gracefully handle missing predictions for new users/movies
            pass
        return 5.0

    def get_hybrid_recommendations(
        self,
        movie_id: Optional[int] = None,
        movie_title: Optional[str] = None,
        user_id: Optional[int] = None,
        limit: int = settings.REC_LIMIT_DEFAULT,
        content_weight: float = settings.REC_CONTENT_WEIGHT_DEFAULT,
        diversity_factor: float = settings.REC_DIVERSITY_FACTOR_DEFAULT,
        min_rating: float = 0,
    ) -> List[Dict]:
        """Get hybrid recommendations with improved scoring."""
        if self.movies_df is None or self.movies_df.empty:
            return []
        movie_id = self._resolve_movie_id(movie_id, movie_title)
        if movie_id is None:
            return []

        cache_key = (
            f"hybrid_{movie_id}_{user_id}_{limit}_{content_weight}_{diversity_factor}"
        )
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        source_movie = self.get_movie_by_id(movie_id)
        if not source_movie or (self.similarity_matrix is None and self.content_matrix is None):
            return self.get_trending(limit)

        try:
            movie_idx = self.movies_df[self.movies_df.id == movie_id].index[0]
        except IndexError:
            return []

        source_director = safe_str(source_movie.get("director", "")).casefold()

        # Get content-based candidates (more than needed for filtering)
        if self.similarity_matrix is not None:
            content_scores = list(enumerate(self.similarity_matrix[movie_idx]))
        else:
            content_scores = list(
                enumerate(
                    linear_kernel(
                        self.content_matrix, self.content_matrix[movie_idx]
                    ).ravel()
                )
            )
        content_scores = sorted(content_scores, key=lambda x: x[1], reverse=True)[
            1 : limit * 3
        ]

        # Calculate hybrid scores
        results = []
        seen_genres = Counter()

        for idx, content_score in content_scores:
            row = self.movies_df.iloc[idx]
            if row["vote_average"] < min_rating:
                continue

            movie_dict = self._movie_to_dict(row)
            movie_genres = {g.casefold() for g in split_genres(movie_dict.get("genres", ""))}

            # Score components
            collab_score = (
                (self.get_collaborative_score(user_id, movie_dict["id"]) / 10)
                if user_id
                else 0.5
            )
            popularity = self._get_popularity_score(row)
            quality = self._get_quality_score(row)
            director_bonus = (
                settings.REC_DIRECTOR_BONUS
                if source_director
                and source_director == safe_str(row.get("director", "")).casefold()
                else 0.0
            )
            diversity_penalty = self._get_diversity_penalty(movie_genres, seen_genres)

            hybrid_score = (
                content_score * content_weight
                + collab_score * (1 - content_weight) * settings.REC_COLLAB_WEIGHT
                + quality * settings.REC_QUALITY_WEIGHT
                + popularity * settings.REC_POPULARITY_WEIGHT
                + director_bonus
                - diversity_penalty
            )

            results.append(
                {
                    **movie_dict,
                    "content_score": round(content_score * 100, 1),
                    "collaborative_score": round(collab_score * 100, 1),
                    "hybrid_score": round(hybrid_score * 100, 1),
                    "reason": self._generate_reason(
                        source_movie, movie_dict, content_score, director_bonus > 0
                    ),
                }
            )

            for g in movie_genres:
                seen_genres[g] += 1

        # Final sort and limit
        results.sort(key=lambda x: x["hybrid_score"], reverse=True)
        results = results[:limit]
        self.cache.set(cache_key, results)
        return results

    def _generate_reason(
        self, source: Dict, target: Dict, content_score: float, same_director: bool
    ) -> str:
        """Generate human-readable recommendation reason."""
        reasons = []

        # Check genre overlap
        source_genres = {g.casefold() for g in split_genres(safe_str(source.get("genres", "")))}
        target_genres = {g.casefold() for g in split_genres(safe_str(target.get("genres", "")))}
        common_genres = source_genres & target_genres

        if common_genres:
            genres_str = ", ".join(list(common_genres)[:2]).title()
            reasons.append(f"Similar {genres_str} themes")

        if same_director:
            reasons.append(f"Same director: {target.get('director', 'Unknown')}")

        if content_score > 0.3:
            reasons.append("Highly similar content")
        elif content_score > 0.15:
            reasons.append("Related storyline")

        if target["vote_average"] >= 7.5:
            reasons.append("Highly rated")

        return "; ".join(reasons[:2]) if reasons else "You might enjoy this"

    def get_personalized_recommendations(
        self, user_id: int, limit: int = 10, exclude_rated: bool = True
    ) -> List[Dict]:
        """Get personalized recommendations based on user's rating history."""
        if self.movies_df is None or self.movies_df.empty:
            return []
        with db_engine.connect() as conn:
            top_rated = conn.execute(
                text(
                    """
                    SELECT movie_id, rating
                    FROM ratings
                    WHERE user_id = :user_id AND rating >= 7
                    ORDER BY rating DESC, updated_at DESC
                    LIMIT 5
                    """
                ),
                {"user_id": user_id},
            ).fetchall()

        if not top_rated:
            # Fall back to trending for new users
            return self.get_trending(limit)

        # Get rated movie IDs to exclude
        excluded_ids = set()
        if exclude_rated:
            with db_engine.connect() as conn:
                excluded_ids = {
                    int(row[0])
                    for row in conn.execute(
                        text("SELECT movie_id FROM ratings WHERE user_id = :user_id"),
                        {"user_id": user_id},
                    ).fetchall()
                }

        # Aggregate recommendations from top-rated movies
        all_recs = []
        for movie_id, _ in top_rated[:3]:
            recs = self.get_hybrid_recommendations(
                movie_id=movie_id,
                user_id=user_id,
                limit=limit * 2,
                diversity_factor=0.3,
            )
            for rec in recs:
                if rec["id"] not in excluded_ids:
                    all_recs.append(rec)

        # Deduplicate and sort
        seen_ids = set()
        unique_recs = []
        for rec in sorted(all_recs, key=lambda x: x["hybrid_score"], reverse=True):
            if rec["id"] not in seen_ids:
                seen_ids.add(rec["id"])
                unique_recs.append(rec)
                if len(unique_recs) >= limit:
                    break

        return unique_recs

    def discover_movies(
        self,
        query: Optional[str] = None,
        user_id: Optional[int] = None,
        liked_movie_ids: Optional[List[int]] = None,
        liked_titles: Optional[List[str]] = None,
        excluded_movie_ids: Optional[List[int]] = None,
        limit: int = settings.REC_LIMIT_DEFAULT,
        min_rating: float = 0,
        diversity_factor: float = settings.REC_DIVERSITY_FACTOR_DEFAULT,
        semantic_candidates: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Hybrid discovery endpoint for mood, taste, and collaborative ranking."""
        if self.movies_df is None or self.movies_df.empty:
            return {
                "query_movie": query,
                "query_user": str(user_id) if user_id is not None else None,
                "recommendation_type": "discover",
                "total_results": 0,
                "applied_signals": [],
                "recommendations": [],
            }

        cache_key = RedisRecommendationCache._generate_cache_key(
            "discover",
            query=query,
            user_id=user_id,
            liked_movie_ids=sorted(liked_movie_ids or []),
            liked_titles=sorted(liked_titles or []),
            excluded_movie_ids=sorted(excluded_movie_ids or []),
            limit=limit,
            min_rating=min_rating,
            diversity_factor=diversity_factor,
        )
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        if self.content_matrix is None:
            self._train_content_model()

        query_context = self._build_query_context(query or "")
        profile = self._build_preference_profile(
            user_id=user_id,
            liked_movie_ids=liked_movie_ids,
            liked_titles=liked_titles,
            excluded_movie_ids=excluded_movie_ids,
        )
        semantic_boosts = self._semantic_boost_lookup(semantic_candidates)

        excluded_ids = set(profile["positive_ids"]) | set(profile["negative_ids"])
        excluded_ids.update(safe_int(movie_id) for movie_id in excluded_movie_ids or [])
        applied_signals: List[str] = []

        mask = self.movies_df["vote_average"] >= min_rating
        if excluded_ids:
            mask &= ~self.movies_df["id"].isin(excluded_ids)

        # Apply language filter when query specifies a language
        if query_context.get("language"):
            lang_code = query_context["language"]
            lang_mask = self.movies_df["original_language"].astype(str).str.strip().str.lower() == lang_code
            if lang_mask.any():
                mask &= lang_mask
                applied_signals.append(f"language:{lang_code}")

        candidate_df = self.movies_df[mask]
        if candidate_df.empty:
            return {
                "query_movie": query,
                "query_user": str(user_id) if user_id is not None else None,
                "recommendation_type": "discover",
                "total_results": 0,
                "applied_signals": applied_signals,
                "recommendations": [],
            }

        candidate_positions = candidate_df.index.to_numpy(dtype=int)
        candidate_count = len(candidate_positions)
        base_scores = np.zeros(candidate_count, dtype=float)
        query_scores_scaled = np.zeros(candidate_count, dtype=float)
        profile_scores_scaled = np.zeros(candidate_count, dtype=float)
        metadata_scores_scaled = np.zeros(candidate_count, dtype=float)
        collaborative_scores = np.zeros(candidate_count, dtype=float)
        semantic_scores = np.zeros(candidate_count, dtype=float)
        genre_match_bonus = np.zeros(candidate_count, dtype=float)
        quality_scores = np.zeros(candidate_count, dtype=float)
        popularity_scores = np.zeros(candidate_count, dtype=float)

        if query_context["normalized_query"] and self.content_matrix is not None:
            query_vector = self._ensure_sparse_vector(
                self.vectorizer.transform([query_context["normalized_query"]])
            )
            if query_vector is not None:
                query_scores_scaled = self._scale_scores(
                    linear_kernel(self.content_matrix[candidate_positions], query_vector).ravel()
                )
                base_scores += query_scores_scaled * 0.33
                applied_signals.append("query_intent")

        if profile["taste_vector"] is not None and self.content_matrix is not None:
            profile_scores_scaled = self._scale_scores(
                linear_kernel(
                    self.content_matrix[candidate_positions], profile["taste_vector"]
                ).ravel()
            )
            base_scores += profile_scores_scaled * 0.25
            applied_signals.append("taste_feedback")

        metadata_scores = np.array(
            [
                self._profile_affinity_score(self.movies_df.iloc[position], profile)
                for position in candidate_positions
            ],
            dtype=float,
        )
        if np.any(metadata_scores):
            metadata_scores_scaled = self._scale_scores(metadata_scores)
            base_scores += metadata_scores_scaled * 0.12
            applied_signals.append("metadata_affinity")

        if semantic_boosts:
            semantic_scores = np.array(
                [
                    semantic_boosts.get(
                        safe_int(self.movies_df.iloc[position]["id"]), 0.0
                    )
                    for position in candidate_positions
                ],
                dtype=float,
            )
            if np.any(semantic_scores):
                base_scores += semantic_scores * 0.14
                applied_signals.append("dense_semantic")

        if query_context["genres"]:
            # Proper set intersection now that genres are pipe-delimited and
            # multi-word genres like "Science Fiction" are preserved as single tokens
            def _genre_match(position: int) -> float:
                movie_genres = {g.casefold() for g in split_genres(safe_str(self.movies_df.iloc[position].get("genres", "")))}
                return 1.0 if movie_genres & query_context["genres"] else 0.0

            genre_match_bonus = np.array(
                [_genre_match(pos) for pos in candidate_positions],
                dtype=float,
            )
            if np.any(genre_match_bonus):
                # Strong weight: when user explicitly asks for a genre, it should
                # be the dominant signal (not drowned out by generic TF-IDF scores)
                base_scores += genre_match_bonus * 0.25
                applied_signals.append("genre_constraints")

        # Keyword boost: match non-genre keywords (e.g. "spy", "heist", "zombie")
        # against title, overview, and keywords fields
        if query_context.get("keywords"):
            kw_set = query_context["keywords"]

            def _keyword_score(position: int) -> float:
                row = self.movies_df.iloc[position]
                searchable = " ".join([
                    safe_str(row.get("title", "")),
                    safe_str(row.get("overview", "")),
                    safe_str(row.get("keywords", "")),
                    safe_str(row.get("genres", "")),
                ]).casefold()
                hits = sum(1 for kw in kw_set if kw in searchable)
                return hits / len(kw_set) if kw_set else 0.0

            keyword_scores = np.array(
                [_keyword_score(pos) for pos in candidate_positions],
                dtype=float,
            )
            if np.any(keyword_scores):
                base_scores += keyword_scores * 0.15
                applied_signals.append("keyword_boost")

        if user_id is not None:
            collaborative_scores = np.array(
                [
                    np.clip(
                        self.get_collaborative_score(
                            user_id, safe_int(self.movies_df.iloc[position]["id"])
                        )
                        / 10,
                        0.0,
                        1.0,
                    )
                    for position in candidate_positions
                ],
                dtype=float,
            )
            if np.any(collaborative_scores):
                base_scores += collaborative_scores * 0.14
                applied_signals.append("collaborative")

        for idx, position in enumerate(candidate_positions):
            row = self.movies_df.iloc[position]
            quality_scores[idx] = self._get_quality_score(row)
            popularity_scores[idx] = self._get_popularity_score(row)

        base_scores += quality_scores * 0.10
        base_scores += popularity_scores * 0.04

        # Recency boost: movies from the past 2-3 years get a significant boost
        # Exponential decay: boost = 1 + amplitude * exp(-age_years / half_life)
        # Half-life=1.5yr → movies <1yr get ~1.18x, 2yr ~1.07x, 5yr ~1.0x
        try:
            release_dates = pd.to_datetime(
                self.movies_df.iloc[candidate_positions]["release_date"], errors="coerce"
            )
            now = pd.Timestamp.now()
            age_years = (now - release_dates).dt.total_seconds() / (365.25 * 86400)
            age_years = age_years.fillna(20.0).clip(lower=0).values
            recency_boost = 0.20 * np.exp(-age_years / 1.5)
            base_scores += recency_boost
            applied_signals.append("recency_boost")
        except Exception:
            pass  # graceful degradation

        if not applied_signals or (base_scores.size > 0 and float(base_scores.max()) <= 0.0):
            trending = self.get_trending(limit)
            response = {
                "query_movie": query,
                "query_user": str(user_id) if user_id is not None else None,
                "recommendation_type": "discover",
                "total_results": len(trending),
                "applied_signals": ["trending_fallback"],
                "recommendations": trending,
            }
            self.cache.set(cache_key, response)
            return response

        candidate_pool_size = min(candidate_count, max(limit * 12, 60))
        ranked_positions = np.argsort(base_scores)[::-1][:candidate_pool_size]
        top_candidate_indices = [int(candidate_positions[position]) for position in ranked_positions]
        top_base_scores = base_scores[ranked_positions]
        top_payloads: List[Dict[str, Any]] = []

        for position, movie_idx in zip(ranked_positions, top_candidate_indices):
            row = self.movies_df.iloc[movie_idx]
            movie = self._movie_to_dict(row)

            semantic_component = max(
                float(query_scores_scaled[position]), float(semantic_scores[position])
            )
            profile_component = max(
                float(profile_scores_scaled[position]),
                float(metadata_scores_scaled[position]),
            )
            collaborative_component = float(collaborative_scores[position])
            hybrid_component = float(base_scores[position])

            movie.update(
                {
                    "content_score": round(float(query_scores_scaled[position]) * 100, 1),
                    "semantic_score": round(semantic_component * 100, 1),
                    "profile_score": round(profile_component * 100, 1),
                    "collaborative_score": round(collaborative_component * 100, 1),
                    "quality_score": round(float(quality_scores[position]) * 100, 1),
                    "popularity_score": round(float(popularity_scores[position]) * 100, 1),
                    "hybrid_score": round(hybrid_component * 100, 1),
                    "reason": self._generate_discovery_reason(
                        row,
                        query_context,
                        profile,
                        semantic_component,
                        profile_component,
                        collaborative_component,
                    ),
                }
            )
            top_payloads.append(movie)

        diversified_recommendations = self._diversify_candidates(
            candidate_indices=top_candidate_indices,
            candidate_payloads=top_payloads,
            base_scores=top_base_scores,
            limit=limit,
            diversity_factor=diversity_factor,
        )

        response = {
            "query_movie": query or (liked_titles[0] if liked_titles else None),
            "query_user": str(user_id) if user_id is not None else None,
            "recommendation_type": "discover",
            "total_results": len(diversified_recommendations),
            "applied_signals": list(dict.fromkeys(applied_signals)),
            "recommendations": diversified_recommendations,
        }
        self.cache.set(cache_key, response)
        return response

    def get_trending(self, limit: int = 10) -> List[Dict]:
        """Get trending/popular movies using IMDB weighted rating formula."""
        if self.movies_df is None or self.movies_df.empty:
            return []

        cache_key = f"trending_{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        df = self.movies_df.copy()

        # IMDB weighted rating formula
        m = df["vote_count"].quantile(0.70)  # Minimum votes required
        C = df["vote_average"].mean()  # Mean vote across all movies

        qualified = df[df["vote_count"] >= m].copy()
        qualified["weighted_rating"] = (
            qualified["vote_count"] / (qualified["vote_count"] + m)
        ) * qualified["vote_average"] + (m / (qualified["vote_count"] + m)) * C

        top_movies = qualified.nlargest(limit, "weighted_rating")

        results = []
        for _, row in top_movies.iterrows():
            movie = self._movie_to_dict(row)
            movie["weighted_rating"] = round(float(row["weighted_rating"]), 2)
            movie["content_score"] = 0
            movie["collaborative_score"] = 0
            movie["hybrid_score"] = round(row["weighted_rating"] * 10, 1)
            movie["reason"] = f"Popular with {int(row['vote_count']):,} votes"
            results.append(movie)

        self.cache.set(cache_key, results)
        return results

    def get_latest(self, limit: int = 10) -> List[Dict]:
        """Get latest releases sorted by release date."""
        if self.movies_df is None or self.movies_df.empty:
            return []

        df = self.movies_df.copy()
        df = df[df["release_date"].notna() & (df["release_date"] != "")]
        df = df[df["release_date"] >= "2024-01-01"]
        latest_movies = df.sort_values(by=["release_date", "vote_average"], ascending=[False, False]).head(limit)

        results = []
        for _, row in latest_movies.iterrows():
            movie = self._movie_to_dict(row)
            movie["content_score"] = 0
            movie["collaborative_score"] = 0
            movie["hybrid_score"] = 0
            movie["reason"] = f"Released on {row['release_date']}"
            results.append(movie)

        return results

    def search_movies(
        self,
        query: Optional[str] = None,
        genre: Optional[str] = None,
        director: Optional[str] = None,
        actor: Optional[str] = None,
        min_rating: float = 0,
        max_rating: float = 10,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        sort_by: str = "vote_average",
        sort_order: str = "desc",
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Dict], int]:
        """Search movies with multiple filters and language-aware query parsing."""
        if self.movies_df is None or self.movies_df.empty:
            return [], 0

        mask = np.ones(len(self.movies_df), dtype=bool)

        if query:
            # Use language-aware query parsing to extract language and clean query
            query_context = self._build_query_context(query)

            # Apply language filter if detected
            if query_context.get("language"):
                lang_code = query_context["language"]
                lang_mask = self.movies_df["original_language"].astype(str).str.strip().str.lower() == lang_code
                if lang_mask.any():
                    mask &= lang_mask

            # Apply genre filter when genres are detected from aliases or direct match
            if query_context.get("genres"):
                genre_mask = np.zeros(len(self.movies_df), dtype=bool)
                for g in query_context["genres"]:
                    genre_mask |= self.movies_df["genres_normalized"].str.contains(g, na=False, regex=False)
                if genre_mask.any():
                    mask &= genre_mask

            # Search across title, genres, overview, keywords, director, cast
            search_term = query_context.get("normalized_query", query).casefold()
            search_words = search_term.split()
            if search_words:
                # Match any word in title OR genres OR overview
                word_mask = np.zeros(len(self.movies_df), dtype=bool)
                for word in search_words:
                    if len(word) < 2:
                        continue
                    word_mask |= self.movies_df["title_normalized"].str.contains(word, na=False, regex=False)
                    word_mask |= self.movies_df["genres_normalized"].str.contains(word, na=False, regex=False)
                    if "overview" in self.movies_df.columns:
                        word_mask |= self.movies_df["overview"].astype(str).str.lower().str.contains(word, na=False, regex=False)
                mask &= word_mask

        if genre:
            mask &= self.movies_df["genres_normalized"].str.contains(
                genre.casefold(), na=False, regex=False
            )
        if director:
            mask &= self.movies_df["director_normalized"].str.contains(
                director.casefold(), na=False, regex=False
            )
        if actor:
            mask &= self.movies_df["cast_normalized"].str.contains(
                actor.casefold(), na=False, regex=False
            )

        mask &= (self.movies_df["vote_average"] >= min_rating) & (
            self.movies_df["vote_average"] <= max_rating
        )

        if year_from is not None or year_to is not None:
            release_years = pd.to_numeric(
                self.movies_df["release_date"].str[:4], errors="coerce"
            )
            if year_from is not None:
                mask &= release_years >= year_from
            if year_to is not None:
                mask &= release_years <= year_to

        filtered_df = self.movies_df[mask]
        total = len(filtered_df)

        # Sort: when sorting by vote_average, use Bayesian weighted rating
        # to prevent 10.0-rated movies with 1 vote from dominating
        allowed_sort = {"vote_average", "release_date", "title", "vote_count"}
        sort_col = sort_by if sort_by in allowed_sort else "vote_average"
        ascending = sort_order.lower() == "asc"

        if sort_col == "vote_average" and not ascending:
            # Bayesian weighted rating: (v/(v+m))*R + (m/(v+m))*C
            m, C = 300, 6.5
            vc = filtered_df["vote_count"].fillna(0).astype(float)
            va = filtered_df["vote_average"].fillna(0).astype(float)
            weighted = (vc / (vc + m)) * va + (m / (vc + m)) * C

            # Add recency boost: recent movies (past 2-3 years) get priority
            try:
                release_dates = pd.to_datetime(filtered_df["release_date"], errors="coerce")
                now = pd.Timestamp.now()
                age_years = (now - release_dates).dt.total_seconds() / (365.25 * 86400)
                age_years = age_years.fillna(20.0).clip(lower=0)
                recency_boost = 1.5 * np.exp(-age_years / 1.5)  # +1.5 points for brand new
                weighted = weighted + recency_boost
            except Exception:
                pass

            sort_indices = weighted.argsort()[::-1]
            paged_df = filtered_df.iloc[sort_indices[offset : offset + limit]]
        else:
            paged_df = filtered_df.sort_values(sort_col, ascending=ascending, na_position="last").iloc[
                offset : offset + limit
            ]

        results = [self._movie_to_dict(row) for _, row in paged_df.iterrows()]
        return results, total

    def get_genres(self) -> List[Dict]:
        """Return precomputed genres (Efficiency: PERFORMANCE_PROTOCOL.md)."""
        if self.movies_df is None or self.movies_df.empty or not hasattr(self, "genre_list_detailed"):
            return []
        return self.genre_list_detailed

    def get_similar_users(self, user_id: int, limit: int = 5) -> List[Dict]:
        """Find users with similar taste."""
        if self.ratings_df is None or len(self.ratings_df) == 0:
            return []

        # Get user's ratings
        user_ratings = self.ratings_df[self.ratings_df.user_id == user_id]
        if len(user_ratings) == 0:
            return []

        user_movies = set(user_ratings["movie_id"].tolist())

        # Find users who rated similar movies
        similar_users = []
        for other_id in self.ratings_df["user_id"].unique():
            if other_id == user_id:
                continue

            other_ratings = self.ratings_df[self.ratings_df.user_id == other_id]
            other_movies = set(other_ratings["movie_id"].tolist())

            # Calculate Jaccard similarity
            intersection = len(user_movies & other_movies)
            union = len(user_movies | other_movies)

            if union > 0 and intersection >= 3:
                similarity = intersection / union
                similar_users.append(
                    {
                        "user_id": int(other_id),
                        "similarity": round(similarity * 100, 1),
                        "common_movies": intersection,
                    }
                )

        # Sort by similarity
        similar_users.sort(key=lambda x: x["similarity"], reverse=True)
        return similar_users[:limit]



# Global engine instance
_engine: Optional[EnhancedRecommendationEngine] = None
_engine_lock = threading.Lock()
_engine_init_started = False
_placeholder_engine = EnhancedRecommendationEngine()


def start_engine_warmup() -> None:
    """Kick off async engine loading once per process."""
    if not settings.ENABLE_STARTUP_WARMUP:
        logger.info("Startup warmup disabled; recommendation engine will remain lazy.")
        return

    global _engine_init_started
    with _engine_lock:
        if _engine is not None or _engine_init_started:
            return
        _engine_init_started = True
        thread = threading.Thread(target=_background_init, daemon=True)
        thread.start()

def _background_init():
    """Background initialization for the recommendation engine."""
    global _engine, _engine_init_started
    logger.info("🚀 Starting background recommendation engine initialization (1.2M+ records)...")
    try:
        temp_engine = EnhancedRecommendationEngine()
        temp_engine.load_data().train()
        with _engine_lock:
            _engine = temp_engine
        logger.info("✅ Recommendation engine background initialization complete.")
    except Exception as e:
        logger.error(f"❌ Background initialization failed: {e}")
        with _engine_lock:
            _engine_init_started = False

def get_engine() -> EnhancedRecommendationEngine:
    """Get the recommendation engine. Returns a shared placeholder while loading."""
    if _engine is None:
        if settings.ENABLE_STARTUP_WARMUP:
            start_engine_warmup()
        return _placeholder_engine
    return _engine

def reset_engine():
    """Reset the global engine."""
    global _engine, _engine_init_started
    with _engine_lock:
        _engine = None
        _engine_init_started = False
