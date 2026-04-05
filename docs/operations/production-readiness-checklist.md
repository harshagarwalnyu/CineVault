# Production Readiness Checklist

## Release Gates

1. CI pipeline green for backend and frontend.
2. Migration applied successfully.
3. Security checks pass with no critical findings.

## Runtime Health

1. `/health` reports healthy and engine loaded.
2. `/admin/health/full` reports database, redis, and search dependencies healthy.
3. `/admin/slo` error rate below 1% and p95 latency within agreed threshold.

## Rollback

1. Previous stable image/tag available.
2. Database rollback command validated.
3. Feature-flag kill switches available for risky paths.

## Sign-Off

1. Engineering owner:
2. Reviewer:
3. Timestamp:
