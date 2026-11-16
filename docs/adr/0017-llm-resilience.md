# 0017. Bound every LLM call, and never let safety alerts depend on the LLM

- **Status:** Accepted (timeouts and retries implemented; fallback planned)
- **Date:** 2026-11-16

## Context

During development, the free Gemini tier sometimes hung or returned 504 errors. An alert system that waits forever, or fails because the model is unavailable, could delay a message to a worried family.

## Decision

Every Gemini call has a timeout and a limited number of retries, and the API returns a clear error instead of crashing. Simple rules decide when a situation is urgent; the LLM only adds judgement and wording. If the LLM fails, a plain-text alert is still sent.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Rules decide, LLM explains, with fallback (chosen) | Alerts are reliable and testable; the LLM improves quality without being a single point of failure | Two paths to build and test |
| LLM decides everything | Least code | Model outages or mistakes block or corrupt safety alerts |
| No LLM in alerts | Most predictable | Less helpful, less natural messages |

## Consequences

Alert logic is tested with simulated scenarios (Phase 5) independently of the model.

## When to revisit

Not expected to change.
