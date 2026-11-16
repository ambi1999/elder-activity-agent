# 0007. Deploy only through GitHub Actions, and verify the exact commit is live

- **Status:** Accepted
- **Date:** 2026-11-16

## Context

Render can deploy automatically on every push, which would let untested code reach production.

## Decision

Turn off Render's auto-deploy. A GitHub Actions workflow runs tests on every push and pull request; on `main` only, after tests pass, it triggers Render through a secret deploy hook, then polls `/health` until it reports the exact commit that was pushed (`RENDER_GIT_COMMIT`).

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Actions-gated deploy hook (chosen) | Untested code cannot deploy; the pipeline confirms the new version is live | Deploy hook URL is a secret to manage; polling adds a few minutes |
| Render auto-deploy | Simplest | Deploys even if tests fail |
| Health check without commit verification | Simpler | Passes even if the old version is still running |

## Consequences

A failed test, a failed build or a version that never goes live all show as a red pipeline.

## When to revisit

Revisit when moving to AWS (the same pattern applies with different tooling).
