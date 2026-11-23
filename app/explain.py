"""Explaining an alert in plain words with the LLM, never on the critical path (ADR 0026, story E-4).

The rules have already decided to alert. This only adds one or two sentences
describing what the data shows. It sends summaries only: no names, contact
details or raw readings. If the LLM is not configured, fails or is slower than
``alerts.llm_timeout_seconds``, the fixed template from ``app/messages.py`` is
used, so an alert is never delayed or lost because of the LLM.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime

from google import genai
from google.genai import types

from app import messages
from app.rules import INACTIVITY, Finding

log = logging.getLogger(__name__)

MAX_LENGTH = 400  # characters; longer answers are cut at a sentence end

PROMPT = """You write one or two calm, plain sentences for a family member about an older relative's phone data.
Facts only: say what the data shows and since when. Don't guess causes, don't give medical advice,
don't use names, don't alarm. Refer to the relative as "they".

Data:
{facts}"""


@dataclass(frozen=True)
class Explanation:
    """The explanation and where it came from ("llm" or "template")."""

    text: str
    source: str


@dataclass(frozen=True)
class Facts:
    """The summary facts an explanation may use, and nothing else.

    Attributes:
        since_local: When the quiet period began, as local clock time, e.g. "9:05 am".
        hours: The rule's threshold in hours.
        steps_today: Steps counted today, or None if unknown.
        battery: Last battery level 0-1, or None.
        minutes_since_data: Minutes since the phone last sent data.
    """

    since_local: str
    hours: int
    steps_today: int | None
    battery: float | None
    minutes_since_data: int


def _facts_text(finding: Finding, facts: Facts) -> str:
    lines = []
    if finding.rule == INACTIVITY:
        lines.append(f"- No steps, screen use or walking since {facts.since_local} (alert after {facts.hours} hours).")
        lines.append(f"- The phone is still sending data; last data {facts.minutes_since_data} minutes ago.")
    else:
        lines.append(f"- The phone has sent no data since {facts.since_local} (alert after {facts.hours} hours).")
    if facts.steps_today is not None:
        lines.append(f"- Steps today: {facts.steps_today}.")
    if facts.battery is not None:
        lines.append(f"- Last battery level: {round(facts.battery * 100)}%.")
    return "\n".join(lines)


def _trim(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= MAX_LENGTH:
        return text
    cut = text[:MAX_LENGTH]
    return cut[: cut.rfind(". ") + 1] if ". " in cut else cut.rstrip() + "…"


def explain(finding: Finding, facts: Facts, template: str, timeout_seconds: int) -> Explanation:
    """Explain an alert with the LLM, or fall back to the template.

    Args:
        finding: What the rule found.
        facts: Summary facts for the prompt.
        template: The fixed explanation to use if the LLM can't help.
        timeout_seconds: How long to wait for the LLM.

    Returns:
        The explanation, marked "llm" or "template".
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return Explanation(template, "template")
    try:
        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_seconds * 1000))
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
            contents=PROMPT.format(facts=_facts_text(finding, facts)),
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
            ),
        )
        text = _trim(response.text or "")
    except Exception:  # any failure means the template is used; the alert must still go out
        log.warning("LLM explanation failed; using the template", exc_info=True)
        return Explanation(template, "template")
    if not text:
        return Explanation(template, "template")
    return Explanation(text, "llm")


def describe_since(moment: datetime, timezone: str) -> str:
    """Local clock time for the prompt, e.g. "9:05 am"."""
    return messages.clock(moment, timezone)
