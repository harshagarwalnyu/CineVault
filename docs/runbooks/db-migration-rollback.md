# Database Migration and Rollback

## Apply Migration

1. `uv run alembic -c alembic.ini upgrade head`
2. Verify table presence and row counts.
3. Start API only after migration succeeds.

## Rollback Procedure

1. Identify current revision: `uv run alembic -c alembic.ini current`
2. Downgrade one revision: `uv run alembic -c alembic.ini downgrade -1`
3. Validate schema and critical queries.

## Safety Rules

1. Never deploy application code requiring a schema that has not been migrated.
2. Do not run implicit schema initialization in production.
3. Keep migration scripts idempotent where possible.
