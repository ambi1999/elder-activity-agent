# 0012. Use Neon serverless Postgres

- **Status:** Accepted
- **Date:** 2026-11-16

## Context

The system needs a database that is free without a card, survives for the weeks of history that baseline learning requires, and can grow into production.

## Decision

Use Neon's free Postgres plan, connected through a single `DATABASE_URL` setting. Code uses standard Postgres only, so the provider can change by changing that setting.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Neon (chosen) | Free without a card; no expiry; scales to zero; database branching; upgrade without migration | Small free storage and compute allowances; first query after idle is slower |
| Render Postgres free | Same platform as the app | Free databases expire after a limited period, losing history |
| SQLite file | Simplest | Files are wiped on redeploy on Render |
| Supabase | Postgres with extras (auth, storage) | More than needed; free projects pause when inactive |
| Time-series database (TimescaleDB, InfluxDB) | Built for sensor data | Extra complexity; free hosted options are limited |

## Consequences

Connections must handle Neon closing idle connections (connection checks before use). Nothing should keep the database awake unnecessarily (see ADR 0016).

## When to revisit

Revisit if storage or compute exceeds the free allowance, or when moving to AWS.
