from typing import cast

from surrealdb import AsyncSurreal
from surrealdb.connections.async_http import AsyncHttpSurrealConnection
from surrealdb.connections.async_ws import AsyncWsSurrealConnection
from backend.config import settings

# The app only ever connects over ws(s):// or http(s):// URLs, never the
# embedded (in-process) backend, so narrow the factory's return union
# accordingly — this also avoids AsyncEmbeddedSurrealConnection.connect()'s
# differing signature (it requires a redundant "url" argument).
AsyncSurrealConnection = AsyncWsSurrealConnection | AsyncHttpSurrealConnection


async def get_surreal_db() -> AsyncSurrealConnection:
    """Get an authenticated connection to SurrealDB."""
    db = cast(AsyncSurrealConnection, AsyncSurreal(settings.SURREALDB_URL))
    # The connection was already given its URL via the AsyncSurreal(url) factory
    # above; connect() itself takes no further arguments on ws/http connections
    # at runtime, but the shared AsyncTemplate base the stubs resolve to types
    # it as requiring one — this is a stub-precision gap, not a real bug.
    await db.connect()  # type: ignore[call-arg]
    await db.signin({"user": settings.SURREALDB_USER, "pass": settings.SURREALDB_PASS})
    await db.use(settings.SURREALDB_NS, settings.SURREALDB_DB)
    return db


async def setup_surreal_schema(db: AsyncSurrealConnection):
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
        "DEFINE FIELD embedding ON movie TYPE array<float>;",
    ]

    for query in queries:
        await db.query(query)
