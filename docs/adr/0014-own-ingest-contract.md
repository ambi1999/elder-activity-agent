# 0014. Define our own versioned ingest contract, with an adapter per data source

- **Status:** Accepted (Sensor Logger adapter implemented; `v1` endpoint in Stage C2b, implementing phone-sensor-logger's protocol v1: [ADR 0023](0023-phone-sensor-logger-as-data-source.md))
- **Date:** 2026-11-16

## Context

Sensor Logger's message format is designed for researchers, not for this product, and it will be replaced by a native app. If the rest of the system used Sensor Logger's format directly, switching sources would mean rewriting storage and analysis.

## Decision

Define a `v1` format (`POST /v1/readings`) using the product's own sensor names (`steps_total`, `light_lux`, `battery`) and a batch identity (`device_id`, `session_id`, `batch_seq`). It also allows per-minute summaries computed on the phone. Sensor Logger is supported through an adapter on `/ingest` that translates into the internal model. Everything after the adapter sees only the internal model.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Own versioned contract plus adapters (chosen) | Sources can be swapped without touching storage or analysis; the native app has a clear specification | Extra translation layer; versioning must be managed |
| Use Sensor Logger's format everywhere | Least work now | Ties the whole system to a third-party format |
| Generic event schema with free-form JSON | Very flexible | Weak validation; harder to reason about |

## Consequences

Step totals are treated as running totals that can reset, which covers both Sensor Logger recordings and Android's hardware step counter (which resets on reboot). The native app sends `v1` directly.

## When to revisit

Breaking changes require a new version (`v2`) while `v1` keeps working.
