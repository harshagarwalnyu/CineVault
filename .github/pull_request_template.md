## Summary

- What changed:
- Why this change is needed:

## Scope

- Files/areas touched:
- Out-of-scope explicitly left unchanged:

## Verification

- [ ] `uv run ruff check backend`
- [ ] `uv run mypy backend`
- [ ] `uv run pytest -m "unit or integration" --cov=backend --cov-report=term-missing`
- [ ] `bun run lint` (from `frontend/`)
- [ ] `bun run build` (from `frontend/`)

## API / Contract Impact

- [ ] No API contract changes
- [ ] Backward-compatible API changes
- [ ] Breaking API changes (include migration notes)

## Risk and Rollback

- Risk level: Low / Medium / High
- Rollback plan:

## Reviewer Focus

- Please verify:
1. Correctness and behavior regressions
2. Security and auth implications
3. Performance impact
4. Test coverage for new logic
