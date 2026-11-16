# 0016. Keep `/health` independent of the database

- **Status:** Accepted (implemented)
- **Date:** 2026-11-16

## Context

Render calls `/health` every few seconds while the service runs. Neon's free compute allowance is consumed whenever the database is awake.

## Decision

`/health` reports only that the app is running and which commit is deployed. A separate `/health/db` endpoint checks the database and is called manually or by monitoring at a low rate.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| App-only health check (chosen) | Database can sleep; health checks are cheap | A database outage does not fail the main health check |
| Health check queries the database | Detects database problems immediately | Keeps Neon awake constantly, using up the free compute allowance |

## Consequences

Database problems are detected through `/health/db` and through ingestion errors in logs.

## When to revisit

Revisit on a paid, always-on database.
