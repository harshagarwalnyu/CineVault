from surrealdb import Surreal
from backend.config import settings

async def get_surreal_db() -> Surreal:
    """Get an authenticated connection to SurrealDB."""
    db = Surreal(settings.SURREALDB_URL)
    await db.connect()
    await db.signin({
        "user": settings.SURREALDB_USER,
        "pass": settings.SURREALDB_PASS
    })
    await db.use(settings.SURREALDB_NS, settings.SURREALDB_DB)
    return db

async def setup_surreal_schema(db: Surreal):
    """Initialize the schema for the Uncopyable Moat Graph."""
    # Create tables and enforce schema
    queries = [
        "DEFINE TABLE movie SCHEMAFULL;",
        "DEFINE FIELD title ON movie TYPE string;",
        "DEFINE FIELD overview ON movie TYPE string;",
        "DEFINE FIELD genres ON movie TYPE array<string>;",
        "DEFINE FIELD release_date ON movie TYPE string;",
        "DEFINE FIELD popularity ON movie TYPE float;",
        
        "DEFINE TABLE trope SCHEMAFULL;",
        "DEFINE FIELD name ON trope TYPE string;",
        "DEFINE FIELD description ON trope TYPE string;",
        "DEFINE INDEX trope_name ON trope COLUMNS name UNIQUE;",
        
        "DEFINE TABLE has_trope TYPE RELATION IN movie OUT trope;",
        "DEFINE FIELD confidence ON has_trope TYPE float;",
        "DEFINE FIELD explanation ON has_trope TYPE string;",
        
        # Vector embedding field for tropes/movies if needed
        # We'll use 768 dimensions for Google GenAI text-embedding-004 embeddings
        "DEFINE FIELD embedding ON movie TYPE array<float>;"
    ]
    
    for query in queries:
        await db.query(query)
