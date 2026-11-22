# Elder Activity Agent

An AI agent that watches phone sensor data (movement, light, charging) for signs that an older person has had a normal, active day, and will send a daily summary plus alerts to family. No wearable needed: it uses the phone they already own.

> **Not a medical device or emergency service.** It reports activity patterns and can miss events, for example when the phone is left behind ([ADR 0002](docs/adr/0002-wellness-not-medical-device.md)).

**Status:** Phase 1 in progress. Phones stream data to the cloud, where it is authenticated per device and stored as per-minute summaries in Postgres.

- [Architecture](docs/architecture.md) (C4 diagrams of the system today)
- [Architecture Decision Records](docs/adr/README.md) (why it's built this way)
- [Threat model](docs/security/threat-model.md) and [security policy](SECURITY.md)

## Stack

| Layer | Choice |
|---|---|
| Language / packaging | Python 3.12, uv (lockfile for reproducible installs) |
| API | FastAPI |
| Database | Neon serverless Postgres, SQLAlchemy, Alembic migrations |
| LLM | Google Gemini Flash via `google-genai` |
| Data collection | Sensor Logger (Android) for now; own Kotlin app planned |
| Container | Docker (uv-based image, non-root user, migrations on start-up) |
| Hosting | Render free web service |
| CI/CD | GitHub Actions: tests against a Postgres container, dependency audit, gated deploys |
| Security tooling | Dependabot, CodeQL, pip-audit, GitHub secret scanning |

## API

| Endpoint | Auth | Description |
|---|---|---|
| `POST /ingest` | Device token (`Authorization` header) | Receives a batch from a phone; returns `status` (`ok` or `duplicate`) and counts of readings `stored`, `ignored` and `dropped` |
| `POST /chat` | `X-API-Key` | Tool-using agent; returns the answer and a trace of tool calls |
| `GET /health` | none | App status and deployed commit (never touches the database) |
| `GET /health/db` | `X-API-Key` | Database connectivity and schema revision |
| `GET /docs` | none | Interactive API documentation |

## Run locally

Install [uv](https://docs.astral.sh/uv/) and Docker, then:

```bash
uv sync
cp .env.example .env              # Windows: copy .env.example .env, then fill in real values

docker compose up -d              # throwaway Postgres for tests, on port 5433
uv run --env-file .env pytest -rs # all tests, including database tests
uv run pytest -rs                 # without a database: database tests are skipped

uv run --env-file .env uvicorn app.main:app --reload   # http://localhost:8000/docs
```

Tests never touch the production database: they use `TEST_DATABASE_URL` and refuse to run against Neon.

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini access and model name |
| `APP_API_KEY` | Required on `/chat` and `/health/db` |
| `DATABASE_URL` | Neon connection string (direct, not pooled) |
| `TEST_DATABASE_URL` | Local Docker database for tests |
| `DEVICE_TOKEN` | Optional; a phone's token, for `scripts/check_token.py` |

## Managing phones

```bash
uv run --env-file .env python scripts/register_device.py add --name "Test phone" --timezone Australia/Brisbane
uv run --env-file .env python scripts/register_device.py list
uv run --env-file .env python scripts/register_device.py revoke DEVICE_ID
```

`add` prints the device's token once; only a SHA-256 hash is stored. Put the token in the phone app's `Authorization` header.

## Delivery pipeline

1. Every change goes through a pull request; `main` is protected.
2. **test** runs pytest against a Postgres service container; **audit** runs `pip-audit` on the locked dependencies.
3. On `main`, after both pass, GitHub Actions triggers Render's deploy hook (Render auto-deploy is off).
4. The container runs `alembic upgrade head`, then starts the app. A failed migration means the new version never goes live.
5. The pipeline polls `/health` until it reports the exact commit that was pushed.

## Roadmap

Full plan: [docs/ROADMAP.md](docs/ROADMAP.md). User stories: [docs/backlog/working-version.md](docs/backlog/working-version.md).

- [x] **Phase 0:** tool-using agent, tests, Docker, CI/CD
- [x] **Phase 1, Stage A:** Postgres, migrations, database tests in CI
- [x] **Phase 1, Stage B:** per-device tokens, idempotent ingestion, per-minute summaries
- [x] Security baseline: threat model, supply-chain checks, request limits
- [x] Phone app: phone-sensor-logger, a separate product in a private repository (ADR 0023)
- [ ] **C2a:** typed settings, ruff, mypy, pre-commit
- [ ] **Backend SRS**
- [ ] **C2b:** `POST /v1/readings` implementing the logger's protocol v1
- [ ] **C3:** households, email sign-in, add a phone by QR code
- [ ] **D:** family web app: today and past days, contacts
- [ ] **E:** inactivity and phone-silent alerts by email and Telegram (**working version**)
- [ ] **Phases 2–5:** activity features, personal baseline, agent summaries, evaluation
- [ ] Before real users: legal review, Australian hosting, least-privilege logins, retention
