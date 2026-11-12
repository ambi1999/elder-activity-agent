"""The agent loop.

1. Send the user's message to Gemini, along with the list of tools.
2. If Gemini asks to call a tool, run it and send back the result.
3. Repeat until Gemini replies with a plain answer (or we hit MAX_STEPS).

Automatic function calling is switched off on purpose so the loop is
visible here. That loop is the core of every agent you'll build.
"""
import json
import logging
import os
import sys

from google import genai
from google.genai import types

from app.tools import TOOLS, run_tool

log = logging.getLogger(__name__)

# Check Google AI Studio for which Flash models your free tier includes.
# MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

MAX_STEPS = 5
SYSTEM_PROMPT = (
    "You are a helpful assistant. For any question about the date, the time "
    "or arithmetic, use the tools instead of guessing. Keep answers short."
)

_client = None

def _get_client() -> genai.Client:
    # Created on first use, so importing this module (e.g. in tests)
    # doesn't need an API key.
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=types.HttpOptions(
                timeout=60_000,  # milliseconds: give up after 60 seconds
                retry_options=types.HttpRetryOptions(attempts=2),  # retry once, not indefinitely
            ),
        )
    return _client

def run_agent(message: str) -> dict:
    """Answer a message, using tools as needed. Returns the answer plus a trace of tool calls."""
    client = _get_client()
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=list(TOOLS.values()),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        thinking_config=types.ThinkingConfig(thinking_level="low"),
    )
    contents = [types.Content(role="user", parts=[types.Part(text=message)])]
    trace = []

    for _ in range(MAX_STEPS):
        response = client.models.generate_content(model=MODEL, contents=contents, config=config)
        calls = response.function_calls or []

        if not calls:
            return {"answer": response.text or "", "tool_calls": trace}

        # Keep the model's tool request in the history, then add the results.
        contents.append(response.candidates[0].content)
        result_parts = []
        for call in calls:
            args = dict(call.args or {})
            result = run_tool(call.name, args)
            log.info("tool=%s args=%s result=%s", call.name, args, result)
            trace.append({"tool": call.name, "args": args, "result": result})
            result_parts.append(
                types.Part.from_function_response(name=call.name, response={"result": result})
            )
        contents.append(types.Content(role="user", parts=result_parts))

    return {"answer": "Sorry, I couldn't finish that within the step limit.", "tool_calls": trace}


if __name__ == "__main__":
    # Quick local test:  python -m app.agent "what is 17 times 23?"
    logging.basicConfig(level=logging.INFO)
    question = " ".join(sys.argv[1:]) or "What is 17 times 23, and what day is it in London?"
    print(json.dumps(run_agent(question), indent=2))
