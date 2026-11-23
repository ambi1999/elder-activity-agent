# 0023. Receive data from phone-sensor-logger through its protocol v1, and keep the logger a separate product

- **Status:** Accepted
- **Date:** 2026-11-22

## Context

ADR 0010 chose Sensor Logger (a third-party app) to prove the pipeline, with "our own Kotlin app" to follow. That app now exists as a separate project, **phone-sensor-logger** (Iteration 1 released as v0.2.0): a generic Android logger with an open upload protocol, `phone-sensor-logger/v1`, meant to be used by many receivers and sold separately. This service is its first receiver.

The question is how tightly the two are coupled: whether the logger knows about households, families and alerts, or only about its protocol.

## Decision

- **The logger stays generic.** It knows only protocol v1: an HTTPS endpoint, a device token, batches of readings and per-minute summaries, and the provisioning QR format. Households, people, family members and alerts exist only here.
- **This service implements protocol v1** at `POST /v1/readings` (step A), with a vendored, version-pinned copy of the protocol's schemas and examples and contract tests that run every example through the endpoint. The Sensor Logger adapter on `/ingest` stays until no test phone uses it, then is removed.
- **Phones use the logger's `activity` profile** (steps, light, battery, screen, activity, motion). It has no location; any location reading that arrives anyway is ignored and never stored (ADR 0022).
- **Setup uses the protocol's QR format** (see ADR 0024 for pairing).
- This supersedes ADR 0010's plan for an own app inside this project, and ADR 0014's "native app" is phone-sensor-logger.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Generic logger, receiver-specific logic here (chosen) | The logger can be reused and sold; each side is tested on its own against the protocol | Two repositories and a contract to keep in step |
| One app that is both logger and family app | One install | The logger can't be reused; families would need the older person's phone to see anything |
| Keep Sensor Logger | No app work | Third-party format, battery use, no setup by QR; not suitable for families (ADR 0010) |

## Consequences

The contract tests are the boundary: a protocol change is a new protocol version in the logger repository, then a vendored update here. The family-facing parts (accounts, web app, alerts) are built here without touching the phone.

## When to revisit

If another receiver needs something only this one has (move it into the protocol), or if protocol v2 is published.
