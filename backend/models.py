"""
SQLModel ORM Models for Movie Recommender
==========================================
Unified SQLModel classes that serve as both database ORM models AND
Pydantic validation schemas. Eliminates the dual models.py/schemas.py pattern.

SOTA 2026: SQLModel fuses SQLAlchemy 2.0 + Pydantic v2 into a single class.
"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy import Column, DateTime, BigInteger, Text, UniqueConstraint
from sqlalchemy.sql import func


class Movie(SQLModel, table=True):
    """Movie entity — primary content table."""

    __tablename__ = "movies"

    id: int = Field(primary_key=True)
    title: str = Field(index=True)
    genres: Optional[str] = Field(default=None)
    keywords: Optional[str] = Field(default=None, sa_column=Column(Text))
    tagline: Optional[str] = Field(default=None, sa_column=Column(Text))
    overview: Optional[str] = Field(default=None, sa_column=Column(Text))
    cast: Optional[str] = Field(default=None, sa_column=Column(Text))
    director: Optional[str] = Field(default=None)
    vote_average: float = Field(default=0)
    vote_count: int = Field(default=0)
    imdb_rating: Optional[float] = Field(default=None)
    imdb_votes: Optional[int] = Field(default=None)
    rt_critic_score: Optional[int] = Field(default=None)
    rt_audience_score: Optional[int] = Field(default=None)
    reddit_sentiment: Optional[float] = Field(default=None)
    popularity_score: float = Field(default=0, index=True)
    budget: Optional[int] = Field(default=0, sa_column=Column(BigInteger, default=0))
    revenue: Optional[int] = Field(default=0, sa_column=Column(BigInteger, default=0))
    runtime: Optional[int] = Field(default=None)
    original_language: Optional[str] = Field(default=None)
    release_date: Optional[str] = Field(default=None)
    poster_path: Optional[str] = Field(default=None)
    backdrop_path: Optional[str] = Field(default=None)
    tmdb_id: Optional[int] = Field(default=None)
    imdb_id: Optional[str] = Field(default=None, unique=True, index=True)
    homepage: Optional[str] = Field(default=None)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )

    # Relationships
    ratings: list["Rating"] = Relationship(back_populates="movie")
    watch_history: list["WatchHistory"] = Relationship(back_populates="movie")
    user_favorites: list["UserFavorite"] = Relationship(back_populates="movie")

    def __repr__(self) -> str:
        return f"<Movie(id={self.id}, title='{self.title}')>"


class User(SQLModel, table=True):
    """User entity — authentication and profile."""

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: Optional[str] = Field(default=None, unique=True)
    password_hash: Optional[str] = Field(default=None)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    last_login: Optional[datetime] = Field(default=None)

    # Relationships
    ratings: list["Rating"] = Relationship(back_populates="user")
    watch_history: list["WatchHistory"] = Relationship(back_populates="user")
    user_favorites: list["UserFavorite"] = Relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}')>"


class Rating(SQLModel, table=True):
    """User rating for a movie (1-10 scale)."""

    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("user_id", "movie_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    movie_id: int = Field(foreign_key="movies.id", index=True)
    rating: float = Field(ge=0, le=10)
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now(), onupdate=func.now()),
    )

    user: Optional["User"] = Relationship(back_populates="ratings")
    movie: Optional["Movie"] = Relationship(back_populates="ratings")

    def __repr__(self) -> str:
        return f"<Rating(user_id={self.user_id}, movie_id={self.movie_id}, rating={self.rating})>"


class WatchHistory(SQLModel, table=True):
    """Tracks which movies a user has watched."""

    __tablename__ = "watch_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    movie_id: int = Field(foreign_key="movies.id", index=True)
    watched_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )
    watch_duration_minutes: Optional[int] = Field(default=None)
    completed: bool = Field(default=False)

    user: Optional["User"] = Relationship(back_populates="watch_history")
    movie: Optional["Movie"] = Relationship(back_populates="watch_history")

    def __repr__(self) -> str:
        return f"<WatchHistory(user_id={self.user_id}, movie_id={self.movie_id})>"


class UserFavorite(SQLModel, table=True):
    """User's favorite movies."""

    __tablename__ = "user_favorites"
    __table_args__ = (UniqueConstraint("user_id", "movie_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    movie_id: int = Field(foreign_key="movies.id", index=True)
    added_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, server_default=func.now()),
    )

    user: Optional["User"] = Relationship(back_populates="user_favorites")
    movie: Optional["Movie"] = Relationship(back_populates="user_favorites")

    def __repr__(self) -> str:
        return f"<UserFavorite(user_id={self.user_id}, movie_id={self.movie_id})>"
