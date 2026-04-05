import asyncio
import json
import os
import sys
import pandas as pd
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import traceback

# Add parent directory to path so we can import backend modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.config import settings
from backend.surreal_db import get_surreal_db, setup_surreal_schema

class TropeExtraction(BaseModel):
    name: str = Field(description="The name of the trope, pacing, or mood, e.g., 'Enemies to Lovers', 'Fast-Paced', 'Cyberpunk Noir'")
    description: str = Field(description="A brief explanation of what this trope means generally.")
    confidence: float = Field(description="How confident you are this trope applies to this movie (0.0 to 1.0).")
    explanation: str = Field(description="Exactly how and why this trope appears in THIS specific movie.")

class MovieTropes(BaseModel):
    tropes: list[TropeExtraction]

async def main():
    if not settings.GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY not set in environment or config.")
        return

    # Initialize SurrealDB
    try:
        db = await get_surreal_db()
        await setup_surreal_schema(db)
        print("Connected to SurrealDB and schema initialized.")
    except Exception as e:
        print(f"Failed to connect to SurrealDB: {e}")
        return

    # Initialize Gemini
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    
    # Load movies
    csv_path = "data/movies.csv"
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        return
        
    df = pd.read_csv(csv_path)
    
    # Let's just process a sample of 10 for demonstration of the "Moat"
    # In production, this would run over the entire dataset via a task queue.
    sample_df = df.head(10).fillna("")
    
    print(f"Starting ingestion of {len(sample_df)} movies into SurrealDB...")

    for index, row in sample_df.iterrows():
        movie_id = row['id']
        title = row['title']
        overview = row['overview']
        genres = str(row['genres']).split(',') if row['genres'] else []
        release_date = str(row['release_date'])
        popularity = float(row['popularity_score']) if 'popularity_score' in row else 0.0
        
        print(f"Processing: {title}...")
        
        # 1. Prompt Gemini for structured Tropes Extraction
        prompt = f"""
        Analyze the following movie based on its title, genres, and overview.
        Extract up to 5 defining 'tropes', moods, or pacing styles that would help someone find this specific vibe.
        Be specific and granular (e.g., use 'Gritty Cyberpunk' instead of just 'Sci-Fi', or 'Reluctant Hero').
        
        Title: {title}
        Genres: {genres}
        Overview: {overview}
        """
        
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MovieTropes,
                ),
            )
            
            tropes_data = json.loads(response.text)
            
            # 2. Get embeddings for the movie
            embedding_response = client.models.embed_content(
                model='text-embedding-004',
                contents=f"Title: {title}. Overview: {overview}. Genres: {', '.join(genres)}",
            )
            embedding = embedding_response.embeddings[0].values
            
            # 3. Insert into SurrealDB
            # Upsert Movie
            movie_record_id = f"movie:{movie_id}"
            await db.query(
                "UPSERT type::thing('movie', $id) SET title = $title, overview = $overview, "
                "genres = $genres, release_date = $release_date, popularity = $popularity, embedding = $embedding;",
                {
                    "id": str(movie_id),
                    "title": title,
                    "overview": overview,
                    "genres": genres,
                    "release_date": release_date,
                    "popularity": popularity,
                    "embedding": embedding
                }
            )
            
            # Upsert Tropes and Relationships
            for t in tropes_data.get('tropes', []):
                # We use a slugified version of the name for the ID to avoid duplicates
                trope_slug = t['name'].lower().replace(' ', '_').replace('-', '_')
                trope_id = f"trope:{trope_slug}"
                
                await db.query(
                    "UPSERT type::thing('trope', $id) SET name = $name, description = $description;",
                    {
                        "id": trope_slug,
                        "name": t['name'],
                        "description": t['description']
                    }
                )
                
                # Create the Graph Relationship: Movie -> Trope
                await db.query(
                    "RELATE $movie_id->has_trope->$trope_id SET confidence = $confidence, explanation = $explanation;",
                    {
                        "movie_id": movie_record_id,
                        "trope_id": trope_id,
                        "confidence": t['confidence'],
                        "explanation": t['explanation']
                    }
                )
                
            print(f"✓ Successfully ingested {title} and linked {len(tropes_data.get('tropes', []))} tropes.")
            
        except Exception as e:
            print(f"✗ Error processing {title}: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
