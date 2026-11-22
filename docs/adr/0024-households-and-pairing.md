# 0024. Serve many households, and pair phones with the protocol v1 setup QR code

- **Status:** Accepted
- **Date:** 2026-11-22

## Context

Until now there is one developer, a few devices and a command-line script (`register_device.py`). A working version must let several unrelated families use the same deployment, each seeing only their own person, and must let a family member (not the developer) connect a phone.

Protocol v1's setup QR code (`provisioning-v1.schema.json`) contains the endpoint and the **device token itself**; one-time pairing codes are only a possible future protocol version.

## Decision

- **Data model.** A **household** is the unit of isolation. It has **people** (the monitored person, normally one), **members** (signed-in family users, with role `owner` or `viewer`), **devices** (phones, each belonging to one person), **alert contacts** (an email address or a Telegram chat, with quiet hours) and **alert rules**. Every row below household carries `household_id`, directly or through its parent.
- **Isolation is enforced in one place.** Every query that reads household data goes through functions that take the signed-in member's household and filter by it. Tests sign in as members of two households and check that every page and endpoint returns 404 for the other household's ids. A later step can add Postgres row-level security as a second layer.
- **Pairing by QR, with a manual fallback.** An owner taps "Add phone" in the web app. The server creates a device with a fresh 256-bit token, stores only its SHA-256 hash (ADR 0011), marks it **pending**, and shows the provisioning v1 QR code once, with the endpoint and token as text below it for typing by hand. The token is never shown again.
- **Limiting a photographed QR code.** A pending device's token expires if no batch (a heartbeat counts) arrives within **`pairing.pending_token_expiry_minutes`**, a server setting in `config/settings.toml` (default **30**, allowed 5 to 1440, overridable per environment with `PAIRING__PENDING_TOKEN_EXPIRY_MINUTES`); the page states the time and then offers a new code. Shorter is safer if a photo of the code leaks; longer gives a slow helper more time. It is one setting for the whole server, not per household, so it can't be weakened from the web app. The first accepted batch makes the device **active** and is shown to the owner ("Phone connected"). Owners can revoke a device at any time. The phone's own consent screen (logger SRS SL-FR-PRV-007) shows the phone's owner what is shared before anything is sent.
- `register_device.py` stays for developers and tests, and gains a `--household` option.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Protocol v1 QR with pending expiry (chosen) | Works with the logger as released; short exposure of a leaked code | The token is in the QR code |
| One-time pairing code (protocol v2) | A photographed code is useless after first use | Needs a new protocol version and an exchange endpoint in both projects |
| Developer registers every phone | No pairing code to build | Doesn't scale beyond the developer's family |
| Separate database per household | Strong isolation | Many databases on a free tier; migrations per household |

## Consequences

Families can be onboarded without the developer. Every new feature must use the household-scoped queries and add an isolation test. Moving to pairing codes later means a protocol v2 and a migration path for v1 phones.

## When to revisit

If QR codes are seen being shared or photographed; when more than one monitored person per household is common; before real users (row-level security).
