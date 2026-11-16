# 0019. Adopt a security baseline for accounts, secrets and database access

- **Status:** Accepted (secret scanning and two-factor authentication: manual settings; separate database logins planned)
- **Date:** 2026-11-17

## Context

The developer accounts (GitHub, Render, Neon, Google) control the code, deployments, data and API keys. During development, an ingest token and the database password were exposed in chats and logs and had to be rotated. The app currently connects to Neon as the database owner, which can do anything, including dropping tables.

## Decision

Every account that can affect the system uses two-factor authentication, preferably passkeys. GitHub secret scanning and push protection are enabled so secrets are blocked before they reach the repository. Secrets are kept only in `.env`, Render, GitHub Actions secrets and a password manager. Before real users, the app connects with a login that can only read and write data, while migrations use a separate login that can change table structure. Leaked secrets follow the runbook in the threat model: rotate, update, verify.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Baseline with least privilege (chosen) | Limits the damage of any single leak; cheap; standard practice | Two database logins to manage |
| Single owner login for everything (current) | Simplest | A leaked app password gives full control of the database |
| Central secrets manager (Vault, AWS Secrets Manager) | Automated rotation and auditing | Extra service; cloud options needed a card; planned with the AWS move |

## Consequences

Account security is a manual setting and can't be enforced by code; it is listed in the threat model so it is reviewed. The database login split is tied to moving migrations into the pipeline (ADR 0015).

## When to revisit

Revisit when moving to AWS, or when anyone else gets access.
