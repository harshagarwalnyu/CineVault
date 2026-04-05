#!/usr/bin/env bash
set -euo pipefail
cd /home/bossman/projects/Movies-Recommender

echo "=== Fetching latest movies from TMDB ==="
uv run python -c "
import asyncio
import sys
sys.path.insert(0, '.')

from backend.scripts.tmdb_client import TMDBClient
from backend.database import engine, create_tables
from sqlmodel import text

async def fetch_latest():
    create_tables()

    async with TMDBClient() as client:
        all_movies = []
        # Fetch 10 pages of popular movies (200 movies)
        for page in range(1, 11):
            print(f'  Fetching page {page}/10...')
            movies = await client.get_popular_movies(page=page)
            all_movies.extend(movies)

        # Also fetch recent releases (2025-2026)
        for page in range(1, 6):
            print(f'  Fetching recent releases page {page}/5...')
            movies = await client.discover_movies(
                page=page,
                sort_by='popularity.desc',
                **{'primary_release_date.gte': '2025-01-01'}
            )
            all_movies.extend(movies)

        print(f'  Fetched {len(all_movies)} movies from TMDB')

        # Get existing IDs to avoid duplicates
        with engine.connect() as conn:
            existing = conn.execute(text('SELECT tmdb_id FROM movies WHERE tmdb_id IS NOT NULL')).fetchall()
            existing_tmdb_ids = {r[0] for r in existing}
            existing_titles = conn.execute(text('SELECT title FROM movies')).fetchall()
            existing_title_set = {r[0].lower() for r in existing_titles}

        inserted = 0
        with engine.begin() as conn:
            for m in all_movies:
                tmdb_id = m.get('id')
                title = m.get('title', '')
                if not title:
                    continue
                if tmdb_id in existing_tmdb_ids:
                    continue
                if title.lower() in existing_title_set:
                    continue

                # Extract genre names from TMDB genre_ids
                genre_ids = m.get('genre_ids', [])
                genre_map = {
                    28: 'Action', 12: 'Adventure', 16: 'Animation', 35: 'Comedy',
                    80: 'Crime', 99: 'Documentary', 18: 'Drama', 10751: 'Family',
                    14: 'Fantasy', 36: 'History', 27: 'Horror', 10402: 'Music',
                    9648: 'Mystery', 10749: 'Romance', 878: 'Science Fiction',
                    10770: 'TV Movie', 53: 'Thriller', 10752: 'War', 37: 'Western'
                }
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
                    'original_language': m.get('original_language', ''),
                    'tmdb_id': tmdb_id,
                    'genres': genres,
                    'popularity_score': m.get('popularity', 0),
                })
                inserted += 1
                existing_tmdb_ids.add(tmdb_id)
                existing_title_set.add(title.lower())

        print(f'  Inserted {inserted} new movies')

        # Show final count
        with engine.connect() as conn:
            total = conn.execute(text('SELECT COUNT(*) FROM movies')).scalar()
            print(f'  Total movies in DB: {total}')

asyncio.run(fetch_latest())
"

echo "=== Done! ==="
