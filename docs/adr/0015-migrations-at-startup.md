# 0015. Run Alembic migrations when the app starts, and move them into the pipeline later

- **Status:** Accepted (to be implemented in Phase 1, Stage A)
- **Date:** 2026-11-16

## Context

Database structure must be version-controlled and changed safely. Running migrations in GitHub Actions would require the database password to be stored in GitHub as well as Render. Render's pre-deploy command appears to be a paid feature.

## Decision

Use Alembic migration files in Git. The container runs `alembic upgrade head` before starting the app. If a migration fails, the new version does not start, its health check fails, and the previous version keeps serving. Later, move migrations into the pipeline using a separate database login that can only change table structure, while the app's login can only read and write data.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| At startup (chosen for now) | Database password stays in one place; simplest | Failures appear in Render logs rather than as a pipeline step |
| Pipeline step with one login | Visible, separate step that blocks the deploy | Database password stored in two places |
| Pipeline step with separate least-privilege logins (planned) | Visible; each system holds only the permissions it needs | More setup |
| Render pre-deploy command | Designed for this | Paid feature |

## Consequences

Migrations must be backward compatible with the currently running version (expand and contract), because old and new code overlap during deploys. A CI test applies, reverts and re-applies all migrations.

## When to revisit

Revisit after Stage B, or when moving to AWS.
