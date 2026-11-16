# 0022. Collect the minimum, delete what isn't needed, and keep Australian users' data in Australia

- **Status:** Proposed (needs legal advice before real users)
- **Date:** 2026-11-17

## Context

Activity patterns of older people are likely to count as health information, which is sensitive information under Australia's Privacy Act. They also reveal when someone is home or alone, which is a physical safety risk. The database currently runs in AWS us-west-2 (Oregon), and data is kept indefinitely.

## Decision

Collect only what the product needs: no location, microphone or camera; per-minute summaries instead of raw readings. Proposed retention: raw step totals for 90 days, per-minute summaries for 13 months (enough for a year of baseline comparison), and batch records for 30 days, enforced by a scheduled clean-up job. For Australian users, store data in Australia (Neon offers a Sydney region; Render has no Australian region, so hosting moves to an Australian region when migrating to AWS). Each monitored person gives informed consent, and the privacy policy explains all of the above. Confirm with legal advice before onboarding real users.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Minimise, expire and localise (proposed) | Less to lose in a breach; easier compliance; builds trust | Clean-up jobs to run; old data unavailable for later analysis |
| Keep everything forever | Maximum flexibility | Larger breach impact; likely non-compliant; storage cost |
| Keep data overseas with contractual safeguards | No migration | Extra legal obligations for cross-border disclosure |

## Consequences

Requires a scheduled job (not available on the free tier without workarounds) and a database region move before real users. Retention periods may change after legal advice.

## When to revisit

Before real users, after legal advice.
