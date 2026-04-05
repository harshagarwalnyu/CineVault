"""
Mock Data Seeder
================
Generates dummy movies and users if the database is empty.
Ensures the application works out-of-the-box without large downloads.
"""

import random
import pandas as pd
from datetime import datetime, timedelta
from backend.database import engine, text, initialize_database


def seed_data():
    print("🌱 Checking data seed status...")

    from backend.database import create_sample_users

    with engine.connect() as conn:
        # Check if we have movies
        try:
            count = conn.execute(text("SELECT COUNT(*) FROM movies")).scalar()
        except Exception:
            print("   -> Tables missing, initializing DB...")
            initialize_database()
            count = 0

        if count > 0:
            create_sample_users(n_users=10)
            print(f"✅ Database already has {count} movies. Skipping seed.")
            return

    print("🌱 Seeding database with mock data...")

    # Generate 50 Mock Movies
    genres_list = [
        "Action",
        "Adventure",
        "Comedy",
        "Drama",
        "Sci-Fi",
        "Horror",
        "Romance",
        "Thriller",
    ]

    movies = []
    for i in range(1, 51):
        genre = random.choice(genres_list)
        movies.append(
            {
                "id": i,
                "title": f"Mock Movie {i}: The {genre} Saga",
                "genres": f"{genre} {random.choice(genres_list)}",
                "keywords": f"mock, test, {genre.lower()}",
                "tagline": "This is a generated movie.",
                "overview": f"A generated plot for Mock Movie {i}. It features intense {genre.lower()} scenes and amazing acting.",
                "cast": "Actor A, Actor B, Actor C",
                "director": f"Director {i}",
                "vote_average": round(random.uniform(3.0, 9.5), 1),
                "vote_count": random.randint(10, 10000),
                "popularity_score": random.uniform(0, 100),
                "release_date": (
                    datetime.now() - timedelta(days=random.randint(0, 3650))
                ).strftime("%Y-%m-%d"),
                "runtime": random.randint(80, 180),
                "poster_path": "",  # No poster for mock
            }
        )

    df_movies = pd.DataFrame(movies)

    # Write to DB
    try:
        df_movies.to_sql("movies", engine, if_exists="append", index=False)
        print(f"✅ Inserted {len(df_movies)} mock movies.")
    except Exception as e:
        print(f"❌ Failed to insert mock movies: {e}")
        return

    # Generate Users and Ratings
    from backend.database import generate_sample_ratings

    create_sample_users(n_users=10)
    generate_sample_ratings(ratings_per_user=10)

    print("✅ Seeding complete.")


if __name__ == "__main__":
    seed_data()
