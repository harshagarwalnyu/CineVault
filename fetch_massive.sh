#!/usr/bin/env bash
set -euo pipefail
cd ~/projects/Movies-Recommender

echo "=== MASSIVE English + Hindi movie fetch from TMDB ==="
uv run python -c "
import asyncio
import sys
import time
sys.path.insert(0, '.')

from backend.scripts.tmdb_client import TMDBClient
from backend.database import engine
from sqlmodel import text

GENRE_MAP = {
    28: 'Action', 12: 'Adventure', 16: 'Animation', 35: 'Comedy',
    80: 'Crime', 99: 'Documentary', 18: 'Drama', 10751: 'Family',
    14: 'Fantasy', 36: 'History', 27: 'Horror', 10402: 'Music',
    9648: 'Mystery', 10749: 'Romance', 878: 'Science Fiction',
    10770: 'TV Movie', 53: 'Thriller', 10752: 'War', 37: 'Western'
}

async def fetch_massive():
    # Get existing TMDB IDs
    with engine.connect() as conn:
        existing = conn.execute(text('SELECT tmdb_id FROM movies WHERE tmdb_id IS NOT NULL')).fetchall()
        existing_tmdb_ids = {r[0] for r in existing}
        total_before = conn.execute(text('SELECT COUNT(*) FROM movies')).scalar()
    print(f'Starting with {total_before} movies ({len(existing_tmdb_ids)} with TMDB IDs)')

    total_inserted = 0

    async with TMDBClient() as client:
        # Strategy: TMDB discover API maxes at page 500 (10k movies per query)
        # Work around by querying year ranges

        configs = []

        # --- ENGLISH MOVIES ---
        # By year ranges to get more than 10k
        for year_start in range(1950, 2027, 3):
            year_end = min(year_start + 2, 2026)
            configs.append({
                'lang': 'en', 'label': f'English {year_start}-{year_end}',
                'pages': 50,  # 1000 per range
                'extra': {
                    'primary_release_date.gte': f'{year_start}-01-01',
                    'primary_release_date.lte': f'{year_end}-12-31',
                },
                'sort': 'popularity.desc'
            })
        # Top rated English (high vote count)
        configs.append({
            'lang': 'en', 'label': 'English top-rated',
            'pages': 100, 'extra': {'vote_count.gte': '10'},
            'sort': 'vote_average.desc'
        })
        # Revenue-sorted English
        configs.append({
            'lang': 'en', 'label': 'English by revenue',
            'pages': 100, 'extra': {},
            'sort': 'revenue.desc'
        })

        # --- HINDI MOVIES ---
        for year_start in range(1950, 2027, 5):
            year_end = min(year_start + 4, 2026)
            configs.append({
                'lang': 'hi', 'label': f'Hindi {year_start}-{year_end}',
                'pages': 50,
                'extra': {
                    'primary_release_date.gte': f'{year_start}-01-01',
                    'primary_release_date.lte': f'{year_end}-12-31',
                },
                'sort': 'popularity.desc'
            })
        configs.append({
            'lang': 'hi', 'label': 'Hindi top-rated',
            'pages': 100, 'extra': {'vote_count.gte': '5'},
            'sort': 'vote_average.desc'
        })
        configs.append({
            'lang': 'hi', 'label': 'Hindi by revenue',
            'pages': 100, 'extra': {},
            'sort': 'revenue.desc'
        })

        for cfg in configs:
            lang = cfg['lang']
            label = cfg['label']
            max_pages = cfg['pages']
            sort_by = cfg['sort']
            extra = cfg['extra']

            batch_movies = []
            empty_pages = 0

            for page in range(1, max_pages + 1):
                try:
                    movies = await client.discover_movies(
                        page=page,
                        sort_by=sort_by,
                        with_original_language=lang,
                        **extra
                    )
                except Exception as e:
                    print(f'  Error on {label} page {page}: {e}')
                    break

                if not movies:
                    empty_pages += 1
                    if empty_pages >= 2:
                        break
                    continue

                batch_movies.extend(movies)
                empty_pages = 0

                # Strict rate limit courtesy (Max 10 requests per second)
                await asyncio.sleep(0.1)

            # Dedup within batch
            seen = set()
            unique = []
            for m in batch_movies:
                mid = m.get('id')
                if mid and mid not in seen:
                    seen.add(mid)
                    unique.append(m)

            # Insert
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
                        'original_language': lang,
                        'tmdb_id': tmdb_id,
                        'genres': genres,
                        'popularity_score': m.get('popularity', 0),
                    })
                    inserted += 1
                    existing_tmdb_ids.add(tmdb_id)

            total_inserted += inserted
            if inserted > 0:
                print(f'  {label}: {len(unique)} found, {inserted} new')

    # Final stats
    with engine.connect() as conn:
        total = conn.execute(text('SELECT COUNT(*) FROM movies')).scalar()
        breakdown = conn.execute(text('''
            SELECT original_language, COUNT(*) as cnt
            FROM movies
            GROUP BY original_language
            ORDER BY cnt DESC
            LIMIT 15
        ''')).fetchall()
        print(f'')
        print(f'=== Final Database Stats ===')
        print(f'Total movies: {total} ({total_inserted} new this run)')
        for lang, cnt in breakdown:
            print(f'  {lang}: {cnt}')

asyncio.run(fetch_massive())
"

echo "=== DONE ==="
