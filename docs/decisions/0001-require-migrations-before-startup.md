# ADR 0001: Require Migrations Before API Startup

## Context

Runtime schema initialization can diverge environments and bypass rollback safety.

## Decision

The API startup will fail when required tables are missing unless `AUTO_INIT_DB=true` is explicitly set for local development.
All schema changes must be shipped through Alembic migrations.

## Consequences

1. Production behavior is deterministic and auditable.
2. Deployment pipelines must run migrations before app startup.
3. Local onboarding may require one extra command but gains parity with production.
