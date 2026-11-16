# 0020. Limit request size and batch size now, and add per-device rate limiting

- **Status:** Accepted (size limits implemented; rate limiting planned)
- **Date:** 2026-11-17

## Context

`/ingest` is public. Very large requests could exhaust the 512 MB of memory on the free Render instance, and a misbehaving or stolen device could flood the service and fill the database. Render's free tier offers no request filtering.

## Decision

Reject request bodies over 1 MB (413) in a small middleware that also counts bytes as they arrive, and reject batches with more than 10,000 readings (422). A normal Sensor Logger batch is a few kilobytes. Next, add per-device rate limiting (for example a token bucket keyed by device ID), held in memory while there is a single instance.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Limits in the app (chosen) | No extra services; testable; works on the free tier | In-memory rate limits reset on restart and don't work across multiple instances |
| Edge protection (Cloudflare or a cloud WAF) in front of Render | Blocks attacks before they reach the app; also hides the origin | More setup; custom domain needed |
| Shared store for rate limits (Redis) | Works across instances | Extra paid service; not needed with one instance |
| No limits | Nothing to build | One bad request can crash the service |

## Consequences

Limits are deliberately generous so real phones are never affected. Rate limiting moves to a shared store or the edge if the API ever runs more than one instance.

## When to revisit

Revisit when moving to AWS (API Gateway has built-in throttling) or before real users.
