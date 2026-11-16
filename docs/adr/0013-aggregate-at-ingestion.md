# 0013. Summarise sensor data per minute at ingestion, keep raw step totals, and make ingestion idempotent

- **Status:** Accepted (implemented)
- **Date:** 2026-11-16

## Context

Sensor Logger sends around 600,000 readings per phone per day. Storing them all would fill Neon's free storage within days. Real data also showed that batches arrive late and out of order, that step counts are running totals that reset each recording, and that the first pedometer reading can carry a timestamp hours old.

## Decision

Store one `minute_summary` row per phone per minute (light sum, count and maximum; latest battery state; reading count). Store raw step running totals, which are sparse, and calculate steps per minute in queries. Record each processed batch ID in `ingested_batches` so a resent batch is skipped. Order everything by the time a reading was recorded, never by arrival time. Ignore unknown sensors. Drop readings stamped more than 10 minutes before the newest reading in their batch, or more than 5 minutes in the future. Each batch is saved in one transaction.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Aggregate per minute at ingestion (chosen) | Over 99% less storage; fast queries; late data merges correctly | Raw detail is lost; new metrics only apply to future data |
| Store every raw reading | Nothing lost | Fills free storage in days; slow queries |
| Store raw, aggregate later in batch jobs | Flexible | Needs storage and a scheduler that the free tier lacks |
| Calculate step differences on arrival | Simpler queries | Breaks when batches arrive out of order |

## Consequences

The summary design must be compatible with the native app sending pre-computed minute summaries. Idempotency lets clients retry safely.

## When to revisit

Revisit if new analysis needs higher-resolution data.
