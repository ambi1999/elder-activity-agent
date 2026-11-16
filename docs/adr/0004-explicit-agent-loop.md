# 0004. Write the agent loop explicitly instead of using an agent framework

- **Status:** Accepted
- **Date:** 2026-11-16

## Context

The agent needs to call tools (time, maths, and later activity summaries and messaging) and decide what to do. Frameworks and SDK features can run this loop automatically.

## Decision

Implement the tool-calling loop directly in `app/agent.py` with automatic function calling switched off, and a step limit. Tools are plain Python functions whose type hints and docstrings describe them to the model.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Explicit loop (chosen) | Fully visible and debuggable; no framework lock-in; easy to log and test; good for learning and interviews | More code to write; features such as memory must be built by hand |
| SDK automatic function calling | Least code | Hides the loop; harder to log, limit or test each step |
| Agent frameworks (LangChain, LangGraph, CrewAI) | Many features out of the box | Extra abstraction and dependencies; harder to see what the model is doing |

## Consequences

Each tool call is logged and returned in a trace. Tool errors are returned to the model as text so it can recover. Tools with real-world effects (such as alerting family) must state clearly in their docstrings when they may be used.

## When to revisit

Revisit if the agent needs multi-agent coordination or long-running workflows.
