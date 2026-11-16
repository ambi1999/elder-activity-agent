# 0005. Use Gemini Flash (free tier) as the LLM, and send it only anonymised summaries

- **Status:** Accepted
- **Date:** 2026-11-16

## Context

The project must be free during development and must not depend on the developer's own computer for hosting. The LLM needs reliable tool calling.

## Decision

Use a Gemini Flash model through the Gemini API free tier during development. The model name is configuration (`GEMINI_MODEL`), not code. Only anonymised activity summaries are ever sent to the model, never raw sensor data, names or locations. A paid tier is required before real users' data is processed.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Gemini Flash free tier (chosen) | Free; capable tool calling; hosted | Free-tier prompts may be used by Google to improve products; rate limits; occasional slow responses |
| OpenAI or Anthropic APIs | Strong models | No meaningful free tier for this use |
| Local model with Ollama | Private; free; offline | Needs a capable computer that is always on, which conflicts with cloud-only hosting |
| On-device model on the phone | Most private | Needs the native app; limited model size; later option |

## Consequences

Privacy depends on what the backend sends, so summaries must be built carefully. Moving to paid usage (where data is not used for training) is a precondition for real users.

## When to revisit

Revisit before onboarding real users, or if quality or rate limits become a problem.
