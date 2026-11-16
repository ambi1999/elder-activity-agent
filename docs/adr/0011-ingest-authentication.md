# 0011. Authenticate devices with tokens in the Authorization header, fail closed, and move to per-device hashed tokens

- **Status:** Accepted (header token implemented; per-device tokens planned)
- **Date:** 2026-11-16

## Context

`/ingest` is a public URL. The first version accepted a token in the URL query string, which leaked into server logs and shared screenshots.

## Decision

Tokens are accepted only in the `Authorization` header (with or without `Bearer`). If no token is configured on the server, all requests are rejected (fail closed). Comparisons are constant-time. Next, each phone gets its own random token; the database stores only a SHA-256 hash, and a phone can be revoked on its own. Phones are identified by their token, not by Sensor Logger's device ID, which can change on reinstall.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Per-device tokens in the header (chosen) | No secrets in logs; revoke one phone at a time; works for any client | Token must be entered on each phone; a pairing flow is needed later |
| Token in the URL | Works with any client | Leaks into logs, history and screenshots |
| One shared token | Simplest | Losing one phone means changing every phone |
| OAuth or user accounts | Standard for consumer apps | Too much for an MVP; needed later for family dashboards |

## Consequences

Random tokens with high entropy can be stored as plain SHA-256 hashes; slow password hashing is not needed because they cannot be guessed.

## When to revisit

Revisit when the native app adds a pairing flow or user accounts.
