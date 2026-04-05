#!/usr/bin/env bash
set -euo pipefail
cd ~/projects/Movies-Recommender

echo "=== Fetching Indian regional movies from TMDB ==="
uv run python -c "
import asyncio
import sys
sys.path.insert(0, '.')

from backend.scripts.tmdb_client import TMDBClient
from backend.database import engine
from sqlmodel import text

# Major Indian languages: Tamil, Telugu, Malayalam, Kannada, Bengali, Marathi, Punjabi, Gujarati
INDIAN_LANGS = {
    'ta': 'Tamil',
    'te': 'Telugu',
    'ml': 'Malayalam',
    'kn': 'Kannada',
    'bn': 'Bengali',
    'mr': 'Marathi',
    'pa': 'Punjabi',
    'gu': 'Gujarati',
}

GENRE_MAP = {
    28: 'Action', 12: 'Adventure', 16: 'Animation', 35: 'Comedy',
    80: 'Crime', 99: 'Documentary', 18: 'Drama', 10751: 'Family',
    14: 'Fantasy', 36: 'History', 27: 'Horror', 10402: 'Music',
    9648: 'Mystery', 10749: 'Romance', 878: 'Science Fiction',
    10770: 'TV Movie', 53: 'Thriller', 10752: 'War', 37: 'Western'
}

async def fetch_indian():
    async with TMDBClient() as client:
        # Get existing TMDB IDs to skip
        with engine.connect() as conn:
            existing = conn.execute(text('SELECT tmdb_id FROM movies WHERE tmdb_id IS NOT NULL')).fetchall()
            existing_tmdb_ids = {r[0] for r in existing}

        total_inserted = 0

        for lang_code, lang_name in INDIAN_LANGS.items():
            print(f'--- Fetching {lang_name} ({lang_code}) movies ---')
            all_movies = []

            # Popular
            for page in range(1, 16):
                movies = await client.discover_movies(
                    page=page,
                    sort_by='popularity.desc',
                    with_original_language=lang_code
                )
                if not movies:
                    break
                all_movies.extend(movies)

            # Top rated with enough votes
            for page in range(1, 11):
                movies = await client.discover_movies(
                    page=page,
                    sort_by='vote_average.desc',
                    with_original_language=lang_code,
                    **{'vote_count.gte': '50'}
                )
                if not movies:
                    break
                all_movies.extend(movies)

            # Dedup
            seen = set()
            unique = []
            for m in all_movies:
                if m['id'] not in seen:
                    seen.add(m['id'])
                    unique.append(m)

            inserted = 0
            with engine.begin() as conn:
                for m in unique:
                    tmdb_id = m.get('id')
                    title = m.get('title', '')
                    if not title or tmdb_id in existing_tmdb_ids:
                        continue

                    genre_ids = m.get('genre_ids', [])
                    genres = ' '.join(GENRE_MAP.get(gid, '') for gid in genre_ids).strip()

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
                        'original_language': lang_code,
                        'tmdb_id': tmdb_id,
                        'genres': genres,
                        'popularity_score': m.get('popularity', 0),
                    })
                    inserted += 1
                    existing_tmdb_ids.add(tmdb_id)

            total_inserted += inserted
            print(f'  {lang_name}: {len(unique)} found, {inserted} inserted')

        with engine.connect() as conn:
            total = conn.execute(text('SELECT COUNT(*) FROM movies')).scalar()
            breakdown = conn.execute(text('''
                SELECT original_language, COUNT(*) as cnt
                FROM movies
                WHERE original_language IN ('en','hi','ta','te','ml','kn','bn','mr','pa','gu')
                GROUP BY original_language
                ORDER BY cnt DESC
            ''')).fetchall()
            print(f'Total movies: {total}')
            for lang, cnt in breakdown:
                name = {'en':'English','hi':'Hindi','ta':'Tamil','te':'Telugu','ml':'Malayalam','kn':'Kannada','bn':'Bengali','mr':'Marathi','pa':'Punjabi','gu':'Gujarati'}.get(lang, lang)
                print(f'  {name}: {cnt}')

        print(f'Total new Indian regional movies inserted: {total_inserted}')

asyncio.run(fetch_indian())
"

echo "=== Done ==="
