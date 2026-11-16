# 0021. Check dependencies, code and images automatically

- **Status:** Accepted
- **Date:** 2026-11-17

## Context

Most of the code running in production comes from third-party packages, base images and GitHub Actions. A vulnerable or malicious update could leak secrets or data. Updates also need to keep flowing, or the project falls behind on security fixes.

## Decision

Lock all Python dependencies (`uv.lock`). Run `pip-audit` against the locked dependencies in CI; a known vulnerability blocks the deploy. Enable Dependabot alerts and weekly update pull requests for Python packages, GitHub Actions and Docker images, so updates go through the same tests as any change. Enable CodeQL code scanning (GitHub's default setup). Pin the `uv` image used in the Dockerfile to a specific version instead of `latest`.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Automated checks in CI and GitHub (chosen) | Free for public repositories; issues found before deploy; updates arrive as tested pull requests | Occasional noisy alerts and update pull requests to review |
| Manual updates and reviews | No noise | Easy to forget; vulnerabilities go unnoticed |
| Commercial scanners (Snyk and similar) | Richer reports | Cost; overlap with free tools |
| Pin GitHub Actions to commit SHAs | Strongest protection against a compromised action tag | Harder to read and update; planned once Dependabot is in place |

## Consequences

Dependabot pull requests must pass CI like any other change. Container image scanning (for example Trivy) and SHA-pinned actions are the next steps.

## When to revisit

Revisit if alert volume becomes unmanageable, or when moving to AWS (Amazon ECR image scanning).
