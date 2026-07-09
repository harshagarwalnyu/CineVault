import asyncio
import json
import logging
import os
import sys
import time
import random
from typing import List

import aiohttp
from sqlmodel import text
from sqlalchemy.exc import OperationalError  # sqlmodel re-exports sqlalchemy
from backend.database import engine
from backend.config import TMDB_API_KEY

# Configuration
BATCH_SIZE = 20  # Reduced for stability
CONCURRENCY = 4  # Reduced for stability
STATE_FILE = "enrichment_state.json"
MAX_DB_RETRIES = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("enrichment.log"), logging.StreamHandler()],
)


class EnrichmentWorker:
    def __init__(self):
        if not TMDB_API_KEY:
            logging.critical(
                "❌ TMDB_API_KEY is missing in environment/config. Exiting."
            )
            sys.exit(1)

        self.last_id = 0
        self.processed_count = 0
        self.start_time = time.time()
        self.load_state()

    def load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                    self.last_id = data.get("last_processed_id", 0)
                    self.processed_count = data.get("total_processed", 0)
                    logging.info(
                        f"🔄 Resuming from ID: {self.last_id} (Processed: {self.processed_count})"
                    )
            except Exception:
                logging.warning("⚠️ State file corrupted. Starting fresh.")
        else:
            logging.info("🚀 Starting fresh enrichment process.")

    def save_state(self):
        try:
            # Atomic write pattern to prevent corruption
            temp_file = STATE_FILE + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(
                    {
                        "last_processed_id": self.last_id,
                        "total_processed": self.processed_count,
                        "timestamp": time.time(),
                    },
                    f,
                )
            os.replace(temp_file, STATE_FILE)
        except Exception as e:
            logging.error(f"⚠️ Failed to save state: {e}")

    async def fetch_tmdb_data(self, session, imdb_id):
        """Fetch details from TMDB using external ID (IMDb ID)."""
        url = f"https://api.themoviedb.org/3/find/{imdb_id}"
        params = {"api_key": TMDB_API_KEY, "external_source": "imdb_id"}
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("movie_results", [])
                    return results[0] if results else None
                elif response.status == 429:
                    # Exponential Backoff with Jitter
                    wait_time = int(
                        response.headers.get("Retry-After", 2)
                    ) + random.uniform(0, 1)
                    logging.warning(
                        f"⚠️ Rate limit hit for {imdb_id}. Sleeping {wait_time:.1f}s..."
                    )
                    await asyncio.sleep(wait_time)
                    return await self.fetch_tmdb_data(session, imdb_id)
                elif response.status == 401:
                    logging.critical("❌ 401 Unauthorized. Check your TMDB_API_KEY.")
                    sys.exit(1)
                else:
                    return None  # 404 or other error
        except Exception as e:
            logging.error(f"❌ Exception fetching {imdb_id}: {e}")
            return None

    def get_batch(self):
        """Get a batch of movies that need enrichment."""
        query = text("""
            SELECT id, imdb_id
            FROM movies
            WHERE id > :last_id
            AND (overview IS NULL OR poster_path IS NULL)
            AND imdb_id IS NOT NULL
            ORDER BY id ASC
            LIMIT :limit
        """)
        with engine.connect() as conn:
            return conn.execute(
                query, {"last_id": self.last_id, "limit": BATCH_SIZE}
            ).fetchall()

    def update_db(self, updates: List[dict]):
        """Bulk update movies with retry logic for SQLite locks."""
        if not updates:
            return

        stmt = text("""
            UPDATE movies
            SET
                overview = :overview,
                poster_path = :poster_path,
                release_date = COALESCE(release_date, :release_date),
                vote_average = COALESCE(:vote_average, vote_average),
                vote_count = COALESCE(:vote_count, vote_count),
                popularity_score = COALESCE(:popularity, popularity_score),
                updated_at = CURRENT_TIMESTAMP
            WHERE imdb_id = :imdb_id
        """)

        for attempt in range(MAX_DB_RETRIES):
            try:
                with engine.begin() as conn:
                    conn.execute(stmt, updates)
                logging.info(f"✅ Updated {len(updates)} movies.")
                return
            except OperationalError as e:
                if "locked" in str(e).lower():
                    wait = (attempt + 1) * 0.5
                    logging.warning(f"🔒 Database locked. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logging.error(f"❌ DB Error: {e}")
                    raise e
            except Exception as e:
                logging.error(f"❌ Unexpected DB Error: {e}")
                return

    async def process_batch(self):
        rows = self.get_batch()
        if not rows:
            logging.info("🎉 No more movies to enrich! Sleeping 60s before check...")
            await asyncio.sleep(60)
            return True  # Continue loop, maybe new data comes in

        async with aiohttp.ClientSession() as session:
            tasks = []
            valid_rows = []

            for row in rows:
                tasks.append(self.fetch_tmdb_data(session, row.imdb_id))
                valid_rows.append(row)

            results = await asyncio.gather(*tasks)

            updates = []
            max_id_in_batch = self.last_id

            for row, data in zip(valid_rows, results):
                max_id_in_batch = max(max_id_in_batch, row.id)

                if data:
                    updates.append(
                        {
                            "imdb_id": row.imdb_id,
                            "overview": data.get("overview"),
                            "poster_path": data.get("poster_path"),
                            "release_date": data.get("release_date"),
                            "vote_average": data.get("vote_average"),
                            "vote_count": data.get("vote_count"),
                            "popularity": data.get("popularity"),
                        }
                    )
                else:
                    # Mark as "checked" by setting a placeholder so we don't query again
                    updates.append(
                        {
                            "imdb_id": row.imdb_id,
                            "overview": "No overview available.",
                            "poster_path": None,  # Keep null or set a placeholder
                            "release_date": None,
                            "vote_average": None,
                            "vote_count": None,
                            "popularity": None,
                        }
                    )

            self.update_db(updates)
            self.last_id = max_id_in_batch
            self.processed_count += len(rows)
            self.save_state()

            await asyncio.sleep(0.5)  # Rate limit nice-ness

        return True

    async def run(self):
        logging.info("🕷️ Enrichment Worker Started (Robust Mode).")
        while True:
            try:
                await self.process_batch()
            except Exception as e:
                logging.error(f"🔥 Critical Error in main loop: {e}")
                await asyncio.sleep(5)


if __name__ == "__main__":
    worker = EnrichmentWorker()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logging.info("🛑 Worker stopped by user.")
