"""
Pydantic Models for Movie Recommender API
==========================================
Data validation and serialization schemas for all API endpoints.
"""

from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ============== Enums ==============


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class RecommendationType(str, Enum):
    CONTENT = "content"
    COLLABORATIVE = "collaborative"
    HYBRID = "hybrid"
    TRENDING = "trending"
    PERSONALIZED = "personalized"
    DISCOVER = "discover"


# ============== Movie Schemas ==============


class MovieBase(BaseModel):
    title: str
    genres: Optional[str] = None
    director: Optional[str] = None
    cast: Optional[str] = None
    tagline: Optional[str] = None
    keywords: Optional[str] = None


class MovieCreate(MovieBase):
    vote_average: Optional[float] = 0
    vote_count: Optional[int] = 0


class MovieResponse(MovieBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vote_average: float = 0
    vote_count: int = 0
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    tmdb_id: Optional[int] = None
    overview: Optional[str] = None
    release_date: Optional[str] = None
    runtime: Optional[int] = None
    original_language: Optional[str] = None
    
    # cinevault Context Placeholders
    cinevault_qualities: List[str] = Field(
        default_factory=lambda: ["720p.WEB", "1080p.WEB"]
    )

    @field_validator("*", mode="before")
    @classmethod
    def convert_nan_to_none(cls, v):
        import math

        try:
            if isinstance(v, float) and math.isnan(v):
                return None
        except Exception:
            pass
        return v


class MovieDetail(MovieResponse):
    """Extended movie details with additional metadata."""

    budget: Optional[int] = None
    revenue: Optional[int] = None
    homepage: Optional[str] = None
    imdb_id: Optional[str] = None


class MovieWithScore(MovieResponse):
    """Movie with recommendation scores."""

    content_score: float = Field(
        0, description="Content-based similarity score (0-100)"
    )
    semantic_score: float = Field(0, description="Semantic retrieval score (0-100)")
    profile_score: float = Field(0, description="User taste/profile match score (0-100)")
    collaborative_score: float = Field(
        0, description="Collaborative filtering score (0-100)"
    )
    quality_score: float = Field(0, description="Quality prior score (0-100)")
    popularity_score: float = Field(0, description="Popularity prior score (0-100)")
    hybrid_score: float = Field(0, description="Combined hybrid score (0-100)")
    reason: Optional[str] = Field(None, description="Why this movie was recommended")


# ============== User Schemas ==============


class UserBase(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)


class UserCreate(UserBase):
    email: Optional[str] = None
    password: Optional[str] = None


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None


class UserLogin(BaseModel):
    username: str
    password: Optional[str] = None


class AgentInput(BaseModel):
    input: str
    chat_history: List[dict] = Field(default_factory=list)
    session_id: Optional[str] = None
    user_id: Optional[int] = None


class UserStats(BaseModel):
    """User activity statistics."""

    user_id: int
    username: str
    total_ratings: int = 0
    total_favorites: int = 0
    average_rating: float = 0
    favorite_genres: List[str] = []
    most_rated_genre: Optional[str] = None


# ============== Rating Schemas ==============


class RatingBase(BaseModel):
    movie_id: int
    rating: float = Field(..., ge=1, le=10, description="Rating from 1 to 10")


class RatingCreate(RatingBase):
    user_id: int


class RatingResponse(RatingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    movie_title: Optional[str] = None


# ============== Favorite Schemas ==============


class FavoriteCreate(BaseModel):
    user_id: int
    movie_id: int


class FavoriteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    movie_id: int
    movie_title: str
    movie_genres: Optional[str] = None
    movie_rating: float = 0
    added_at: Optional[datetime] = None


# ============== Recommendation Schemas ==============


class RecommendationRequest(BaseModel):
    """Request for movie recommendations."""

    movie_id: Optional[int] = None
    movie_title: Optional[str] = None
    user_id: Optional[int] = None
    rec_type: RecommendationType = RecommendationType.HYBRID
    limit: int = Field(10, ge=1, le=50)
    content_weight: float = Field(
        0.6, ge=0, le=1, description="Weight for content-based score"
    )
    diversity_factor: float = Field(
        0.2, ge=0, le=1, description="Penalize similar genres"
    )
    min_rating: float = Field(0, ge=0, le=10, description="Minimum movie rating")


class RecommendationResponse(BaseModel):
    """Response containing movie recommendations."""

    query_movie: Optional[str] = None
    query_user: Optional[str] = None
    recommendation_type: str
    total_results: int
    recommendations: List[MovieWithScore]
    generated_at: datetime = Field(default_factory=datetime.now)


class RecommendationListResponse(BaseModel):
    """Compact recommendation payload for endpoint responses."""

    movie: Optional[str] = None
    recommendations: List[MovieWithScore]


class DiscoveryRequest(BaseModel):
    """Advanced discovery request for natural-language movie recommendations."""

    query: Optional[str] = None
    user_id: Optional[int] = None
    liked_movie_ids: List[int] = Field(default_factory=list)
    liked_titles: List[str] = Field(default_factory=list)
    excluded_movie_ids: List[int] = Field(default_factory=list)
    limit: int = Field(10, ge=1, le=50)
    min_rating: float = Field(0, ge=0, le=10)
    diversity_factor: float = Field(
        0.25, ge=0, le=1, description="Higher values increase result diversity"
    )
    use_reranker: bool = Field(
        default=False,
        description="Apply external reranking to dense semantic candidates when available",
    )


class DiscoveryResponse(RecommendationResponse):
    """Response for the advanced discovery endpoint."""

    applied_signals: List[str] = Field(default_factory=list)


# ============== Search & Filter Schemas ==============


class MovieSearchParams(BaseModel):
    """Parameters for movie search."""

    query: Optional[str] = None
    genre: Optional[str] = None
    director: Optional[str] = None
    actor: Optional[str] = None
    min_rating: float = Field(0, ge=0, le=10)
    max_rating: float = Field(10, ge=0, le=10)
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    sort_by: str = Field("vote_average", description="Field to sort by")
    sort_order: SortOrder = SortOrder.DESC
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)


class PaginatedResponse(BaseModel):
    """Paginated list response."""

    items: List[MovieResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


# ============== Genre Schemas ==============


class GenreStats(BaseModel):
    """Genre with movie count."""

    name: str
    movie_count: int
    average_rating: float


# ============== API Response Schemas ==============


class APIResponse(BaseModel):
    """Standard API response wrapper."""

    success: bool = True
    message: str = "Success"
    data: Optional[dict] = None


class ErrorResponse(BaseModel):
    """Error response."""

    success: bool = False
    error: str
    detail: Optional[str] = None
