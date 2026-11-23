# Architecture Decision Records

This folder records the significant design decisions for the Elder Activity Agent: what was decided, why, which alternatives were considered, and their trade-offs. The format follows the widely used Architecture Decision Record (ADR) practice.

## How to use these records

- One decision per file, numbered in order.
- Add or update an ADR in the same pull request as the change it describes.
- Never delete an ADR. If a decision changes, write a new ADR and set the old one's status to "Superseded by NNNN".
- Status values: Proposed, Accepted, Superseded, Deprecated. "Accepted (planned)" means agreed but not yet built.

## Index

| No. | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-wellness-not-medical-device.md) | Position the product as wellness monitoring, not a medical device | Accepted |
| [0003](0003-python-fastapi-uv.md) | Use Python, FastAPI and uv | Accepted |
| [0004](0004-explicit-agent-loop.md) | Write the agent loop explicitly instead of using an agent framework | Accepted |
| [0005](0005-gemini-flash-llm.md) | Use Gemini Flash (free tier) as the LLM, and send it only anonymised summaries | Accepted |
| [0006](0006-render-hosting.md) | Host on Render's free tier, with a planned move to AWS | Accepted |
| [0007](0007-ci-cd-gated-deploys.md) | Deploy only through GitHub Actions, and verify the exact commit is live | Accepted |
| [0008](0008-protected-main-pull-requests.md) | Protect `main` and make every change through a pull request | Accepted |
| [0009](0009-secrets-management.md) | Keep secrets out of the repository, store each secret in as few places as possible, and verify rotations | Accepted |
| [0010](0010-sensor-logger-then-native-app.md) | Collect data with Sensor Logger first, and build a native Android app later | Accepted (native app part superseded by 0023) |
| [0011](0011-ingest-authentication.md) | Authenticate devices with tokens in the Authorization header, fail closed, and move to per-device hashed tokens | Accepted (implemented; a pairing flow for the native app is planned) |
| [0012](0012-neon-postgres.md) | Use Neon serverless Postgres | Accepted |
| [0013](0013-aggregate-at-ingestion.md) | Summarise sensor data per minute at ingestion, keep raw step totals, and make ingestion idempotent | Accepted (implemented) |
| [0014](0014-own-ingest-contract.md) | Define our own versioned ingest contract, with an adapter per data source | Accepted (Sensor Logger adapter implemented; `v1` endpoint in Stage C); the native app is phone-sensor-logger, 0023 |
| [0015](0015-migrations-at-startup.md) | Run Alembic migrations when the app starts, and move them into the pipeline later | Accepted (migrations at startup implemented; pipeline step planned) |
| [0016](0016-health-checks-avoid-database.md) | Keep `/health` independent of the database | Accepted (implemented) |
| [0017](0017-llm-resilience.md) | Bound every LLM call, and never let safety alerts depend on the LLM | Accepted (timeouts and retries implemented; fallback planned) |
| [0018](0018-testing-strategy.md) | Mock the LLM in tests, and test the database against real Postgres | Accepted (implemented) |
| [0019](0019-security-baseline.md) | Adopt a security baseline for accounts, secrets and database access | Accepted (secret scanning and two-factor authentication: manual settings; separate database logins planned) |
| [0020](0020-request-limits-and-rate-limiting.md) | Limit request size and batch size now, and add per-device rate limiting | Accepted (size limits implemented; rate limiting planned) |
| [0021](0021-supply-chain-security.md) | Check dependencies, code and images automatically | Accepted |
| [0022](0022-data-minimisation-retention-residency.md) | Collect the minimum, delete what isn't needed, and keep Australian users' data in Australia | Proposed (needs legal advice before real users) |
| [0023](0023-phone-sensor-logger-as-data-source.md) | Receive data from phone-sensor-logger through its protocol v1, and keep the logger a separate product | Accepted (`/v1/readings` built in step A) |
| [0024](0024-households-and-pairing.md) | Serve many households, and pair phones with the protocol v1 setup QR code | Accepted (data model and `scripts/household.py` built in step A; web pages in step D) |
| [0025](0025-family-web-app.md) | Build the family interface as a server-rendered, accessible web app that works well on phones | Accepted (to be built in step D; branding from `config/brand.toml`) |
| [0026](0026-rules-decide-llm-explains.md) | Let rules decide when to alert, let the LLM explain, and send alerts by email and Telegram | Accepted (built in step C; email through Resend) |
| [0027](0027-python-version-policy.md) | Run one Python version everywhere, and upgrade it deliberately | Accepted |
| [0028](0028-access-by-person-and-care-overview.md) | Give each signed-in user a set of people, with a care overview first | Accepted (to be built in step D) |

## Template for new records

```markdown
# NNNN. Title

- **Status:** Proposed
- **Date:** YYYY-MM-DD

## Context
What problem or constraint forces a decision?

## Decision
What was decided?

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|

## Consequences
What becomes easier or harder as a result?

## When to revisit
What would make this decision worth reopening?
```
