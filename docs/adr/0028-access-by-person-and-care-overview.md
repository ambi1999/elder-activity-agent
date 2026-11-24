# 0028. Give each signed-in user a set of people, with a care overview first

- **Status:** Accepted (to be built in step D)
- **Date:** 2026-11-23

## Context

The first users were imagined as a family looking after one person. A second, equally important user is a **nurse or carer looking after several people**, for example ten older people in their own homes, each with the logger on their phone. Such a user needs, first and above all, a very simple screen that says **who needs attention now**, and then the details for one person.

The web app (ADR 0025) hasn't been built yet. How it decides what a signed-in user may see is the one part of the design that is expensive to change later: it shapes sign-in, page addresses, every query and every isolation test (ADR 0024).

## Decision

- **Access is a set of people.** A signed-in user may see every person in every household they are a member of (members: user, household, role; a user can be a member of many households). Every query for a person's data checks that the person is in that set; every page address names the person (`/people/{id}/today`), never "the current household".
- **The care overview is the home page when a user can see more than one person.** It lists everyone, **needs attention first**, each with a status shown by **colour, an icon and words** (never colour alone, WCAG 1.4.1):
  - **Red, "Needs attention":** an open or acknowledged alert about the person (who is checking is shown).
  - **Amber, "Phone not sending":** the phone-silent rule has fired: a phone problem, kept apart from concern about the person so visits aren't wasted.
  - **Green, "All OK":** no open alert; the time of the last activity is shown.
  Tapping a person opens their Today page. The overview refreshes itself (HTMX, with an `aria-live` summary).
- **A user who can see one person** goes straight to that person's Today page; no list.
- **Status comes from alerts**, so rules added later (for example a personal baseline, Phase 3) appear on the overview without changing it.
- **Isolation tests** sign in as users with different sets of people and check that every page and endpoint returns 404 for anyone outside the set.
- **Later, not now:** care organisations (several staff sharing people, assigning people to staff, shift handover, a digest instead of one message per alert, audit reports), and legal advice before professional use: health information is "sensitive information" under Australia's Privacy Act, and the system stays a wellness tool, not a medical device (ADR 0002).

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Access by set of people, overview first (chosen) | Families and nurses use the same app and code; no rework when the nurse case is built | One more page and slightly broader isolation tests in step D |
| One household per signed-in user | Simplest sign-in and queries | A nurse would need ten accounts or a rewrite of the access model |
| A separate "care organisation" model now | Ready for agencies | A large new layer before one family or nurse has used the app |

## Consequences

Step D builds sign-in, the overview, and person pages on the access set from the start. A nurse is simply a member (role `viewer` or `owner`) of each household they care for, and can be an alert contact in each. The prototype in `docs/prototype/` shows the overview and its flow.

## When to revisit

When a care organisation wants several staff to share people, or alerts for many people become too noisy for one person (digests, assignment). The care-team use case (nurses in shifts sharing a group of households, the family granting access) is recorded as Proposed requirements EA-FR-TEAM-001 to 006 in the [SRS](../requirements/srs.md#315-care-organisations-l).
