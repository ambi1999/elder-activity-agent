# 0010. Collect data with Sensor Logger first, and build a native Android app later

- **Status:** Accepted (the native app part is superseded by [ADR 0023](0023-phone-sensor-logger-as-data-source.md): the app is the separate phone-sensor-logger project)
- **Date:** 2026-11-16

## Context

The system needs all-day sensor data from an Android phone. Reliable background collection on Android is hard: the system stops background apps, and some brands stop them even more aggressively. The developer wants to stay in Python for now but eventually own the collector.

## Decision

Use the Sensor Logger app's HTTP push to validate the whole pipeline. Build a native Kotlin Android app after the backend's own ingest contract exists (ADR 0014). While on Sensor Logger, testing is limited to at most two phones, and recording runs only for short periods.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Sensor Logger first (chosen) | Real data within days; background collection already solved; problems are isolated to the backend | Dependency on a third-party app; batch period and sampling rates are fixed on the free version (1-second pushes, about 5 light readings per second); high battery use |
| Native Android app now (Kotlin) | Full control; battery-efficient options (hardware step counter, activity recognition, batching) | Weeks before any data flows; two unknown systems to debug at once |
| Python mobile frameworks (Kivy, BeeWare) | Same language | Poor support for reliable background services |
| Cross-platform (Flutter, React Native) | One codebase for Android and iOS | Background sensor work still needs native code |

## Consequences

The backend must not depend on Sensor Logger's format beyond a single adapter. Family rollout waits for the native app because of battery use and data volume.

## When to revisit

Revisit when the ingest contract (ADR 0014) and Phase 1 storage are complete.
