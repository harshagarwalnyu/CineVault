"""MovieLens 32M dataset expansion — new tables and movie metadata columns

Revision ID: 20260405_0002
Revises: 20260329_0001
Create Date: 2026-04-05
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260405_0002"
down_revision = "20260329_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- New tables for MovieLens data ---

    op.create_table(
        "movie_id_mapping",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ml_movie_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("imdb_id", sa.Text(), nullable=True),
        sa.Column(
            "internal_movie_id",
            sa.Integer(),
            sa.ForeignKey("movies.id"),
            nullable=True,
        ),
    )

    op.create_table(
        "ml_ratings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ml_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "movie_id", sa.Integer(), sa.ForeignKey("movies.id"), nullable=True
        ),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=True),
    )

    op.create_table(
        "ml_tags",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ml_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "movie_id", sa.Integer(), sa.ForeignKey("movies.id"), nullable=True
        ),
        sa.Column("tag", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=True),
    )

    # --- Indexes for ml_ratings ---
    op.create_index("idx_ml_ratings_ml_user_id", "ml_ratings", ["ml_user_id"])
    op.create_index("idx_ml_ratings_movie_id", "ml_ratings", ["movie_id"])
    op.create_index(
        "idx_ml_ratings_user_movie",
        "ml_ratings",
        ["ml_user_id", "movie_id"],
    )

    # --- Indexes for ml_tags ---
    op.create_index("idx_ml_tags_movie_id", "ml_tags", ["movie_id"])

    # --- New columns on movies for enriched metadata ---
    op.add_column("movies", sa.Column("metacritic_score", sa.Integer(), nullable=True))
    op.add_column(
        "movies", sa.Column("box_office_worldwide", sa.BigInteger(), nullable=True)
    )
    op.add_column("movies", sa.Column("awards_text", sa.Text(), nullable=True))
    op.add_column(
        "movies", sa.Column("trailer_youtube_key", sa.String(), nullable=True)
    )
    op.add_column(
        "movies", sa.Column("streaming_providers", sa.Text(), nullable=True)
    )
    op.add_column("movies", sa.Column("certification", sa.String(), nullable=True))


def downgrade() -> None:
    # --- Drop new columns from movies ---
    op.drop_column("movies", "certification")
    op.drop_column("movies", "streaming_providers")
    op.drop_column("movies", "trailer_youtube_key")
    op.drop_column("movies", "awards_text")
    op.drop_column("movies", "box_office_worldwide")
    op.drop_column("movies", "metacritic_score")

    # --- Drop indexes ---
    op.drop_index("idx_ml_tags_movie_id", table_name="ml_tags")
    op.drop_index("idx_ml_ratings_user_movie", table_name="ml_ratings")
    op.drop_index("idx_ml_ratings_movie_id", table_name="ml_ratings")
    op.drop_index("idx_ml_ratings_ml_user_id", table_name="ml_ratings")

    # --- Drop new tables ---
    op.drop_table("ml_tags")
    op.drop_table("ml_ratings")
    op.drop_table("movie_id_mapping")
