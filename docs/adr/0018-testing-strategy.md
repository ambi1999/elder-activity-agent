# 0018. Mock the LLM in tests, and test the database against real Postgres

- **Status:** Accepted (database testing planned for Phase 1, Stage A)
- **Date:** 2026-11-16

## Context

Tests must be fast, free and reliable, yet catch real problems. Calling Gemini in tests would cost quota and be flaky. Database behaviour (transactions, conflicts, migrations) is easy to get wrong with fakes.

## Decision

Replace the Gemini call with a fake in tests. Run database tests against a real Postgres container: Docker Compose on the developer's computer, and a service container in GitHub Actions. Tests never touch the Neon production database.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Mock LLM, real Postgres (chosen) | Fast, free, deterministic for the model; realistic for the database | Docker needed locally |
| Call the real LLM in tests | End-to-end realism | Costs quota; flaky; slow |
| SQLite or fakes for the database | No Docker | Misses Postgres-specific behaviour |
| Test against Neon | Realistic | Risks production data; uses free allowances |

## Consequences

Model quality is evaluated separately with scenario tests (Phase 5) rather than unit tests.

## When to revisit

Revisit if an evaluation suite for the agent is added.
