from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from typing import Any

import aiohttp
from dotenv import load_dotenv
from sqlmodel import text

from backend.database import engine

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=25)


@dataclass(frozen=True)
class CatalogMovie:
    id: int
    title: str
    release_date: str | None
    tmdb_id: int | None
    poster_path: str | None
    backdrop_path: str | None


def normalize_title(value: str | None) -> str:
    return " ".join((value or "").casefold().replace("&", "and").split())


def release_year(value: str | None) -> str | None:
    if not value:
        return None
    year = value.split("-", 1)[0].strip()
    return year if len(year) == 4 and year.isdigit() else None


def unique_ints(*values: int | None) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


class TMDBArtworkBackfiller:
    def __init__(self, *, limit: int, concurrency: int):
        self.limit = limit
        self.concurrency = concurrency

    def load_candidates(self) -> list[CatalogMovie]:
        limit_clause = "LIMIT :limit" if self.limit > 0 else ""
        query = text(
            f"""
            SELECT id, title, release_date, tmdb_id, poster_path, backdrop_path
            FROM movies
            WHERE
                poster_path IS NULL OR trim(poster_path) = ''
                OR backdrop_path IS NULL OR trim(backdrop_path) = ''
                OR tmdb_id IS NULL
            ORDER BY vote_count DESC, id ASC
            {limit_clause}
            """
        )
        params = {"limit": self.limit} if self.limit > 0 else {}
        with engine.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            CatalogMovie(
                id=int(row[0]),
                title=str(row[1]),
                release_date=row[2],
                tmdb_id=int(row[3]) if row[3] else None,
                poster_path=row[4],
                backdrop_path=row[5],
            )
            for row in rows
        ]

    async def request_json(
        self,
        session: aiohttp.ClientSession,
        path: str,
        params: dict[str, Any],
        retries: int = 3,
    ) -> dict[str, Any] | None:
        url = f"{TMDB_BASE_URL}{path}"
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                if response.status == 404:
                    return None
                if response.status == 401:
                    raise RuntimeError("TMDB_API_KEY was rejected by TMDB")
                if response.status == 429 and retries > 0:
                    retry_after = float(response.headers.get("Retry-After", "1"))
                    await asyncio.sleep(retry_after)
                    return await self.request_json(session, path, params, retries - 1)
                response.raise_for_status()
        except aiohttp.ClientError as exc:
            if retries > 0:
                await asyncio.sleep(0.6)
                return await self.request_json(session, path, params, retries - 1)
            print(f"TMDB request failed for {path}: {exc}")
        return None

    async def fetch_by_tmdb_id(
        self,
        session: aiohttp.ClientSession,
        tmdb_id: int,
    ) -> dict[str, Any] | None:
        return await self.request_json(
            session,
            f"/movie/{tmdb_id}",
            {"api_key": TMDB_API_KEY},
        )

    def choose_search_match(
        self,
        movie: CatalogMovie,
        results: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        target_title = normalize_title(movie.title)
        target_year = release_year(movie.release_date)
        best_match: dict[str, Any] | None = None
        best_score = float("-inf")

        for result in results:
            result_title = normalize_title(result.get("title") or result.get("original_title"))
            result_year = release_year(result.get("release_date"))
            score = 0.0

            if result_title == target_title:
                score += 12
            elif target_title and (
                target_title in result_title or result_title in target_title
            ):
                score += 6

            if target_year and result_year == target_year:
                score += 6

            if result.get("poster_path"):
                score += 4
            if result.get("backdrop_path"):
                score += 2

            score += min(float(result.get("popularity") or 0) / 100, 2)

            if score > best_score:
                best_score = score
                best_match = result

        return best_match

    async def search_by_title(
        self,
        session: aiohttp.ClientSession,
        movie: CatalogMovie,
    ) -> dict[str, Any] | None:
        target_year = release_year(movie.release_date)
        params: dict[str, Any] = {
            "api_key": TMDB_API_KEY,
            "query": movie.title,
            "include_adult": "false",
            "page": 1,
        }
        if target_year:
            params["year"] = target_year

        data = await self.request_json(session, "/search/movie", params)
        if not data:
            return None

        results = data.get("results", [])
        return self.choose_search_match(movie, results)

    @staticmethod
    def build_update_payload(
        movie_id: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": movie_id,
            "poster_path": data.get("poster_path"),
            "backdrop_path": data.get("backdrop_path"),
            "tmdb_id": data.get("id"),
            "homepage": data.get("homepage"),
        }

    async def resolve_movie(
        self,
        session: aiohttp.ClientSession,
        movie: CatalogMovie,
    ) -> dict[str, Any] | None:
        fallback_payload: dict[str, Any] | None = None

        for candidate_id in unique_ints(movie.tmdb_id, movie.id):
            direct_match = await self.fetch_by_tmdb_id(session, candidate_id)
            if not direct_match:
                continue

            payload = self.build_update_payload(movie.id, direct_match)
            if payload["poster_path"] or payload["backdrop_path"]:
                return payload
            fallback_payload = payload

        search_match = await self.search_by_title(session, movie)
        if not search_match:
            return fallback_payload

        detailed_match = await self.fetch_by_tmdb_id(session, int(search_match["id"]))
        if detailed_match:
            return self.build_update_payload(movie.id, detailed_match)

        return self.build_update_payload(movie.id, search_match)

    async def run(self) -> None:
        if not TMDB_API_KEY:
            raise RuntimeError("TMDB_API_KEY is missing from the environment")

        candidates = self.load_candidates()
        total = len(candidates)
        if total == 0:
            print("No movies need poster backfill.")
            return

        print(f"Processing {total} movie rows with concurrency={self.concurrency}")

        update_stmt = text(
            """
            UPDATE movies
            SET
                poster_path = COALESCE(:poster_path, poster_path),
                backdrop_path = COALESCE(:backdrop_path, backdrop_path),
                tmdb_id = COALESCE(:tmdb_id, tmdb_id),
                homepage = COALESCE(:homepage, homepage),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        )

        semaphore = asyncio.Semaphore(self.concurrency)
        connector = aiohttp.TCPConnector(limit_per_host=self.concurrency)
        completed = 0
        updated = 0
        unresolved = 0

        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT, connector=connector) as session:
            async def worker(movie: CatalogMovie) -> tuple[CatalogMovie, dict[str, Any] | None]:
                async with semaphore:
                    payload = await self.resolve_movie(session, movie)
                    return movie, payload

            tasks = [worker(movie) for movie in candidates]

            with engine.begin() as conn:
                for task in asyncio.as_completed(tasks):
                    movie, payload = await task
                    completed += 1

                    if payload and (payload.get("poster_path") or payload.get("backdrop_path")):
                        conn.execute(update_stmt, payload)
                        updated += 1
                        print(
                            f"[{completed}/{total}] updated {movie.title}"
                            f" poster={bool(payload.get('poster_path'))}"
                            f" backdrop={bool(payload.get('backdrop_path'))}"
                        )
                    else:
                        unresolved += 1
                        print(f"[{completed}/{total}] no artwork for {movie.title}")

        print(
            f"Backfill complete: updated={updated}, unresolved={unresolved}, total={total}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill missing TMDB artwork")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of movie rows to process. Use 0 for all candidates.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Maximum number of concurrent TMDB requests.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    options = parse_args()
    asyncio.run(
        TMDBArtworkBackfiller(
            limit=options.limit,
            concurrency=max(1, options.concurrency),
        ).run()
    )
