# 0001. Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-11-16

## Context

Design decisions are being made quickly while building a portfolio project that may become a product. Without a record, the reasoning behind choices is lost, and it becomes hard to revisit them or explain them to others (including interviewers and future collaborators).

## Decision

Record each significant decision as an Architecture Decision Record (ADR): one short Markdown file per decision in `docs/adr/`, numbered in order, kept in the Git repository and changed through pull requests like code. Decisions are never deleted; a changed decision gets a new ADR that supersedes the old one.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| ADRs in the repository | Versioned with the code; reviewed in PRs; industry-standard format | Needs discipline to keep up to date |
| Wiki or shared document (Word, Google Docs) | Easy to edit; familiar | Drifts away from the code; no review history tied to changes |
| No written record | No effort | Reasoning is lost; decisions get re-argued |

## Consequences

Every significant change to architecture, infrastructure or data handling should come with a new or updated ADR in the same pull request.

## When to revisit

Not expected to change.
