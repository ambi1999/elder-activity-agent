"""The words of every alert message, in one place (ADR 0026, docs/design.md "Tone").

Plain and calm: facts first (what the phone shows and since when), then the
explanation, labelled as written by the agent when it was. Phone problems are
worded as phone problems. No location, no medical claims, no raw data.
"""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.rules import INACTIVITY


@dataclass(frozen=True)
class Message:
    """One message to one contact.

    Attributes:
        subject: Email subject; the first line of a Telegram message.
        text: The body, plain text.
        ack_url: For emails about an open alert, the one-time "I'm checking" link.
        ack_alert_id: For Telegram messages about an open alert, the alert to
            acknowledge from its "I'm checking" button.
    """

    subject: str
    text: str
    ack_url: str | None = None
    ack_alert_id: str | None = None


def clock(moment: datetime, timezone: str) -> str:
    """A time as people say it, in the person's timezone, e.g. "9:05 am"."""
    local = moment.astimezone(ZoneInfo(timezone))
    return local.strftime("%I:%M %p").lstrip("0").lower()


def headline(rule: str, person: str, hours: int) -> str:
    """The alert's title, e.g. "No activity for 4 hours: Mum"."""
    if rule == INACTIVITY:
        return f"No activity for {hours} hours: {person}"
    return f"{person}'s phone has stopped sending"


def template_explanation(
    rule: str, person: str, since: datetime, timezone: str, since_is_wake_start: bool, battery: float | None
) -> str:
    """The fixed explanation, used when the AI isn't available (and always as its fallback)."""
    if rule == INACTIVITY:
        battery_note = f" (battery {round(battery * 100)}%)" if battery is not None else ""
        start = "the start of waking hours, " if since_is_wake_start else ""
        return (
            f"{person}'s phone is still sending data{battery_note}, but there have been no steps, "
            f"screen use or walking since {start}{clock(since, timezone)}."
        )
    return (
        f"{person}'s phone hasn't sent any data since {clock(since, timezone)}. It may be switched off, "
        "out of battery or without internet; this is about the phone, not necessarily about "
        f"{person}."
    )


def opened(
    rule: str, person: str, hours: int, explanation: str, by_llm: bool, ack_url: str | None, alert_id: str
) -> Message:
    """The first message (and any repeat) about an alert."""
    note = "\n(Explanation written by the agent from activity summaries.)" if by_llm else ""
    action = f"\n\nTo let the others know you're checking: {ack_url}" if ack_url else ""
    return Message(
        subject=headline(rule, person, hours),
        text=f"{explanation}{note}{action}",
        ack_url=ack_url,
        ack_alert_id=alert_id,
    )


def acknowledged(rule: str, person: str, hours: int, by: str, at: datetime, timezone: str) -> Message:
    """Tells everyone that someone is checking."""
    return Message(
        subject=f"{by} is checking on {person}",
        text=f"{by} is checking on {person} ({clock(at, timezone)}). Alert: {headline(rule, person, hours)}.",
    )


def resolved(rule: str, person: str, at: datetime, timezone: str) -> Message:
    """Tells everyone the alert is over."""
    what = "Activity resumed" if rule == INACTIVITY else f"{person}'s phone is sending data again"
    return Message(subject=f"All clear: {person}", text=f"{what} at {clock(at, timezone)}. Alert closed.")


def confirm_email(name: str, link: str, minutes: int) -> Message:
    """Asks a new email contact to confirm their address."""
    return Message(
        subject="Confirm your email for Elder Activity alerts",
        text=(
            f"Hello {name},\n\nYou've been added as an alert contact. Open this link to confirm your "
            f"email address and start receiving alerts (it works once, for {minutes} minutes):\n\n{link}\n\n"
            "If you weren't expecting this, ignore this email and nothing will be sent to you."
        ),
    )


def telegram_linked(name: str) -> Message:
    """Confirms to a new Telegram contact that their chat is linked."""
    return Message(
        subject="Linked",
        text=f"Thanks {name}: this chat will now receive Elder Activity alerts. This is a test message.",
    )


def signin_link(product: str, link: str, minutes: int) -> Message:
    """The email with a one-time sign-in link for the web app (story C3-1)."""
    return Message(
        subject=f"Sign in to {product}",
        text=(
            f"Open this link to sign in to {product}. It works once, for {minutes} minutes:\n\n{link}\n\n"
            "If you didn't ask to sign in, ignore this email: nobody can sign in without the link."
        ),
    )
