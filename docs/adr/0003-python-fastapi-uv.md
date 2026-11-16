# 0003. Use Python, FastAPI and uv

- **Status:** Accepted
- **Date:** 2026-11-16

## Context

The backend needs an HTTP API, LLM integration and data processing. The developer is most comfortable in Python, and the project should demonstrate modern, reproducible tooling.

## Decision

Python 3.12 with FastAPI for the API, and uv for dependency management with a committed lockfile (`uv.lock`). CI and the Docker image install from the lockfile with `uv sync --locked`.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| FastAPI | Automatic request validation and interactive API docs; async support; widely used | Fewer built-in features than Django (no admin, ORM) |
| Flask | Simple and well known | Validation and API docs need extra libraries |
| Django | Batteries included | Heavier than needed for an API-only service |
| uv (chosen) vs pip + requirements.txt | Lockfile gives identical installs everywhere; fast CI; installs Python itself | Newer tool; team members may need to learn it |
| Poetry | Mature lockfile workflow | Slower; more configuration |

## Consequences

Dependencies are added with `uv add`, never pip. CI fails if `uv.lock` is out of date, so local, CI and production cannot drift apart.

## When to revisit

Not expected to change.
