# ADR 0002: Enforce CI Quality Gates

## Context

Manual verification is error-prone and allows regressions to merge.

## Decision

Introduce required CI gates for backend (ruff, mypy, unit/integration tests), frontend (lint, build), and an e2e smoke check.

## Consequences

1. Merge latency increases slightly but quality and release confidence improve.
2. Contributors must satisfy baseline checks before merge.
3. Operational incidents from preventable regressions should decrease.
