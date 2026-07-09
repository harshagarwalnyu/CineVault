"""Initial schema for movies recommender

Revision ID: 20260329_0001
Revises:
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260329_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "movies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("genres", sa.String(), nullable=True),
        sa.Column("keywords", sa.Text(), nullable=True),
        sa.Column("tagline", sa.Text(), nullable=True),
        sa.Column("overview", sa.Text(), nullable=True),
        sa.Column("cast", sa.Text(), nullable=True),
        sa.Column("director", sa.String(), nullable=True),
        sa.Column("vote_average", sa.Float(), nullable=True, server_default="0"),
        sa.Column("vote_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("imdb_rating", sa.Float(), nullable=True),
        sa.Column("imdb_votes", sa.Integer(), nullable=True),
        sa.Column("rt_critic_score", sa.Integer(), nullable=True),
        sa.Column("rt_audience_score", sa.Integer(), nullable=True),
        sa.Column("reddit_sentiment", sa.Float(), nullable=True),
        sa.Column("popularity_score", sa.Float(), nullable=True, server_default="0"),
        sa.Column("budget", sa.BigInteger(), nullable=True, server_default="0"),
        sa.Column("revenue", sa.BigInteger(), nullable=True, server_default="0"),
        sa.Column("runtime", sa.Integer(), nullable=True),
        sa.Column("original_language", sa.String(), nullable=True),
        sa.Column("release_date", sa.String(), nullable=True),
        sa.Column("poster_path", sa.String(), nullable=True),
        sa.Column("backdrop_path", sa.String(), nullable=True),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("imdb_id", sa.String(), nullable=True),
        sa.Column("homepage", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("imdb_id", name="uq_movies_imdb_id"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("last_login", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "ratings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movies.id"), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.CheckConstraint("rating >= 0 AND rating <= 10", name="ck_ratings_range"),
        sa.UniqueConstraint("user_id", "movie_id", name="uq_ratings_user_movie"),
    )

    op.create_table(
        "watch_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movies.id"), nullable=False),
        sa.Column("watched_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("watch_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=True, server_default=sa.false()),
    )

    op.create_table(
        "user_favorites",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movies.id"), nullable=False),
        sa.Column("added_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "movie_id", name="uq_user_favorites_user_movie"),
    )

    op.create_index("idx_movies_title", "movies", ["title"])
    op.create_index("idx_movies_popularity", "movies", ["popularity_score"])
    op.create_index("idx_movies_vote_avg", "movies", ["vote_average"])
    op.create_index("idx_movies_imdb_id", "movies", ["imdb_id"])


def downgrade() -> None:
    op.drop_index("idx_movies_imdb_id", table_name="movies")
    op.drop_index("idx_movies_vote_avg", table_name="movies")
    op.drop_index("idx_movies_popularity", table_name="movies")
    op.drop_index("idx_movies_title", table_name="movies")

    op.drop_table("user_favorites")
    op.drop_table("watch_history")
    op.drop_table("ratings")
    op.drop_table("users")
    op.drop_table("movies")
