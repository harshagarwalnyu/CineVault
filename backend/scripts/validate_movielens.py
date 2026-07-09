"""
Validate MovieLens 32M ingestion
=================================
Reports row counts, matched-movie ratio, rating distribution,
and tag statistics to verify a successful ingest.

Usage:
    python -m backend.scripts.validate_movielens
"""

import logging

from sqlalchemy import text

from backend.database import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def count_table(conn, table: str) -> int:
    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
    return result.scalar() or 0


def validate() -> None:
    log.info("=== MovieLens Validation Report ===\n")

    with engine.connect() as conn:
        # --- Row counts ---
        n_movies = count_table(conn, "movies")
        n_ml_ratings = count_table(conn, "ml_ratings")
        n_ml_tags = count_table(conn, "ml_tags")
        n_mappings = count_table(conn, "movie_id_mapping")

        log.info("Row counts:")
        log.info("  movies:           %d", n_movies)
        log.info("  ml_ratings:       %d", n_ml_ratings)
        log.info("  ml_tags:          %d", n_ml_tags)
        log.info("  movie_id_mapping: %d", n_mappings)

        # --- Matched movies ---
        matched = (
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM movie_id_mapping "
                    "WHERE internal_movie_id IS NOT NULL"
                )
            ).scalar()
            or 0
        )
        unmatched = n_mappings - matched
        pct = (matched / n_mappings * 100) if n_mappings else 0.0

        log.info("\nID mapping:")
        log.info(
            "  Matched to internal movies: %d / %d (%.1f%%)", matched, n_mappings, pct
        )
        log.info("  Unmatched:                  %d", unmatched)

        # --- Ratings with valid movie_id ---
        ratings_matched = (
            conn.execute(
                text("SELECT COUNT(*) FROM ml_ratings WHERE movie_id IS NOT NULL")
            ).scalar()
            or 0
        )
        ratings_orphan = n_ml_ratings - ratings_matched
        log.info("\nRatings coverage:")
        log.info("  With internal movie_id: %d", ratings_matched)
        log.info("  Orphaned (no match):    %d", ratings_orphan)

        # --- Distinct users ---
        distinct_users = (
            conn.execute(
                text("SELECT COUNT(DISTINCT ml_user_id) FROM ml_ratings")
            ).scalar()
            or 0
        )
        log.info("\nDistinct ML users: %d", distinct_users)

        # --- Rating distribution ---
        log.info("\nRating distribution:")
        dist_rows = conn.execute(
            text(
                "SELECT rating, COUNT(*) AS cnt "
                "FROM ml_ratings "
                "GROUP BY rating "
                "ORDER BY rating"
            )
        ).fetchall()
        for row in dist_rows:
            bar_len = (
                int(row[1] / max(r[1] for r in dist_rows) * 40) if dist_rows else 0
            )
            bar = "#" * bar_len
            log.info("  %.1f: %8d  %s", row[0], row[1], bar)

        # --- Tag stats ---
        distinct_tags = (
            conn.execute(text("SELECT COUNT(DISTINCT tag) FROM ml_tags")).scalar() or 0
        )
        log.info("\nTag stats:")
        log.info("  Total tag applications: %d", n_ml_tags)
        log.info("  Distinct tags:          %d", distinct_tags)

        # --- Top 10 tags ---
        top_tags = conn.execute(
            text(
                "SELECT tag, COUNT(*) AS cnt "
                "FROM ml_tags "
                "GROUP BY tag "
                "ORDER BY cnt DESC "
                "LIMIT 10"
            )
        ).fetchall()
        if top_tags:
            log.info("\nTop 10 tags:")
            for row in top_tags:
                log.info("  %-30s %d", row[0], row[1])

    log.info("\n=== Validation complete ===")


def main() -> None:
    validate()


if __name__ == "__main__":
    main()
