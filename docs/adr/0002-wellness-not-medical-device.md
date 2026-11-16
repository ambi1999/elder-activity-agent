# 0002. Position the product as wellness monitoring, not a medical device

- **Status:** Accepted
- **Date:** 2026-11-16

## Context

The system watches an older person's daily activity and alerts family. Software that diagnoses, treats or claims to detect medical conditions (for example, falls or illness) can fall under medical device regulation (such as the TGA in Australia or the FDA in the US), which would add significant cost and time.

## Decision

The product reports activity patterns compared with the person's own routine and prompts a check-in. It does not diagnose, does not claim fall detection, and is not an emergency service. All wording in the app, alerts and marketing follows this.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Wellness / activity monitoring | Stays outside medical device regulation; fast to build and iterate | Cannot make clinical claims; must be clear it is not an emergency service |
| Claim fall detection or health monitoring | Stronger marketing message | Likely regulated; high validation burden; liability if it fails |
| Emergency alarm service | Clear value | Needs 24/7 response, reliability guarantees and certification |

## Consequences

Alert and report wording must be reviewed against this ADR. Users and families must be told clearly that the system can miss events (for example, when the phone is left behind).

## When to revisit

Revisit only with legal advice, if clinical features are ever considered.
