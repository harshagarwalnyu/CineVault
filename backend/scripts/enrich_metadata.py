"""
Enrich movie metadata from TMDB
================================
For each movie in the database, fetches trailer, streaming providers,
and certification info from the TMDB API and updates the movies table.

Rate-limited to TMDB_RATE_LIMIT_PER_SEC requests/second.

Usage:
    python -m backend.scripts.enrich_metadata
"""

import asyncio
import json
import logging
import time

import aiohttp
from sqlalchemy import text

from backend.config import settings
from backend.database import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

TMDB_BASE = "https://api.themoviedb.org/3"


class RateLimiter:
    """Token-bucket rate limiter for async requests."""

    def __init__(self, rate_per_sec: int):
        self._rate = rate_per_sec
        self._sem = asyncio.Semaphore(rate_per_sec)
        self._interval = 1.0 / rate_per_sec

    async def acquire(self) -> None:
        await self._sem.acquire()
        asyncio.get_running_loop().call_later(self._interval, self._sem.release)


def _get_movies_to_enrich() -> list[dict]:
    """Return movies that have a tmdb_id but are missing enrichment data."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, tmdb_id FROM movies "
                "WHERE tmdb_id IS NOT NULL "
                "AND (trailer_youtube_key IS NULL "
                "     OR streaming_providers IS NULL "
                "     OR certification IS NULL)"
            )
        ).fetchall()
    return [{"id": r[0], "tmdb_id": r[1]} for r in rows]


async def fetch_enrichment(
    session: aiohttp.ClientSession,
    limiter: RateLimiter,
    tmdb_id: int,
) -> dict | None:
    """Fetch trailer, streaming providers, and certification from TMDB."""
    api_key = settings.TMDB_API_KEY
    if not api_key:
        return None

    url = f"{TMDB_BASE}/movie/{tmdb_id}"
    params = {
        "api_key": api_key,
        "append_to_response": "videos,watch/providers,release_dates",
    }

    await limiter.acquire()
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 429:
                retry_after = int(resp.headers.get("Retry-After", 2))
                log.warning("Rate limited on tmdb_id=%d, sleeping %ds", tmdb_id, retry_after)
                await asyncio.sleep(retry_after)
                return await fetch_enrichment(session, limiter, tmdb_id)
            if resp.status != 200:
                return None
            return await resp.json()
    except Exception as exc:
        log.error("Error fetching tmdb_id=%d: %s", tmdb_id, exc)
        return None


def _extract_trailer_key(data: dict) -> str | None:
    """Extract the first YouTube trailer key from TMDB videos."""
    videos = data.get("videos", {}).get("results", [])
    for v in videos:
        if v.get("site") == "YouTube" and v.get("type") == "Trailer":
            return v.get("key")
    # Fallback: any YouTube video
    for v in videos:
        if v.get("site") == "YouTube":
            return v.get("key")
    return None


def _extract_streaming_providers(data: dict, region: str = "US") -> str | None:
    """Extract streaming provider names for a region as JSON string."""
    providers = data.get("watch/providers", {}).get("results", {})
    region_data = providers.get(region, {})
    flatrate = region_data.get("flatrate", [])
    if not flatrate:
        return None
    names = [p.get("provider_name", "") for p in flatrate if p.get("provider_name")]
    return json.dumps(names) if names else None


def _extract_certification(data: dict, region: str = "US") -> str | None:
    """Extract movie certification (e.g. PG-13) from release_dates."""
    release_dates = data.get("release_dates", {}).get("results", [])
    for entry in release_dates:
        if entry.get("iso_3166_1") == region:
            for rel in entry.get("release_dates", []):
                cert = rel.get("certification", "").strip()
                if cert:
                    return cert
    return None


async def enrich_batch(movies: list[dict]) -> int:
    """Enrich a batch of movies. Returns count of updated rows."""
    limiter = RateLimiter(settings.TMDB_RATE_LIMIT_PER_SEC)
    updated = 0

    async with aiohttp.ClientSession() as session:
        for movie in movies:
            data = await fetch_enrichment(session, limiter, movie["tmdb_id"])
            if not data:
                continue

            trailer_key = _extract_trailer_key(data)
            streaming = _extract_streaming_providers(data)
            cert = _extract_certification(data)

            if not any([trailer_key, streaming, cert]):
                continue

            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE movies SET "
                        "trailer_youtube_key = COALESCE(:trailer, trailer_youtube_key), "
                        "streaming_providers = COALESCE(:streaming, streaming_providers), "
                        "certification = COALESCE(:cert, certification) "
                        "WHERE id = :movie_id"
                    ),
                    {
                        "trailer": trailer_key,
                        "streaming": streaming,
                        "cert": cert,
                        "movie_id": movie["id"],
                    },
                )
            updated += 1

            if updated % 100 == 0:
                log.info("  ... enriched %d movies so far", updated)

    return updated


def main() -> None:
    if not settings.TMDB_API_KEY:
        log.error("TMDB_API_KEY is not set. Cannot enrich metadata.")
        return

    log.info("=== TMDB Metadata Enrichment ===")
    movies = _get_movies_to_enrich()
    log.info("Found %d movies needing enrichment.", len(movies))

    if not movies:
        log.info("Nothing to enrich.")
        return

    t0 = time.monotonic()
    updated = asyncio.run(enrich_batch(movies))
    elapsed = time.monotonic() - t0

    log.info(
        "Enrichment complete: %d/%d movies updated in %.1fs.",
        updated,
        len(movies),
        elapsed,
    )


if __name__ == "__main__":
    main()
