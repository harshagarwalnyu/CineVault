"""
Database Schema and Setup for Movie Recommender
================================================
Creates database schema for movies, users, ratings, and watch history.
Supports both SQLite (local) and PostgreSQL (production).

SOTA 2026: Uses SQLModel engine/session (backed by SQLAlchemy 2.0 internally).
"""

from pathlib import Path
import base64
import hashlib
import hmac
import os
from collections.abc import Generator

import pandas as pd
from sqlmodel import Session, create_engine, text
from sqlalchemy import inspect

from backend.config import settings, DATABASE_URL

_engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs.update(
        {
            "pool_size": 20,
            "max_overflow": 10,
            "pool_timeout": 30,
            "pool_recycle": 1800,
        }
    )

# Create Engine with settings that fit the active database backend.
engine = create_engine(DATABASE_URL, **_engine_kwargs)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a SQLModel Session per request."""
    with Session(engine) as session:
        yield session


def hash_password(password: str, iterations: int = 200_000) -> str:
    """Create a PBKDF2-SHA256 password hash for stored credentials."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("utf-8")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("utf-8")
    return f"pbkdf2_sha256${iterations}${salt_b64}${digest_b64}"


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify a PBKDF2-SHA256 password hash."""
    if not password or not password_hash:
        return False

    try:
        algorithm, iterations_raw, salt_b64, expected_b64 = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False

        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_b64.encode("utf-8"))
        expected = base64.urlsafe_b64decode(expected_b64.encode("utf-8"))
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(candidate, expected)
    except (TypeError, ValueError):
        return False


def authenticate_user(username: str, password: str) -> dict | None:
    """Authenticate a user against the local users table."""
    if not username or not password:
        return None

    with engine.connect() as conn:
        user = (
            conn.execute(
                text(
                    """
                SELECT id, username, email, password_hash
                FROM users
                WHERE username = :username
                """
                ),
                {"username": username},
            )
            .mappings()
            .first()
        )

    if not user or not verify_password(password, user.get("password_hash")):
        return None

    return {
        "id": int(user["id"]),
        "username": str(user["username"]),
        "email": user.get("email"),
    }


def touch_user_last_login(user_id: int) -> None:
    """Persist the last successful login timestamp."""
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = :user_id"),
            {"user_id": user_id},
        )
        conn.commit()


def get_connection():
    """Get a raw database connection (legacy support)."""
    # Force check settings for override
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        import sqlite3

        db_path = url.replace("sqlite:///", "")
        return sqlite3.connect(db_path)
    else:
        print(f"DEBUG: get_connection falling back to Postgres with URL: {url}")
        return engine.raw_connection()


def execute_sql(sql: str, params: dict | None = None):
    """Execute raw SQL safely across DB types."""
    with engine.connect() as conn:
        if params:
            result = conn.execute(text(sql), params)
        else:
            result = conn.execute(text(sql))
        conn.commit()
        return result


def create_tables() -> None:
    """Create all database tables using raw SQL for simplicity/portability."""

    # Check if tables exist
    inspector = inspect(engine)
    if inspector.has_table("movies"):
        print("✓ Tables already exist")
        return

    print(f"Creating tables in {DATABASE_URL}...")

    # Schema definitions (Postgres/SQLite compatible)
    is_postgres = "postgresql" in DATABASE_URL

    pk_type = (
        "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    )

    commands = [
        """
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY, -- Using explicit ID from dataset
            title TEXT NOT NULL,
            genres TEXT,
            keywords TEXT,
            tagline TEXT,
            overview TEXT,
            "cast" TEXT,
            director TEXT,
            vote_average REAL DEFAULT 0,
            vote_count INTEGER DEFAULT 0,
            imdb_rating REAL,
            imdb_votes INTEGER,
            rt_critic_score INTEGER,
            rt_audience_score INTEGER,
            reddit_sentiment REAL,
            popularity_score REAL DEFAULT 0,
            budget BIGINT DEFAULT 0,
            revenue BIGINT DEFAULT 0,
            runtime INTEGER,
            original_language TEXT,
            release_date TEXT,
            poster_path TEXT,
            backdrop_path TEXT,
            tmdb_id INTEGER,
            imdb_id TEXT UNIQUE,
            homepage TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS users (
            id {pk_type},
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS ratings (
            id {pk_type},
            user_id INTEGER NOT NULL,
            movie_id INTEGER NOT NULL,
            rating REAL NOT NULL CHECK(rating >= 0 AND rating <= 10),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (movie_id) REFERENCES movies(id),
            UNIQUE(user_id, movie_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS watch_history (
            id {pk_type},
            user_id INTEGER NOT NULL,
            movie_id INTEGER NOT NULL,
            watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            watch_duration_minutes INTEGER,
            completed BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (movie_id) REFERENCES movies(id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS user_favorites (
            id {pk_type},
            user_id INTEGER NOT NULL,
            movie_id INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (movie_id) REFERENCES movies(id),
            UNIQUE(user_id, movie_id)
        )
        """,
    ]

    with engine.connect() as conn:
        for sql in commands:
            conn.execute(text(sql))

        # Performance Indices (PERFORMANCE_PROTOCOL.md)
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_movies_title ON movies(title)")
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_movies_popularity ON movies(popularity_score)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_movies_vote_avg ON movies(vote_average)"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_movies_imdb_id ON movies(imdb_id)")
        )

        try:
            conn.execute(text("CREATE INDEX idx_movies_genres ON movies(genres)"))
        except Exception as e:
            print(f"Note: Could not create genres index (expected in some DBs): {e}")

        conn.commit()

    print("✓ Database tables created successfully")


def import_csv_to_db(csv_path: str = "data/movies.csv") -> bool:
    """Import movies from CSV file to database."""
    path = Path(csv_path)
    if not path.exists():
        print(f"✗ CSV file not found: {csv_path}")
        return False

    print(f"Importing movies from {csv_path}...")
    df = pd.read_csv(csv_path)

    # Clean data to match schema
    df = df.rename(columns={"id": "id"})  # Ensure ID column matches

    # Select only columns that exist in our schema
    expected_cols = [
        "id",
        "title",
        "genres",
        "keywords",
        "tagline",
        "cast",
        "director",
        "vote_average",
        "vote_count",
        "budget",
        "homepage",
        "overview",
        "release_date",
        "runtime",
    ]

    # Filter df to available columns
    available_cols = [c for c in expected_cols if c in df.columns]
    df_import = df[available_cols].copy()

    # Fill NaNs
    df_import = df_import.fillna(
        {"vote_average": 0, "vote_count": 0, "budget": 0, "runtime": 0}
    )

    # Write to DB
    try:
        # Check existing IDs to avoid duplicates
        with engine.connect() as conn:
            existing = pd.read_sql("SELECT id FROM movies", conn)
            existing_ids = set(existing["id"].tolist())

        df_new = df_import[~df_import["id"].isin(existing_ids)]

        if len(df_new) > 0:
            df_new.to_sql("movies", engine, if_exists="append", index=False)
            print(f"✓ Imported {len(df_new)} new movies")
        else:
            print("✓ No new movies to import")

    except Exception as e:
        print(f"Warning during import: {e}")
        return False

    return True


def create_sample_users(n_users: int = 100) -> None:
    """Create or normalize sample users for testing."""
    with engine.connect() as conn:
        for i in range(n_users):
            try:
                username = f"user_{i + 1}"
                email = f"user{i + 1}@example.com"
                password_hash = hash_password(f"sample-user-{i + 1}")

                # Upsert syntax varies by DB, so we use a simple check-insert
                exists = conn.execute(
                    text("SELECT id FROM users WHERE username = :u"), {"u": username}
                ).fetchone()
                if exists:
                    conn.execute(
                        text(
                            """
                            UPDATE users
                            SET email = :e, password_hash = :p
                            WHERE username = :u
                            """
                        ),
                        {"u": username, "e": email, "p": password_hash},
                    )
                else:
                    conn.execute(
                        text("""
                        INSERT INTO users (username, email, password_hash)
                        VALUES (:u, :e, :p)
                    """),
                        {"u": username, "e": email, "p": password_hash},
                    )
            except Exception as e:
                print(f"Error creating user {username}: {e}")
        conn.commit()
    print("✓ Users check/create complete")


def generate_sample_ratings(ratings_per_user: int = 30) -> None:
    """Generate sample ratings for collaborative filtering."""
    import random  # Used for non-cryptographic sampling

    with engine.connect() as conn:
        # Get user IDs
        users = conn.execute(text("SELECT id FROM users")).fetchall()
        user_ids = [u[0] for u in users]

        # Get movie IDs
        movies = conn.execute(text("SELECT id, vote_average FROM movies")).fetchall()

        if not user_ids or not movies:
            return

        movie_data = {m[0]: m[1] for m in movies}
        movie_ids = list(movie_data.keys())

        # Generate ratings — prepare batch insert for performance
        ratings_data: list[dict] = []

        existing_ratings: set[tuple[int, int]] = set()
        rows = conn.execute(text("SELECT user_id, movie_id FROM ratings")).fetchall()
        for r in rows:
            existing_ratings.add((r[0], r[1]))

        for user_id in user_ids:
            # Rate random subset
            targets = random.sample(movie_ids, min(ratings_per_user, len(movie_ids)))

            for movie_id in targets:
                if (user_id, movie_id) in existing_ratings:
                    continue

                base_rating = movie_data.get(movie_id, 5.0) or 5.0
                rating = max(1, min(10, base_rating + random.uniform(-2, 2)))
                ratings_data.append(
                    {"u": user_id, "m": movie_id, "r": round(rating, 1)}
                )

        if ratings_data:
            print(f"Inserting {len(ratings_data)} ratings...")
            # Batch insert
            conn.execute(
                text("""
                INSERT INTO ratings (user_id, movie_id, rating)
                VALUES (:u, :m, :r)
            """),
                ratings_data,
            )
            conn.commit()
            print("✓ Ratings generated")


def get_stats() -> dict[str, int]:
    """Get database statistics."""
    stats: dict[str, int] = {}
    with engine.connect() as conn:
        stats["movies"] = (
            conn.execute(text("SELECT COUNT(*) FROM movies")).scalar() or 0
        )
        stats["users"] = conn.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
        stats["ratings"] = (
            conn.execute(text("SELECT COUNT(*) FROM ratings")).scalar() or 0
        )
    return stats


def initialize_database(include_mock_data: bool | None = None) -> None:
    """Full database initialization with optional mock data seeding."""
    print(f"Initializing database: {DATABASE_URL}")
    create_tables()
    import_csv_to_db()

    should_seed_mock_data = (
        settings.USE_MOCK_DATA if include_mock_data is None else include_mock_data
    )
    if should_seed_mock_data:
        create_sample_users()
        generate_sample_ratings()
    else:
        print("Skipping mock user/rating generation (USE_MOCK_DATA=false)")

    stats = get_stats()
    print("DB Stats:", stats)


if __name__ == "__main__":
    initialize_database()
