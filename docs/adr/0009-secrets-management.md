# 0009. Keep secrets out of the repository, store each secret in as few places as possible, and verify rotations

- **Status:** Accepted
- **Date:** 2026-11-16

## Context

The system uses several secrets: the Gemini API key, the API key for `/chat`, the ingest token, the database URL and the deploy hook URL. Secrets have already appeared in shared logs and screenshots during development, which required rotation.

## Decision

Local secrets live in `.env` (ignored by Git); `.env.example` holds placeholders only. Production secrets live in Render environment variables; GitHub holds only what the pipeline needs (the deploy hook and service URL). Every client gets its own credential. After rotating a secret, `scripts/check_token.py` verifies the old value is rejected and the new one works.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Per-environment stores (chosen) | Simple; each secret has few copies | Manual rotation |
| Secrets in the repository | Convenient | Leaks permanently into Git history |
| Dedicated secret manager (Vault, cloud secret managers) | Central rotation and auditing | Extra service; cloud options needed a card |

## Consequences

If a secret is ever committed or shared, it is revoked and replaced, not just deleted. Logs never print secrets.

## When to revisit

Revisit when moving to AWS (AWS Secrets Manager or Parameter Store).
