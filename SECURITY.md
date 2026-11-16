# Security policy

This is a portfolio project under active development. It processes activity data from phones, so security reports are taken seriously.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report privately through GitHub: go to the repository's **Security** tab and choose **Report a vulnerability**. Include:

- what you found and where (endpoint, file, or configuration)
- steps to reproduce it
- the impact you think it has

You can expect an acknowledgement within a week. This is a personal project, so fixes are made on a best-effort basis, prioritised by severity.

## Scope

In scope: the code in this repository and the deployed API at `https://elder-activity-agent.onrender.com`.

Please don't:

- access, modify or delete data that isn't yours
- run denial-of-service tests or automated scanners against the live service
- attempt to access the developer's accounts or third-party services (Render, Neon, Google, GitHub)

## Supported versions

Only the latest version on `main` is supported.

## How this project approaches security

See [the threat model](docs/security/threat-model.md) and the security-related architecture decisions:
[0009](docs/adr/0009-secrets-management.md), [0011](docs/adr/0011-ingest-authentication.md),
[0019](docs/adr/0019-security-baseline.md), [0020](docs/adr/0020-request-limits-and-rate-limiting.md),
[0021](docs/adr/0021-supply-chain-security.md) and [0022](docs/adr/0022-data-minimisation-retention-residency.md).
