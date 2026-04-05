import os
import asyncio
import aiohttp
import logging
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()


class TMDBClient:
    """High-performance asynchronous TMDB client."""

    BASE_URL = "https://api.themoviedb.org/3"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TMDB_API_KEY")
        if not self.api_key or self.api_key == "your_tmdb_key_here":
            # Attempt to find from shared env or fallback
            logging.warning("TMDB_API_KEY not found. Using discovery...")

        self.semaphore = asyncio.Semaphore(
            20
        )  # TMDB rate limit is generous but let's be safe
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_movie_details(
        self, tmdb_id: int, retries: int = 3
    ) -> Optional[Dict]:
        """Fetch full details for a single movie."""
        if not self.session:
            self.session = aiohttp.ClientSession()

        if not self.api_key:
            logging.error("TMDB API Key missing")
            return None

        url = f"{self.BASE_URL}/movie/{tmdb_id}"
        params = {
            "api_key": self.api_key,
            "append_to_response": "credits,keywords,videos",
        }

        async with self.semaphore:
            try:
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:
                        if retries > 0:
                            wait_time = int(response.headers.get("Retry-After", 1))
                            logging.warning(
                                f"Rate limited (429). Retrying in {wait_time}s..."
                            )
                            await asyncio.sleep(wait_time)
                            return await self.fetch_movie_details(tmdb_id, retries - 1)
                        else:
                            logging.error(f"Max retries reached for movie {tmdb_id}")
                            return None
                    return None
            except Exception as e:
                logging.error(f"Error fetching {tmdb_id}: {e}")
                return None

    async def get_popular_movies(self, page: int = 1) -> List[Dict]:
        """Get a list of popular movies."""
        url = f"{self.BASE_URL}/movie/popular"
        params = {"api_key": self.api_key, "page": page}

        async with self.semaphore:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("results", [])
                return []

    async def discover_movies(
        self, page: int = 1, sort_by: str = "popularity.desc", **kwargs
    ) -> List[Dict]:
        """Discover movies with various filters."""
        url = f"{self.BASE_URL}/discover/movie"
        params = {
            "api_key": self.api_key,
            "page": page,
            "sort_by": sort_by,
            "include_adult": "false",
        }
        params.update(kwargs)

        async with self.semaphore:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("results", [])
                return []
