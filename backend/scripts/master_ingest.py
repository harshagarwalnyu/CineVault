import json
import os
import asyncio
import logging
import pandas as pd
from typing import List, Dict
from elasticsearch import Elasticsearch, helpers
from backend.scripts.tmdb_client import TMDBClient
from backend.database import engine, create_tables

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Elasticsearch setup
ES_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
es = Elasticsearch(ES_URL)
INDEX_NAME = "movies"


async def create_es_index():
    """Create Elasticsearch index with optimized mapping."""
    try:
        if es.indices.exists(index=INDEX_NAME):
            return
    except Exception as e:
        logging.warning(f"Could not connect to Elasticsearch at {ES_URL}: {e}")
        return

    mapping = {
        "mappings": {
            "properties": {
                "id": {"type": "integer"},
                "title": {
                    "type": "text",
                    "analyzer": "standard",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "overview": {"type": "text"},
                "genres": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "director": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "cast": {"type": "text"},
                "vote_average": {"type": "float"},
                "vote_count": {"type": "integer"},
                "popularity_score": {"type": "float"},
                "release_date": {
                    "type": "date",
                    "format": "yyyy-MM-dd||strict_date_optional_time",
                },
                "runtime": {"type": "integer"},
                "original_language": {"type": "keyword"},
            }
        }
    }
    es.indices.create(index=INDEX_NAME, body=mapping)
    logging.info(f"Created Elasticsearch index: {INDEX_NAME}")


async def index_to_es(movies: List[Dict]):
    """Bulk index movies to Elasticsearch."""
    try:
        actions = [{"_index": INDEX_NAME, "_id": m["id"], "_source": m} for m in movies]
        helpers.bulk(es, actions)
        logging.info(f"Indexed {len(movies)} movies to Elasticsearch")
    except Exception as e:
        logging.error(f"ES indexing error: {e}")


def save_to_db(movies: List[Dict]):
    """Save movies to PostgreSQL in batches."""
    df = pd.DataFrame(movies)
    # Map fields to DB schema
    df = df.rename(
        columns={
            "popularity_score": "popularity_score",
        }
    )

    # Ensure columns exist in DB schema
    expected_cols = [
        "id",
        "title",
        "genres",
        "overview",
        "vote_average",
        "vote_count",
        "popularity_score",
        "release_date",
        "runtime",
        "director",
        "cast",
        "original_language",
    ]
    df = df[[c for c in expected_cols if c in df.columns]]

    with engine.begin() as conn:
        try:
            # Check existing IDs
            ids_str = ",".join(map(str, df["id"].tolist()))
            existing = pd.read_sql(
                f"SELECT id FROM movies WHERE id IN ({ids_str})", conn
            )
            existing_ids = set(existing["id"].tolist())

            df_new = df[~df["id"].isin(existing_ids)]

            if not df_new.empty:
                df_new.to_sql("movies", engine, if_exists="append", index=False)
                logging.info(f"Saved {len(df_new)} new movies to DB")
        except Exception as e:
            logging.error(f"DB Error: {e}")


async def run_ingestion(pages: int = 10):
    """Orchestrate the ingestion process."""
    await create_es_index()
    create_tables()

    # SOTA Multilingual: Global cinematic coverage
    languages = [
        "en",
        "hi",
        "es",
        "fr",
        "ja",
        "ko",
        "zh",
        "de",
        "it",
        "pt",
        "ru",
        "te",
        "ta",
        "",
    ]

    async with TMDBClient() as client:
        for lang in languages:
            logging.info(f"--- Discovering movies for language: '{lang}' ---")
            for page in range(1, pages + 1):
                logging.info(f"Processing TMDB page {page} for language '{lang}'...")
                movies = await client.discover_movies(
                    page=page, with_original_language=lang
                )
                if not movies:
                    logging.warning(
                        f"No movies found on page {page} for language '{lang}'"
                    )
                    break

                tasks = [client.fetch_movie_details(m["id"]) for m in movies]
                results = await asyncio.gather(*tasks)

                detailed_movies = []
                for m in results:
                    if not m:
                        continue

                    genres = json.dumps([g["name"] for g in m.get("genres", [])])
                    director = ""
                    for person in m.get("credits", {}).get("crew", []):
                        if person["job"] == "Director":
                            director = person["name"]
                            break

                    cast = [p["name"] for p in m.get("credits", {}).get("cast", [])[:5]]

                    movie_data = {
                        "id": m["id"],
                        "title": m["title"],
                        "overview": m.get("overview", ""),
                        "genres": genres,
                        "director": director,
                        "cast": ", ".join(cast),
                        "vote_average": m.get("vote_average", 0),
                        "vote_count": m.get("vote_count", 0),
                        "popularity_score": m.get("popularity", 0),
                        "release_date": m.get("release_date", ""),
                        "runtime": m.get("runtime", 0),
                        "original_language": m.get("original_language", lang),
                    }
                    detailed_movies.append(movie_data)

                if detailed_movies:
                    save_to_db(detailed_movies)
                    await index_to_es(detailed_movies)


if __name__ == "__main__":
    asyncio.run(run_ingestion(pages=3))  # Extended for massive multilingual run
