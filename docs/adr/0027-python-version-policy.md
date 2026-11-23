# 0027. Run one Python version everywhere, and upgrade it deliberately

- **Status:** Accepted
- **Date:** 2026-11-23

## Context

Python appears in several places: `.python-version` (what uv uses locally and in CI), the Docker base image (what runs in production), `requires-python` in `pyproject.toml`, and the target versions of ruff and mypy. If they drift apart, CI can pass on one version while production runs another. Dependabot offered to move the Docker image from 3.12 to 3.15 on its own (PR #11), which would have done exactly that; ADR 0021's ignore rule stopped it.

Newer Python versions bring speed and typing improvements, but a few dependencies (database drivers, the Gemini SDK) can lag behind a new release.

## Decision

- **One version, currently Python 3.12**, in all of: `.python-version`, the `Dockerfile` base image (`python:3.12-slim`), ruff's `target-version` and mypy's `python_version`. `requires-python = ">=3.12"` states the minimum the code supports.
- **Patch releases** (3.12.x) arrive automatically through the Docker image and uv.
- **Minor upgrades are deliberate**, at most once a year, in one pull request that changes every place above together, after checking that all locked dependencies publish wheels for the new version. Dependabot is told to ignore minor and major Python updates (ADR 0021).
- **Next upgrade:** Python 3.14, tracked as a `tech-debt` issue "Upgrade to Python 3.14".

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| One pinned version, deliberate upgrades (chosen) | CI tests what runs in production; upgrades are planned | Falls behind the newest Python for a while |
| Always the newest Python | Newest features | Dependencies may not support it yet; surprise breakage |
| Test several versions in CI | Catches version problems early | Slower CI for a service that only ever runs one version |

## Consequences

The step A tooling (ruff, mypy) reads its target version from configuration that must change with every upgrade; the upgrade pull request's checklist includes them.

## When to revisit

When 3.12 approaches end of security support (October 2028), or if a dependency needs a newer version.
