# Incident Response Runbook

## Severity Matrix

1. SEV-1: Full outage or data integrity risk. Response target: under 15 minutes.
2. SEV-2: Partial outage or major degradation. Response target: under 60 minutes.
3. SEV-3: Non-critical degradation. Response target: under 4 hours.

## Immediate Triage

1. Confirm impact with `/health` and `/admin/health/full`.
2. Capture failing endpoints, error rate, and p95 latency.
3. Identify blast radius (all users, region, endpoint class).

## Containment

1. Roll back latest deployment if SLO breach persists for 10 minutes.
2. Disable risky feature flags and route to stable path.
3. Scale down traffic if downstream dependencies are unstable.

## Communication

1. Open incident channel and assign commander.
2. Publish updates every 15 minutes (SEV-1/2) and every 60 minutes (SEV-3).
3. Record timeline with exact timestamps.

## Recovery

1. Verify `/health` and `/admin/slo` are stable.
2. Confirm error rate and latency are back within thresholds.
3. Announce recovery and monitor for 30 minutes before closure.

## Post-Incident

1. Publish postmortem in `docs/incidents/` within 48 hours.
2. Track corrective actions with owners and deadlines.
