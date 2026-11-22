# 0026. Let rules decide when to alert, let the LLM explain, and send alerts by email and Telegram

- **Status:** Accepted
- **Date:** 2026-11-22

## Context

The point of the system is to tell a family when something looks unusual. An alert that is missed, or sent when nothing is wrong, costs trust quickly. LLMs are good at explaining a day in plain words but are not deterministic, can be unavailable (ADR 0017), and are hard to test for "did it alert when it should have".

## Decision

- **Rules decide.** Alerts come from explicit, tested rules with settings stored per household. The first two:
  - **Inactivity:** no steps and no screen use for `inactive_hours` (default 4) within the person's waking hours (default 08:00 to 21:00, in their timezone), while the phone is still sending data.
  - **Phone silent:** no batch from the phone for `silent_hours` (default 6), worded as "the phone has stopped sending", not as a concern about the person.
  More rules (for example, compared with the person's own baseline) come later, each with scenario tests.
- **The LLM explains.** When a rule fires, the agent may write a short explanation from per-minute summaries only (never raw readings, names or contact details). If the LLM fails or is slow, a fixed template is sent instead: an alert never waits for or depends on the LLM.
- **Alert lifecycle**: open, acknowledged (by any member, from the web app or the message), resolved (when activity resumes). An open alert isn't repeated; quiet hours per contact are respected except for a resend after a configurable delay.
- **Channels**: **email** (a transactional email API on its free tier) and **Telegram** (a bot; a contact links their chat by opening a one-time `t.me/<bot>?start=<code>` link from the web app). SMS later, behind the same `Notifier` interface.
- **Checked every 5 minutes.** On the free tier there is no background worker, so a GitHub Actions schedule calls a protected `POST /jobs/check-alerts` endpoint (which also wakes the service). GitHub's schedule is best effort and can be late, which is accepted while testing and replaced by a real scheduler before real users.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Rules decide, LLM explains (chosen) | Testable and predictable; works when the LLM is down | Rules need tuning per person |
| LLM decides | Flexible, can spot unusual patterns | Not repeatable; hard to test; fails when the LLM is unavailable |
| Machine-learning anomaly model | Learns each person's routine | Needs weeks of data and labelled examples first |
| SMS only | Reaches everyone | Costs per message from the start |

## Consequences

The first useful version works without a baseline. False alerts are tuned by settings, not prompts. The agent's role grows (daily summaries, answering family questions) without being on the alert path.

## When to revisit

When enough data exists to compare with a personal baseline, or when families ask for SMS or push notifications.
