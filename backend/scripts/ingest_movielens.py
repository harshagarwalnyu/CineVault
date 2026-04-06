"""
Ingest MovieLens 32M dataset
=============================
Downloads the ML-32M zip, parses ratings.csv / tags.csv / links.csv,
maps MovieLens movie IDs to internal IDs via TMDB/IMDB, and batch-inserts
ratings and tags into the database.

Usage:
    python -m backend.scripts.ingest_movielens
"""

import csv
import io
import logging
import os
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

from sqlalchemy import text

from backend.config import settings
from backend.database import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

ML_32M_URL = "https://files.grouplens.org/datasets/movielens/ml-32m.zip"
ML_ZIP_NAME = "ml-32m.zip"


def ensure_data_dir() -> Path:
    """Create the movielens data directory if it doesn't exist."""
    data_dir = Path(settings.MOVIELENS_DATA_PATH)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def download_dataset(data_dir: Path) -> Path:
    """Download ML-32M zip if not already present."""
    zip_path = data_dir / ML_ZIP_NAME
    if zip_path.exists():
        log.info("Dataset zip already exists at %s — skipping download.", zip_path)
        return zip_path

    log.info("Downloading MovieLens 32M from %s ...", ML_32M_URL)
    urlretrieve(ML_32M_URL, str(zip_path))
    log.info("Download complete: %s", zip_path)
    return zip_path


def extract_csv_from_zip(zip_path: Path, csv_name: str) -> csv.DictReader:
    """Open a CSV inside the zip and return a DictReader over its rows."""
    zf = zipfile.ZipFile(zip_path, "r")
    # ML-32M zip has files under ml-32m/ prefix
    inner_path = f"ml-32m/{csv_name}"
    fp = io.TextIOWrapper(zf.open(inner_path), encoding="utf-8")
    return csv.DictReader(fp)


def ingest_links(zip_path: Path) -> dict[int, dict]:
    """Parse links.csv and return mapping: ml_movie_id -> {tmdb_id, imdb_id}."""
    log.info("Parsing links.csv ...")
    reader = extract_csv_from_zip(zip_path, "links.csv")
    mapping: dict[int, dict] = {}
    for row in reader:
        ml_id = int(row["movieId"])
        tmdb_raw = row.get("tmdbId", "").strip()
        imdb_raw = row.get("imdbId", "").strip()
        mapping[ml_id] = {
            "tmdb_id": int(tmdb_raw) if tmdb_raw else None,
            "imdb_id": f"tt{imdb_raw}" if imdb_raw else None,
        }
    log.info("Loaded %d link entries.", len(mapping))
    return mapping


def build_id_mappings(links: dict[int, dict]) -> None:
    """Populate movie_id_mapping table and resolve internal_movie_id via tmdb_id."""
    log.info("Building movie_id_mapping table ...")
    batch_size = settings.MOVIELENS_BATCH_SIZE

    with engine.begin() as conn:
        # Load existing tmdb_id -> internal id from movies table
        rows = conn.execute(
            text("SELECT id, tmdb_id FROM movies WHERE tmdb_id IS NOT NULL")
        ).fetchall()
        tmdb_to_internal: dict[int, int] = {r[1]: r[0] for r in rows}
        log.info("Found %d movies with tmdb_id in local DB.", len(tmdb_to_internal))

        # Batch insert into movie_id_mapping
        batch: list[dict] = []
        for ml_id, info in links.items():
            internal_id = tmdb_to_internal.get(info["tmdb_id"]) if info["tmdb_id"] else None
            batch.append(
                {
                    "ml_movie_id": ml_id,
                    "tmdb_id": info["tmdb_id"],
                    "imdb_id": info["imdb_id"],
                    "internal_movie_id": internal_id,
                }
            )
            if len(batch) >= batch_size:
                conn.execute(
                    text(
                        "INSERT INTO movie_id_mapping "
                        "(ml_movie_id, tmdb_id, imdb_id, internal_movie_id) "
                        "VALUES (:ml_movie_id, :tmdb_id, :imdb_id, :internal_movie_id)"
                    ),
                    batch,
                )
                batch.clear()

        if batch:
            conn.execute(
                text(
                    "INSERT INTO movie_id_mapping "
                    "(ml_movie_id, tmdb_id, imdb_id, internal_movie_id) "
                    "VALUES (:ml_movie_id, :tmdb_id, :imdb_id, :internal_movie_id)"
                ),
                batch,
            )

    matched = sum(1 for v in links.values() if tmdb_to_internal.get(v.get("tmdb_id")))
    log.info(
        "movie_id_mapping populated: %d total, %d matched to internal movies.",
        len(links),
        matched,
    )


def _load_ml_to_internal(conn) -> dict[int, int]:
    """Return ml_movie_id -> internal_movie_id for matched movies."""
    rows = conn.execute(
        text(
            "SELECT ml_movie_id, internal_movie_id "
            "FROM movie_id_mapping "
            "WHERE internal_movie_id IS NOT NULL"
        )
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def ingest_ratings(zip_path: Path) -> None:
    """Parse ratings.csv and batch-insert into ml_ratings."""
    log.info("Ingesting ratings.csv ...")
    batch_size = settings.MOVIELENS_BATCH_SIZE
    reader = extract_csv_from_zip(zip_path, "ratings.csv")

    total = 0
    with engine.begin() as conn:
        ml_to_internal = _load_ml_to_internal(conn)

        batch: list[dict] = []
        for row in reader:
            ml_movie_id = int(row["movieId"])
            internal_id = ml_to_internal.get(ml_movie_id)
            batch.append(
                {
                    "ml_user_id": int(row["userId"]),
                    "movie_id": internal_id,
                    "rating": float(row["rating"]),
                    "ts": int(row["timestamp"]),
                }
            )
            if len(batch) >= batch_size:
                conn.execute(
                    text(
                        "INSERT INTO ml_ratings "
                        "(ml_user_id, movie_id, rating, timestamp) "
                        "VALUES (:ml_user_id, :movie_id, :rating, :ts)"
                    ),
                    batch,
                )
                total += len(batch)
                if total % 500_000 == 0:
                    log.info("  ... %d ratings inserted so far", total)
                batch.clear()

        if batch:
            conn.execute(
                text(
                    "INSERT INTO ml_ratings "
                    "(ml_user_id, movie_id, rating, timestamp) "
                    "VALUES (:ml_user_id, :movie_id, :rating, :ts)"
                ),
                batch,
            )
            total += len(batch)

    log.info("Ratings ingestion complete: %d total rows.", total)


def ingest_tags(zip_path: Path) -> None:
    """Parse tags.csv and batch-insert into ml_tags."""
    log.info("Ingesting tags.csv ...")
    batch_size = settings.MOVIELENS_BATCH_SIZE
    reader = extract_csv_from_zip(zip_path, "tags.csv")

    total = 0
    with engine.begin() as conn:
        ml_to_internal = _load_ml_to_internal(conn)

        batch: list[dict] = []
        for row in reader:
            ml_movie_id = int(row["movieId"])
            internal_id = ml_to_internal.get(ml_movie_id)
            batch.append(
                {
                    "ml_user_id": int(row["userId"]),
                    "movie_id": internal_id,
                    "tag": row["tag"],
                    "ts": int(row["timestamp"]),
                }
            )
            if len(batch) >= batch_size:
                conn.execute(
                    text(
                        "INSERT INTO ml_tags "
                        "(ml_user_id, movie_id, tag, timestamp) "
                        "VALUES (:ml_user_id, :movie_id, :tag, :ts)"
                    ),
                    batch,
                )
                total += len(batch)
                batch.clear()

        if batch:
            conn.execute(
                text(
                    "INSERT INTO ml_tags "
                    "(ml_user_id, movie_id, tag, timestamp) "
                    "VALUES (:ml_user_id, :movie_id, :tag, :ts)"
                ),
                batch,
            )
            total += len(batch)

    log.info("Tags ingestion complete: %d total rows.", total)


def main() -> None:
    log.info("=== MovieLens 32M Ingest ===")
    data_dir = ensure_data_dir()
    zip_path = download_dataset(data_dir)

    links = ingest_links(zip_path)
    build_id_mappings(links)
    ingest_ratings(zip_path)
    ingest_tags(zip_path)

    log.info("=== Ingest complete ===")


if __name__ == "__main__":
    main()
