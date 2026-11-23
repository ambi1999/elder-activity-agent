# Architecture

Sections 1 to 8 show how the system looks **today** (end of Phase 1, Stage B). [Section 9](#9-target-architecture-the-working-version) shows the **target for the working version** (steps A to D in the [roadmap](ROADMAP.md)). For *why* it looks like this, see the [Architecture Decision Records](adr/README.md). Diagrams follow the [C4 model](https://c4model.com): each level zooms in further.

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

- Protocol v1 endpoint, households and command-line pairing (step A), replacing the Sensor Logger adapter
- Rules, alerts by email and Telegram (step C)
- Sign-in and the family web app (step D)
- Activity features, personal baseline, agent summaries (Phases 2–4)
- Least-privilege database logins, retention jobs, row-level security

## 9. Target architecture: the working version

Decisions: [0023](adr/0023-phone-sensor-logger-as-data-source.md) (data source), [0024](adr/0024-households-and-pairing.md) (households and pairing), [0025](adr/0025-family-web-app.md) (web app), [0026](adr/0026-rules-decide-llm-explains.md) (alerts). User stories: [backlog/working-version.md](backlog/working-version.md).

### 9.1 System context

```mermaid
flowchart TB
    elder["👵 Monitored person<br/>carries an Android phone<br/>with phone-sensor-logger"]
    family["👨‍👩‍👧 Family members<br/>(owners, viewers)<br/>on their own phones or computers"]
    contacts["📨 Alert contacts"]
    dev["🧑‍💻 Developer"]

    system["Elder Activity Agent<br/>stores activity per household, shows the day,<br/>and alerts when something looks unusual"]

    email["Transactional email API"]
    telegram["Telegram Bot API"]
    gemini["Google Gemini API"]

    elder -- "protocol v1 batches<br/>(after consent on the phone)" --> system
    family -- "web app (PWA):<br/>sign in, add phone, view, settings" --> system
    system -- "sign-in links, alerts" --> email
    system -- "alerts" --> telegram
    email --> contacts
    telegram --> contacts
    system -- "explanations from summaries" --> gemini
    dev -- "deploys and operates" --> system
```

### 9.2 Containers

```mermaid
flowchart TB
    subgraph phone["Monitored person's phone"]
        logger["phone-sensor-logger<br/>(Kotlin, separate product)"]
    end
    subgraph fam["Family member's device"]
        browser["Browser / installed PWA"]
    end

    subgraph render["Render (Docker)"]
        api["FastAPI service<br/>/v1/readings · web pages · /jobs/check-alerts<br/>/chat · /health"]
    end

    neon[("Neon Postgres")]
    gemini["Gemini API"]
    email["Email API"]
    tg["Telegram Bot API"]
    sched["GitHub Actions schedule<br/>(every 5 minutes)"]

    logger -- "HTTPS POST /v1/readings<br/>Bearer device token" --> api
    browser -- "HTTPS, session cookie,<br/>HTML + HTMX" --> api
    sched -- "POST /jobs/check-alerts<br/>job token" --> api
    cli["household.py (developer, steps A–C)<br/>households, contacts, QR in terminal"] -- "SQL over TLS" --> neon
    api -- "SQL over TLS" --> neon
    api -- "HTTPS" --> gemini
    api -- "HTTPS" --> email
    api -- "HTTPS" --> tg
```

### 9.3 Components

```mermaid
flowchart LR
    subgraph ingest["Ingest"]
        v1["v1_readings.py<br/>protocol v1 validation"] --> storage["storage.py"]
    end
    subgraph web["Web app"]
        auth["auth.py<br/>magic links, sessions, CSRF"]
        pages["pages/*.py<br/>Jinja2 + HTMX"]
        pairing["pairing.py<br/>pending devices, QR"]
    end
    subgraph alerts["Alerts"]
        rules["rules.py<br/>inactivity, phone silent"]
        lifecycle["alerts.py<br/>open, acknowledged, resolved"]
        explain["explain.py<br/>LLM with template fallback"]
        notifiers["notifiers/<br/>Notifier: email, telegram"]
    end
    scope["households.py<br/>household-scoped queries"]

    pages --> auth
    pages --> scope
    pairing --> scope
    rules --> scope
    rules --> lifecycle --> explain --> notifiers
    storage --> db["db.py"]
    scope --> db
```

Every read of household data goes through `households.py`, which takes the signed-in member's household: this is where isolation is enforced and tested.

### 9.4 Pairing a phone

```mermaid
sequenceDiagram
    actor O as Owner (browser)
    participant W as Web app
    participant D as Neon
    participant L as phone-sensor-logger
    actor P as Phone's owner

    O->>W: Add phone (signed in, CSRF token)
    W->>D: INSERT device (pending, SHA-256(token), expires after pending_token_expiry_minutes)
    W-->>O: Provisioning v1 QR code, shown once<br/>(endpoint, token, device name)
    O->>L: Scan QR code (or type details)
    L->>P: What will be shared, to whom, how often
    P-->>L: Agree
    L->>L: Store token in Android Keystore
    L->>W: POST /v1/readings (heartbeat batch)
    W->>D: Pending and not expired? → mark active
    W-->>L: 200
    O->>W: Page refresh (HTMX)
    W-->>O: "Phone connected"
    Note over W,D: No first batch within pending_token_expiry_minutes<br/>(setting, default 30):<br/>the token expires and the owner gets a new code
```

### 9.5 Checking for and sending an alert

```mermaid
sequenceDiagram
    participant S as Schedule
    participant R as rules.py
    participant D as Neon
    participant X as explain.py
    participant G as Gemini
    participant N as Notifiers
    actor C as Alert contacts

    S->>R: POST /jobs/check-alerts
    R->>D: Per person: last activity, last batch, settings, open alerts
    alt rule fires and no open alert
        R->>D: INSERT alert (open)
        R->>X: Explain (per-minute summaries only)
        X->>G: Prompt (timeout 10 s)
        alt LLM answers
            G-->>X: Short explanation
        else error or timeout
            X->>X: Template text
        end
        X->>N: Message
        N->>C: Email and Telegram (respecting quiet hours)
    else activity resumed and alert open
        R->>D: UPDATE alert resolved
        R->>N: "Activity resumed"
    end
```

### 9.6 Target data model

New tables, added to those in section 5 (`devices` gains `person_id`, `status` and `pending_expires_at`).

```mermaid
erDiagram
    households ||--o{ people : has
    households ||--o{ members : has
    users ||--o{ members : "belongs as"
    users ||--o{ sessions : has
    users ||--o{ login_links : requests
    people ||--o{ devices : carries
    households ||--o{ alert_contacts : has
    people ||--|| alert_settings : has
    people ||--o{ alerts : about
    alerts ||--o{ alert_deliveries : "sent as"
    alert_contacts ||--o{ alert_deliveries : receives

    households { uuid id PK
        text name }
    people { uuid id PK
        uuid household_id FK
        text display_name
        text timezone }
    users { uuid id PK
        citext email "unique" }
    members { uuid household_id PK
        uuid user_id PK
        text role "owner or viewer" }
    sessions { text id_hash PK
        uuid user_id FK
        timestamptz expires_at
        timestamptz revoked_at }
    login_links { text token_hash PK
        uuid user_id FK
        timestamptz expires_at "15 min"
        timestamptz used_at }
    devices { uuid id PK
        uuid person_id FK
        text status "pending, active, revoked"
        timestamptz pending_expires_at }
    alert_contacts { uuid id PK
        uuid household_id FK
        text channel "email or telegram"
        text address "email or chat id"
        timestamptz confirmed_at
        time quiet_from
        time quiet_to }
    alert_settings { uuid person_id PK
        time waking_from
        time waking_to
        int inactive_hours
        int silent_hours }
    alerts { uuid id PK
        uuid person_id FK
        text rule
        text status "open, acknowledged, resolved"
        timestamptz opened_at
        uuid acknowledged_by }
    alert_deliveries { uuid id PK
        uuid alert_id FK
        uuid contact_id FK
        text result
        timestamptz sent_at }
```

### 9.7 Quality goals added for the working version

| Goal | How | Decisions |
|---|---|---|
| Household isolation | One module for scoped queries; cross-household tests on every route | [0024](adr/0024-households-and-pairing.md) |
| Accessible on any phone | WCAG 2.2 AA, mobile-first CSS, axe-core and Lighthouse in CI, manual screen-reader checks | [0025](adr/0025-family-web-app.md) |
| Alerts are dependable | Rules with scenario tests; LLM never on the critical path | [0026](adr/0026-rules-decide-llm-explains.md) |
| Replaceable phone app | Only protocol v1 crosses the boundary; contract tests | [0023](adr/0023-phone-sensor-logger-as-data-source.md) |
