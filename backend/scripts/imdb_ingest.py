import os
import requests
import pandas as pd
from tqdm import tqdm
from backend.database import engine, text

IMDB_URLS = {
    "basics": "https://datasets.imdbws.com/title.basics.tsv.gz",
    "ratings": "https://datasets.imdbws.com/title.ratings.tsv.gz",
}

DATA_DIR = "data/imdb"


def download_file(url, filename):
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, filename)

    if os.path.exists(filepath):
        # Verify file integrity
        try:
            import gzip

            with gzip.open(filepath, "rb") as f:
                f.seek(-1, os.SEEK_END)
            print(f"Skipping download, {filename} is valid.")
            return filepath
        except Exception:
            print(f"Found corrupted file {filename}. Re-downloading...")
            os.remove(filepath)

    print(f"Downloading {filename}...")
    response = requests.get(url, stream=True, timeout=10)
    total_size = int(response.headers.get("content-length", 0))

    with (
        open(filepath, "wb") as f,
        tqdm(
            desc=filename,
            total=total_size,
            unit="iB",
            unit_scale=True,
            unit_divisor=1024,
        ) as bar,
    ):
        for data in response.iter_content(chunk_size=1024):
            size = f.write(data)
            bar.update(size)
    return filepath


def process_imdb():
    basics_path = download_file(IMDB_URLS["basics"], "title.basics.tsv.gz")
    ratings_path = download_file(IMDB_URLS["ratings"], "title.ratings.tsv.gz")

    print("Reading IMDb ratings...")
    df_ratings = pd.read_csv(
        ratings_path, sep="\t", compression="gzip", na_values="\\N"
    )

    print("Reading IMDb basics (streaming for memory efficiency)...")
    # Optimize chunk size for bulk inserts
    chunk_size = 200000
    reader = pd.read_csv(
        basics_path,
        sep="\t",
        compression="gzip",
        na_values="\\N",
        chunksize=chunk_size,
        low_memory=False,
    )

    total_movies = 0

    # Cache existing IDs once to avoid DB hits in loop (Bloom filter approach)
    print("Caching existing IDs...")
    with engine.connect() as conn:
        existing_ids = set(
            pd.read_sql("SELECT imdb_id FROM movies WHERE imdb_id IS NOT NULL", conn)[
                "imdb_id"
            ]
        )

    print(f"Found {len(existing_ids)} existing movies. Starting bulk ingestion...")

    for chunk in reader:
        # Filter for movies, series, and specials
        allowed_types = ["movie", "tvSeries", "tvMovie", "tvSpecial", "video"]
        movies = chunk[
            (chunk["titleType"].isin(allowed_types)) & (chunk["isAdult"] == 0)
        ]

        if movies.empty:
            continue

        # Fast memory-based filtering
        # Ensure we don't process what we already have
        movies = movies[~movies["tconst"].isin(existing_ids)]
        if movies.empty:
            continue

        # Merge with ratings
        merged = movies.merge(df_ratings, on="tconst", how="left")

        # Prepare for DB
        # Create a clean dataframe for insertion
        db_chunk = pd.DataFrame(
            {
                "imdb_id": merged["tconst"],
                "title": merged["primaryTitle"].fillna("Unknown Title"),
                "genres": merged["genres"].fillna("").str.replace(",", " "),
                "release_date": merged["startYear"].astype(str),
                "runtime": merged["runtimeMinutes"].fillna(0),
                "imdb_rating": merged["averageRating"].fillna(0),
                "imdb_votes": merged["numVotes"].fillna(0),
            }
        )

        # Raw SQL Bulk Insert for Speed
        # We use SQLAlchemy's efficient parameter binding
        data_to_insert = db_chunk.to_dict(orient="records")

        if not data_to_insert:
            continue

        with engine.begin() as conn:
            # Check DB dialect to ensure correct syntax if possible, but ON CONFLICT is widely supported now
            # For strict SQLite compatibility if older versions are used:
            # But we assume reasonably modern env.
            conn.execute(
                text("""
                INSERT INTO movies (imdb_id, title, genres, release_date, runtime, imdb_rating, imdb_votes)
                VALUES (:imdb_id, :title, :genres, :release_date, :runtime, :imdb_rating, :imdb_votes)
                ON CONFLICT (imdb_id) DO NOTHING
                """),
                data_to_insert,
            )

        # Update local cache to prevent duplicates within the same run if any
        existing_ids.update(db_chunk["imdb_id"])

        total_movies += len(db_chunk)
        print(f"Processed {total_movies} new movies...", flush=True)

        # Limit for production
        if len(existing_ids) >= 1200000:
            print("Reached 1,200,000 total movies. Stopping.", flush=True)
            break


if __name__ == "__main__":
    process_imdb()
