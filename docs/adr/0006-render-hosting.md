# 0006. Host on Render's free tier, with a planned move to AWS

- **Status:** Accepted
- **Date:** 2026-11-16

## Context

Hosting must be free and must not require a credit card. Google Cloud, AWS, Azure and Oracle all asked for a card (AWS's newer no-card option is not available to every account and expires after six months).

## Decision

Deploy the Docker container to a Render free web service. Plan a migration to AWS (for example Lambda plus a scheduler) once the project needs always-on scheduled jobs, as a deliberate later step.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Render free (chosen) | No card; deploys the existing Dockerfile; no expiry | Sleeps after 15 minutes idle (cold starts of up to a minute); 750 instance hours and limited bandwidth per month |
| Google Cloud Run | Generous free tier; same ecosystem as Gemini | Requires a card |
| AWS free plan | Most in-demand cloud for jobs | Card may be required; free plan ends after six months |
| Railway, Koyeb, Hugging Face Spaces | Simple | Limited credits, card holds or Docker support moved to paid plans |
| Own computer | Free | Not reliable; ruled out by the developer |

## Consequences

Cold starts must be tolerated (wake the service before demos). Scheduled checks cannot rely on an always-on process while on the free tier. Production use needs a paid always-on instance.

## When to revisit

Revisit when scheduled jobs become essential (Phase 3 or 4) or before real users.
