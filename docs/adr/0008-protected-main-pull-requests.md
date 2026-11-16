# 0008. Protect `main` and make every change through a pull request

- **Status:** Accepted
- **Date:** 2026-11-16

## Context

Pushing directly to `main` is quick but lets broken changes reach the branch that deploys to production.

## Decision

A GitHub ruleset on `main` requires a pull request, requires the `test` check to pass, and blocks force pushes. Each change is made on a short-lived branch named after the change (for example `feature/...`, `chore/...`).

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Protected main with PRs (chosen) | `main` is always deployable; every change is tested and documented in a PR | Slightly slower for a solo developer |
| Push directly to main | Fastest | No gate; mistakes go straight to production |
| Git Flow (develop and release branches) | Structured releases | Too heavy for a small service with continuous deployment |

## Consequences

Required approvals are set to zero while the developer works alone; raise this when collaborators join.

## When to revisit

Revisit when more people contribute.
