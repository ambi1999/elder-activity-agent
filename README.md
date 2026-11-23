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
| Web app | Server-rendered pages (Jinja2 templates), plain CSS, one small script; installable on a phone (ADR 0025) |
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
| `POST /v1/readings` | Device token (`Authorization: Bearer`) | Receives a [phone-sensor-logger protocol v1](protocol/README.md) batch; returns `status` (`ok` or `duplicate`) and counts `stored`, `ignored` and `dropped`; errors as Problem Details (401, 413, 422, 429, 503) |
| `POST /ingest` | Device token (`Authorization` header) | Sensor Logger batches, kept until no test phone uses it (ADR 0014) |
| `POST /chat` | `X-API-Key` | Tool-using agent; returns the answer and a trace of tool calls |
| `GET /health` | none | App status and deployed commit (never touches the database) |
| `GET /health/db` | `X-API-Key` | Database connectivity and schema revision |
| `GET /docs` | none | Interactive API documentation |
| `/`, `/signin`, `/people`, `/alerts`, `/settings` … | Session cookie (email sign-in link) | The family and care web app; see [Web app](#web-app) |

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

Before pushing, run the same checks as CI: `uv run ruff check .`, `uv run ruff format .` and `uv run mypy` (see [CONTRIBUTING.md](CONTRIBUTING.md)).

Behaviour is configured in [`config/settings.toml`](config/settings.toml): every setting is commented with its unit and allowed range, and any one can be overridden with an environment variable named `SECTION__KEY`, for example `PAIRING__PENDING_TOKEN_EXPIRY_MINUTES=60`.

Tests never touch the production database: they use `TEST_DATABASE_URL` and refuse to run against Neon.

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini access and model name |
| `APP_API_KEY` | Required on `/chat` and `/health/db` |
| `DATABASE_URL` | Neon connection string (direct, not pooled) |
| `TEST_DATABASE_URL` | Local Docker database for tests |
| `DEVICE_TOKEN` | Optional; a phone's token, for `scripts/check_token.py` |
| `JOBS_TOKEN` | Required on `/jobs/check-alerts`; same value as the GitHub secret `JOBS_TOKEN` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` | Telegram alerts (empty: logged only) |
| `RESEND_API_KEY` | Email alerts (empty: logged only) |
| `PHONE_TOKEN` | Optional; a phone's token, for `scripts/simulate_phone.py` |

## Households and phones

Until the family web app exists, households are set up from the command line ([ADR 0024](docs/adr/0024-households-and-pairing.md)):

```bash
uv run --env-file .env python scripts/household.py create --name "Family 1" --person Mum --timezone Australia/Brisbane
uv run --env-file .env python scripts/household.py add-phone --person PERSON_ID --name "Mum's phone"
uv run --env-file .env python scripts/household.py list
uv run --env-file .env python scripts/household.py revoke DEVICE_ID
uv run --env-file .env python scripts/household.py delete HOUSEHOLD_ID
```

Replace `PERSON_ID`, `DEVICE_ID` and `HOUSEHOLD_ID` with the IDs that `create` and `list` print. `delete` shows what will be removed and asks you to type the household's name: it permanently deletes the household's people, phones (their tokens stop working) and all their stored data.

`add-phone` prints the setup QR code once, in the terminal: scan it in phone-sensor-logger (Settings > Connection > Scan setup QR code), and the phone's owner agrees on its consent screen. The code holds the device token, so don't screenshot or share it. It works for `pairing.pending_token_expiry_minutes` (default 30) unless the phone's first data arrives sooner; after that the phone is active. Only a hash of the token is stored.

Phones that use the Sensor Logger app are registered directly:

```bash
uv run --env-file .env python scripts/register_device.py add --name "Test phone" --timezone Australia/Brisbane
uv run --env-file .env python scripts/register_device.py list
uv run --env-file .env python scripts/register_device.py revoke DEVICE_ID
```

`add` prints the device's token once; only a SHA-256 hash is stored. Put the token in the phone app's `Authorization` header.

## Alerts

The rules decide, the LLM only explains ([ADR 0026](docs/adr/0026-rules-decide-llm-explains.md)):

- **No activity:** no steps, screen use or walking for `inactive_hours` (default 4) during waking hours (default 08:00–21:00, the person's time), while the phone is still sending.
- **Phone silent:** no data for `silent_hours` (default 6), worded as a phone problem.

Each alert goes to the household's confirmed contacts by Telegram (with an "I'm checking" button) or email (with an "I'm checking" link), respecting each contact's quiet hours. It repeats every `resend_after_minutes` (default 60, at most `max_resends` times) until someone acknowledges it, and an "All clear" follows when activity resumes. The explanation comes from Gemini when it answers within `llm_timeout_seconds`, otherwise from a fixed template. Defaults are in `config/settings.toml` under `[alerts]`.

A GitHub Actions schedule (`.github/workflows/check-alerts.yml`) calls `POST /jobs/check-alerts` every 5 minutes.

**Contacts and settings from the command line** (the same as the web app's pages):

```bash
uv run --env-file .env python scripts/household.py add-contact --household HOUSEHOLD_ID --name Daughter --telegram
uv run --env-file .env python scripts/household.py add-contact --household HOUSEHOLD_ID --name Son --email son@example.com
uv run --env-file .env python scripts/household.py contacts --household HOUSEHOLD_ID
uv run --env-file .env python scripts/household.py quiet-hours CONTACT_ID --from 22:00 --to 07:00
uv run --env-file .env python scripts/household.py alert-settings --person PERSON_ID --waking 08:00-21:00 --inactive-hours 4
```

A Telegram contact opens the printed link and presses **Start**; an email contact opens the confirmation email's link and presses **Confirm**. Nothing is sent to a contact until then.

**Trying it without the logger app:** add a phone (`add-phone`), put its token in `.env` as `PHONE_TOKEN`, then send simulated data:

```bash
uv run --env-file .env python scripts/simulate_phone.py quiet --hours 5    # activity 5 hours ago, nothing since
uv run --env-file .env python scripts/simulate_phone.py active             # activity now: the alert clears
```

The next check (within 5 minutes, or press **Run workflow** on the `check-alerts` workflow) sends the alert. Outside the person's waking hours there is no inactivity alert; for a test at night, set `--waking 00:00-23:59` with `alert-settings`.

Without `TELEGRAM_BOT_TOKEN` or `RESEND_API_KEY`, messages are written to the log instead of sent ("logged only"), so everything works before the accounts exist.

## Web app

The family and care web app is served by the same service ([ADR 0025](docs/adr/0025-family-web-app.md), [ADR 0028](docs/adr/0028-access-by-person-and-care-overview.md)). Open the service's address (locally `http://localhost:8000/`) and sign in with an emailed link: there are no passwords.

- **Who sees what:** a user sees every person in the households they are a member of. Someone with one person goes straight to that person's day; someone with several (a nurse) gets the **care overview** first: needs attention (red), phone not sending (amber), all OK (green), each with an icon and words. Pages about anyone else answer 404.
- **Pages:** the overview, a person's day (status, steps, active hours, battery, when the phone last sent, steps by hour with a table version), past days (7), alerts with **I'm checking**, settings, help and about.
- **Managing (owners):** add a phone (the setup QR code is shown once, and the page says when the phone connects) or remove one; alert times; contacts (they confirm by email before alerts reach them); members (invite by email, as owner or viewer; remove); add a person, in a new household or one you own. Viewers see the same pages without the forms, and the server refuses their changes (403). Your own name is under **Settings → Profile**.
- **Accounts are invite only while testing.** An owner invites people from the household's **Members** page, or from the command line, as `owner` (may change settings) or `viewer`:

```bash
uv run --env-file .env python scripts/household.py add-member --household HOUSEHOLD_ID --email daughter@example.com --name Daughter --role owner
uv run --env-file .env python scripts/household.py members --household HOUSEHOLD_ID
uv run --env-file .env python scripts/household.py user --email nurse@example.com   # their households, roles and people
```

  They then sign in at `/signin` with that address. While Resend can only email your own address (no verified domain yet), print a one-time link for another user instead, and open it in their browser:

```bash
uv run --env-file .env python scripts/household.py signin-link --email nurse@example.com
```

  The link signs in as that user until it is used or expires, so treat it like a password.
- **Security:** sign-in links work once, for `web.signin_link_minutes` (15), and are stored only as hashes; requests are limited per address and per network; sessions are server-side, in a `__Host-` cookie (Secure, HttpOnly, SameSite=Lax), last `web.session_days` (30) and end at once on Sign out; every form carries a CSRF token and must come from this site; pages have a strict Content Security Policy and are never cached.
- **Brand:** company, product name, logo and colours come from [`config/brand.toml`](config/brand.toml) only; `tests/test_brand.py` checks the colours' contrast (WCAG 2.2 AA).
- **On a phone:** open the address in Chrome, then **⋮ → Add to home screen**, or in Safari **Share → Add to Home Screen**.

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
- [x] **Step A:** foundations (typed settings, ruff, mypy), `POST /v1/readings` for the logger's protocol v1, households and QR pairing by script
- [ ] **Step B (logger):** connect by QR with consent, uploads
- [x] **Step C:** inactivity and phone-silent alerts by Telegram and email (**working prototype**, tried with simulated phone data until logger step B)
- [x] **Step D1:** web app: email sign-in, access by set of people, care overview, a person's day, alerts with I'm checking, brand from configuration
- [x] **Step D2:** web app: past days, phones (add by QR), contacts, alert times, members and invitations, add a person
- [ ] **Backend SRS**, written from what was built
- [ ] **Phases 2–5:** activity features, personal baseline, agent summaries, evaluation
- [ ] Before real users: legal review, Australian hosting, least-privilege logins, retention
