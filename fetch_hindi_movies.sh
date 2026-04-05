#!/usr/bin/env bash
set -euo pipefail
cd ~/projects/Movies-Recommender

echo "=== Fetching Hindi (Bollywood) movies from TMDB ==="
uv run python -c "
import asyncio
import sys
sys.path.insert(0, '.')

from backend.scripts.tmdb_client import TMDBClient
from backend.database import engine
from sqlmodel import text

async def fetch_hindi():
    async with TMDBClient() as client:
        all_movies = []

        # Fetch popular Hindi movies (20 pages = ~400 movies)
        for page in range(1, 21):
            print(f'  Fetching Hindi popular page {page}/20...')
            movies = await client.discover_movies(
                page=page,
                sort_by='popularity.desc',
                with_original_language='hi'
            )
            all_movies.extend(movies)

        # Recent Hindi releases (2024-2026)
        for page in range(1, 11):
            print(f'  Fetching recent Hindi page {page}/10...')
            movies = await client.discover_movies(
                page=page,
                sort_by='vote_count.desc',
                with_original_language='hi',
                **{'primary_release_date.gte': '2024-01-01'}
            )
            all_movies.extend(movies)

        # Top rated Hindi movies of all time
        for page in range(1, 11):
            print(f'  Fetching top-rated Hindi page {page}/10...')
            movies = await client.discover_movies(
                page=page,
                sort_by='vote_average.desc',
                with_original_language='hi',
                **{'vote_count.gte': '100'}
            )
            all_movies.extend(movies)

        print(f'  Fetched {len(all_movies)} Hindi movies from TMDB')

        # Deduplicate
        seen_ids = set()
        unique = []
        for m in all_movies:
            if m['id'] not in seen_ids:
                seen_ids.add(m['id'])
                unique.append(m)
        all_movies = unique
        print(f'  After dedup: {len(all_movies)} unique')

        # Get existing
        with engine.connect() as conn:
            existing = conn.execute(text('SELECT tmdb_id FROM movies WHERE tmdb_id IS NOT NULL')).fetchall()
            existing_tmdb_ids = {r[0] for r in existing}

        genre_map = {
            28: 'Action', 12: 'Adventure', 16: 'Animation', 35: 'Comedy',
            80: 'Crime', 99: 'Documentary', 18: 'Drama', 10751: 'Family',
            14: 'Fantasy', 36: 'History', 27: 'Horror', 10402: 'Music',
            9648: 'Mystery', 10749: 'Romance', 878: 'Science Fiction',
            10770: 'TV Movie', 53: 'Thriller', 10752: 'War', 37: 'Western'
        }

        inserted = 0
        with engine.begin() as conn:
            for m in all_movies:
                tmdb_id = m.get('id')
                title = m.get('title', '')
                if not title or tmdb_id in existing_tmdb_ids:
                    continue

                genre_ids = m.get('genre_ids', [])
                genres = ' '.join(genre_map.get(gid, '') for gid in genre_ids).strip()

                conn.execute(text('''
                    INSERT INTO movies (title, overview, poster_path, backdrop_path,
                        vote_average, vote_count, release_date, original_language,
                        tmdb_id, genres, popularity_score)
                    VALUES (:title, :overview, :poster_path, :backdrop_path,
                        :vote_average, :vote_count, :release_date, :original_language,
                        :tmdb_id, :genres, :popularity_score)
                '''), {
                    'title': title,
                    'overview': m.get('overview', ''),
                    'poster_path': m.get('poster_path'),
                    'backdrop_path': m.get('backdrop_path'),
                    'vote_average': m.get('vote_average', 0),
                    'vote_count': m.get('vote_count', 0),
                    'release_date': m.get('release_date', ''),
                    'original_language': 'hi',
                    'tmdb_id': tmdb_id,
                    'genres': genres,
                    'popularity_score': m.get('popularity', 0),
                })
                inserted += 1
                existing_tmdb_ids.add(tmdb_id)

        print(f'  Inserted {inserted} new Hindi movies')

        with engine.connect() as conn:
            total = conn.execute(text('SELECT COUNT(*) FROM movies')).scalar()
            hi_count = conn.execute(text(\"SELECT COUNT(*) FROM movies WHERE original_language = 'hi'\")).scalar()
            en_count = conn.execute(text(\"SELECT COUNT(*) FROM movies WHERE original_language = 'en'\")).scalar()
            print(f'  Total movies: {total} (English: {en_count}, Hindi: {hi_count})')

asyncio.run(fetch_hindi())
"

echo "=== Done ==="
