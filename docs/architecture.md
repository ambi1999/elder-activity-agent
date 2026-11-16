# Architecture

How the system looks **today** (end of Phase 1, Stage B). For *why* it looks like this, see the [Architecture Decision Records](adr/README.md). Diagrams follow the [C4 model](https://c4model.com): each level zooms in further.

Dashed lines show parts that are planned but not built yet.

## 1. System context (C4 level 1)

```mermaid
flowchart TB
    elder["👵 Older person<br/>carries an Android phone"]
    family["👨‍👩‍👧 Family member<br/>receives summaries and alerts"]
    dev["🧑‍💻 Developer<br/>builds, deploys, registers phones"]

    system["Elder Activity Agent<br/>collects phone activity data, learns a personal routine,<br/>and tells family when something looks unusual"]

    gemini["Google Gemini API<br/>LLM"]
    telegram["Telegram<br/>messaging"]

    elder -- "phone sends sensor summaries" --> system
    system -. "daily summaries and alerts (planned)" .-> family
    dev -- "deploys and manages" --> system
    system -- "tool-calling agent" --> gemini
    system -. "sends messages (planned)" .-> telegram
```

## 2. Containers (C4 level 2)

```mermaid
flowchart TB
    subgraph phone["Android phone"]
        sl["Sensor Logger app<br/>(later: our own Kotlin app)"]
    end

    subgraph render["Render (free web service, Docker)"]
        api["FastAPI application<br/>/ingest · /chat · /health · /health/db"]
    end

    neon[("Neon Postgres<br/>AWS us-west-2")]
    gemini["Gemini API"]

    subgraph github["GitHub"]
        repo["Repository<br/>protected main"]
        actions["GitHub Actions<br/>test · audit · deploy"]
    end

    devpc["Developer computer<br/>VS Code, uv, Docker (test DB),<br/>register_device.py"]

    sl -- "HTTPS POST /ingest<br/>Authorization: device token" --> api
    api -- "SQL over TLS" --> neon
    api -- "HTTPS" --> gemini
    devpc -- "git push / pull requests" --> repo
    repo --> actions
    actions -- "deploy hook, then poll /health" --> api
    devpc -- "SQL over TLS (device admin)" --> neon
```

| Container | Technology | Responsibility |
|---|---|---|
| Phone app | Sensor Logger (temporary) | Records light, battery and steps; pushes a batch every second |
| API | Python 3.12, FastAPI, SQLAlchemy, Docker on Render | Authenticates devices, validates and stores data, runs the agent |
| Database | Neon serverless Postgres, Alembic migrations | Devices, batches, step totals, per-minute summaries |
| LLM | Gemini Flash | Agent reasoning and wording |
| CI/CD | GitHub Actions | Tests against a Postgres container, dependency audit, gated deploys |

## 3. Components inside the API (C4 level 3)

```mermaid
flowchart LR
    req["HTTP request"] --> limits["limits.py<br/>1 MB body limit"]
    limits --> main["main.py<br/>routes and auth"]

    main -- "/ingest" --> devices["devices.py<br/>token hash lookup"]
    main -- "/ingest" --> adapter["sensor_logger.py<br/>adapter"]
    adapter --> model["readings.py<br/>internal model"]
    main -- "/ingest" --> storage["storage.py<br/>save_batch()"]
    storage --> model

    main -- "/chat" --> agent["agent.py<br/>tool-calling loop"]
    agent --> tools["tools.py"]

    devices --> db["db.py<br/>connection pool"]
    storage --> db
    main -- "/health/db" --> db
```

The adapter is the only code that knows Sensor Logger's format ([ADR 0014](adr/0014-own-ingest-contract.md)). Replacing the phone app means replacing that one file.

## 4. What happens when a batch arrives

```mermaid
sequenceDiagram
    participant P as Phone
    participant A as API (/ingest)
    participant D as Neon

    P->>A: POST /ingest (Authorization: token, JSON batch)
    A->>A: Reject if body > 1 MB or > 10,000 readings
    A->>D: Find active device by SHA-256(token)
    alt unknown or revoked token
        A-->>P: 401
    end
    A->>A: Adapter: translate, ignore unknown sensors
    A->>D: BEGIN
    A->>D: INSERT batch ID (skip if already seen)
    alt batch already processed
        A-->>P: 200 {"status": "duplicate"}
    end
    A->>A: Drop stale (>10 min old) and future (>5 min) readings
    A->>D: INSERT step totals
    A->>D: UPSERT per-minute light and battery summaries
    A->>D: UPDATE device last_seen_at
    A->>D: COMMIT (or ROLLBACK on any error → 503, phone retries)
    A-->>P: 200 {"status": "ok", "stored", "ignored", "dropped"}
```

## 5. Data model

```mermaid
erDiagram
    devices ||--o{ ingested_batches : sends
    devices ||--o{ step_readings : records
    devices ||--o{ minute_summary : summarised_in

    devices {
        uuid id PK
        text name
        text timezone
        text token_hash "SHA-256, unique"
        timestamptz last_seen_at
        timestamptz revoked_at
    }
    ingested_batches {
        uuid device_id PK
        text session_id PK
        bigint batch_seq PK
        int reading_count
    }
    step_readings {
        uuid device_id PK
        text session_id PK
        timestamptz recorded_at PK
        int steps_total "running total"
    }
    minute_summary {
        uuid device_id PK
        timestamptz minute PK
        float light_sum
        int light_samples
        float light_max
        real battery_level
        bool battery_charging
        timestamptz battery_at
        int readings
    }
```

All timestamps are stored in UTC; each device's timezone is used when showing data.

## 6. Delivery pipeline

```mermaid
flowchart LR
    branch["Feature branch"] --> pr["Pull request"]
    pr --> test["test<br/>pytest + Postgres container"]
    pr --> audit["audit<br/>pip-audit"]
    test --> merge{"Merge to main"}
    audit --> merge
    merge --> t2["test + audit again"]
    t2 --> hook["Trigger Render deploy hook"]
    hook --> mig["Container starts:<br/>alembic upgrade head"]
    mig --> verify["Poll /health until<br/>the new commit is live"]
```

Dependabot opens pull requests for dependency, GitHub Actions and Docker image updates; CodeQL scans the code on GitHub.

## 7. Quality goals and where they're addressed

| Goal | How | Decisions |
|---|---|---|
| Reliability | Idempotent batches, transactions, retry-safe errors, LLM timeouts | [0013](adr/0013-aggregate-at-ingestion.md), [0017](adr/0017-llm-resilience.md) |
| Security | Per-device hashed tokens, request limits, secrets hygiene, supply-chain checks | [0011](adr/0011-ingest-authentication.md), [0019](adr/0019-security-baseline.md)–[0021](adr/0021-supply-chain-security.md) |
| Privacy | Data minimisation, summaries only to the LLM | [0005](adr/0005-gemini-flash-llm.md), [0022](adr/0022-data-minimisation-retention-residency.md) |
| Cost (free tier) | Aggregation at ingest, database-free health check | [0006](adr/0006-render-hosting.md), [0012](adr/0012-neon-postgres.md), [0016](adr/0016-health-checks-avoid-database.md) |
| Replaceable parts | Own ingest contract with adapters; model name as configuration | [0014](adr/0014-own-ingest-contract.md) |

## 8. Not built yet

- `v1` ingest contract (Stage C) and data view endpoint (Stage D)
- Our own Android app
- Activity features, personal baseline, agent decisions and Telegram alerts (Phases 2–4)
- Rate limiting, least-privilege database logins, retention jobs
