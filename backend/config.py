from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """
    Project NEBULA Configuration.
    Managed via pydantic-settings for protocol compliance (AGENTS.md Section 7.1).
    """

    # Core Application Config
    DATABASE_URL: str = Field(default="sqlite:///data/movies_recommender.db")
    APP_ENV: str = Field(default="development")
    AUTO_INIT_DB: bool = Field(default=False)
    USE_MOCK_DATA: bool = Field(default=False)
    ENABLE_STARTUP_WARMUP: bool = Field(default=True)

    # SurrealDB Configuration
    SURREALDB_URL: str = Field(default="ws://localhost:8000/rpc")
    SURREALDB_USER: str = Field(default="root")
    SURREALDB_PASS: str = Field(default="root")
    SURREALDB_NS: str = Field(default="movies")
    SURREALDB_DB: str = Field(default="recommender")

    # Cache Configuration
    REDIS_URL: str = Field(default="redis://localhost:6379")

    # Search / vector infrastructure
    ELASTICSEARCH_URL: str = Field(default="http://localhost:9200")
    QDRANT_URL: str = Field(default="http://localhost:6333")

    # API Keys
    COHERE_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    TMDB_API_KEY: Optional[str] = None

    # Security
    API_KEY_NAME: str = Field(default="access_token")
    PHD_SECRET_KEY: Optional[str] = None
    CORS_ALLOW_ORIGINS: str = Field(
        default="http://localhost:3002,http://127.0.0.1:3002"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True)

    # Project NEBULA Constants
    NEBULA_COLLECTION_NAME: str = "nebula_dna_manifold"

    # Recommendation Constants
    REC_CACHE_TTL: int = Field(default=300)
    REC_LIMIT_DEFAULT: int = Field(default=10)
    REC_CONTENT_WEIGHT_DEFAULT: float = Field(default=0.6)
    REC_DIVERSITY_FACTOR_DEFAULT: float = Field(default=0.2)
    REC_SIMILARITY_THRESHOLD: float = Field(default=0.4)

    # Static Weights
    REC_QUALITY_WEIGHT: float = 0.2
    REC_COLLAB_WEIGHT: float = 0.3
    REC_POPULARITY_WEIGHT: float = 0.05
    REC_DIRECTOR_BONUS: float = 0.2

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


# Singleton instance
settings = Settings()

# Legacy compatibility exports (to minimize impact on existing code)
DATABASE_URL = settings.DATABASE_URL
APP_ENV = settings.APP_ENV
AUTO_INIT_DB = settings.AUTO_INIT_DB
USE_MOCK_DATA = settings.USE_MOCK_DATA
ENABLE_STARTUP_WARMUP = settings.ENABLE_STARTUP_WARMUP
SURREALDB_URL = settings.SURREALDB_URL
SURREALDB_USER = settings.SURREALDB_USER
SURREALDB_PASS = settings.SURREALDB_PASS
SURREALDB_NS = settings.SURREALDB_NS
SURREALDB_DB = settings.SURREALDB_DB
REDIS_URL = settings.REDIS_URL
ELASTICSEARCH_URL = settings.ELASTICSEARCH_URL
QDRANT_URL = settings.QDRANT_URL
COHERE_API_KEY = settings.COHERE_API_KEY
GROQ_API_KEY = settings.GROQ_API_KEY
GEMINI_API_KEY = settings.GEMINI_API_KEY
TMDB_API_KEY = settings.TMDB_API_KEY
API_KEY_NAME = settings.API_KEY_NAME
PHD_SECRET_KEY = settings.PHD_SECRET_KEY
CORS_ALLOW_ORIGINS = settings.CORS_ALLOW_ORIGINS
CORS_ALLOW_CREDENTIALS = settings.CORS_ALLOW_CREDENTIALS
NEBULA_COLLECTION_NAME = settings.NEBULA_COLLECTION_NAME
REC_CACHE_TTL = settings.REC_CACHE_TTL
REC_LIMIT_DEFAULT = settings.REC_LIMIT_DEFAULT
REC_CONTENT_WEIGHT_DEFAULT = settings.REC_CONTENT_WEIGHT_DEFAULT
REC_DIVERSITY_FACTOR_DEFAULT = settings.REC_DIVERSITY_FACTOR_DEFAULT
REC_SIMILARITY_THRESHOLD = settings.REC_SIMILARITY_THRESHOLD
REC_QUALITY_WEIGHT = settings.REC_QUALITY_WEIGHT
REC_COLLAB_WEIGHT = settings.REC_COLLAB_WEIGHT
REC_POPULARITY_WEIGHT = settings.REC_POPULARITY_WEIGHT
REC_DIRECTOR_BONUS = settings.REC_DIRECTOR_BONUS
