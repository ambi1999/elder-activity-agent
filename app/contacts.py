"""Alert contacts: who is told, and how they confirm (ADR 0026, stories C-1, D-3).

A contact belongs to a household and gets messages by email or Telegram. A new
contact receives nothing until confirmed, so alerts can't be sent to a mistyped
address or a stranger's chat:

- **email**: a confirmation email with a one-time link; opening it confirms.
- **telegram**: a one-time ``t.me/<bot>?start=<code>`` link; pressing Start in
  Telegram links the contact's chat (its id becomes the contact's address).

Links expire after ``alerts.link_expiry_minutes`` and only their hashes are stored.
"""

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.devices import hash_token
from app.settings import Settings

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CHANNELS = ("email", "telegram")


@dataclass(frozen=True)
class Contact:
    """Someone who receives alerts for a household.

    Attributes:
        id: The contact's ID.
        household_id: The household they are a contact for.
        display_name: How they are named in messages, e.g. "Daughter".
        channel: "email" or "telegram".
        address: Email address or Telegram chat id; None until a Telegram chat is linked.
        confirmed_at: When they confirmed; None means they get nothing yet.
        quiet_from: Start of their quiet hours (local time of the person), or None.
        quiet_to: End of their quiet hours, or None.
    """

    id: uuid.UUID
    household_id: uuid.UUID
    display_name: str
    channel: str
    address: str | None
    confirmed_at: datetime | None
    quiet_from: time | None
    quiet_to: time | None


@dataclass(frozen=True)
class NewContact:
    """A contact just added, with the one-time link that confirms it."""

    contact: Contact
    link: str


def confirm_url(settings: Settings, token: str) -> str:
    """The link in a confirmation email."""
    return f"{settings.server.public_url}/contacts/confirm/{token}"


def telegram_url(settings: Settings, token: str) -> str:
    """The link that opens the bot in Telegram with the one-time code."""
    return f"https://t.me/{settings.telegram.bot_username}?start={token}"


def add_contact(
    conn: Connection,
    household_id: uuid.UUID,
    name: str,
    channel: str,
    now: datetime,
    settings: Settings,
    email: str | None = None,
) -> NewContact:
    """Add an unconfirmed contact and create its one-time confirmation link.

    Args:
        conn: Open connection; the caller commits.
        household_id: The household.
        name: How they are named in messages.
        channel: "email" or "telegram".
        now: Current time in UTC.
        settings: For link expiry, the public URL and the bot's username.
        email: The address, for email contacts.

    Returns:
        The contact and its link (send it to them; it is shown only once).

    Raises:
        ValueError: For an unknown channel, a missing or invalid email address,
            or a Telegram contact before ``telegram.bot_username`` is set.
    """
    if channel not in CHANNELS:
        raise ValueError(f"channel must be one of {', '.join(CHANNELS)}")
    address = None
    if channel == "email":
        address = (email or "").strip().lower()
        if not EMAIL.match(address):
            raise ValueError("That doesn't look like an email address.")
    elif not settings.telegram.bot_username:
        raise ValueError("Set telegram.bot_username in config/settings.toml first (the bot's name from @BotFather).")

    token = secrets.token_urlsafe(24)  # 32 characters, allowed in Telegram start links
    row = conn.execute(
        text("""
            INSERT INTO alert_contacts (household_id, display_name, channel, address, link_token_hash, link_expires_at)
            VALUES (:household_id, :name, :channel, :address, :hash, :expires)
            RETURNING id, household_id, display_name, channel, address, confirmed_at, quiet_from, quiet_to
        """),
        {
            "household_id": household_id,
            "name": name,
            "channel": channel,
            "address": address,
            "hash": hash_token(token),
            "expires": now + timedelta(minutes=settings.alerts.link_expiry_minutes),
        },
    ).one()
    link = confirm_url(settings, token) if channel == "email" else telegram_url(settings, token)
    return NewContact(Contact(*row), link)


def confirm(conn: Connection, token: str, now: datetime, chat_id: str | None = None) -> Contact | None:
    """Confirm a contact from its one-time link.

    Args:
        conn: Open connection; the caller commits.
        token: The code from the link.
        now: Current time in UTC.
        chat_id: For Telegram, the chat that pressed Start; it becomes the address.

    Returns:
        The confirmed contact, or None if the link is unknown, used or expired,
        or is for the other channel.
    """
    row = conn.execute(
        text("""
            SELECT id, household_id, display_name, channel, address, confirmed_at, quiet_from, quiet_to
            FROM alert_contacts
            WHERE link_token_hash = :hash AND link_expires_at > :now
        """),
        {"hash": hash_token(token), "now": now},
    ).first()
    if row is None:
        return None
    contact = Contact(*row)
    if (contact.channel == "telegram") != (chat_id is not None):
        return None
    address = chat_id if chat_id is not None else contact.address

    # The same chat or address already confirmed in this household: keep that one.
    existing = conn.execute(
        text("""
            SELECT id, household_id, display_name, channel, address, confirmed_at, quiet_from, quiet_to
            FROM alert_contacts
            WHERE household_id = :household AND channel = :channel AND address = :address AND id <> :id
        """),
        {"household": contact.household_id, "channel": contact.channel, "address": address, "id": contact.id},
    ).first()
    if existing is not None:
        conn.execute(text("DELETE FROM alert_contacts WHERE id = :id"), {"id": contact.id})
        return Contact(*existing)

    row = conn.execute(
        text("""
            UPDATE alert_contacts
            SET address = :address, confirmed_at = :now, link_token_hash = NULL, link_expires_at = NULL
            WHERE id = :id
            RETURNING id, household_id, display_name, channel, address, confirmed_at, quiet_from, quiet_to
        """),
        {"address": address, "now": now, "id": contact.id},
    ).one()
    return Contact(*row)


def list_contacts(conn: Connection, household_id: uuid.UUID, confirmed_only: bool = False) -> list[Contact]:
    """A household's contacts, oldest first."""
    rows = conn.execute(
        text("""
            SELECT id, household_id, display_name, channel, address, confirmed_at, quiet_from, quiet_to
            FROM alert_contacts
            WHERE household_id = :id AND (confirmed_at IS NOT NULL OR NOT :confirmed_only)
            ORDER BY created_at
        """),
        {"id": household_id, "confirmed_only": confirmed_only},
    ).all()
    return [Contact(*row) for row in rows]


def find_telegram_contact(conn: Connection, household_id: uuid.UUID, chat_id: str) -> Contact | None:
    """The confirmed Telegram contact for this chat in this household, or None."""
    row = conn.execute(
        text("""
            SELECT id, household_id, display_name, channel, address, confirmed_at, quiet_from, quiet_to
            FROM alert_contacts
            WHERE household_id = :household AND channel = 'telegram' AND address = :chat
              AND confirmed_at IS NOT NULL
        """),
        {"household": household_id, "chat": chat_id},
    ).first()
    return Contact(*row) if row else None


def remove_contact(conn: Connection, contact_id: uuid.UUID) -> bool:
    """Remove a contact; they get no more messages. Returns False if there was none."""
    return conn.execute(text("DELETE FROM alert_contacts WHERE id = :id"), {"id": contact_id}).rowcount == 1


def set_quiet_hours(conn: Connection, contact_id: uuid.UUID, start: time | None, end: time | None) -> bool:
    """Set (or, with None, clear) a contact's quiet hours. They may cross midnight, e.g. 22:00-07:00."""
    if (start is None) != (end is None) or (start is not None and start == end):
        raise ValueError("Give both a start and an end, and make them different.")
    result = conn.execute(
        text("UPDATE alert_contacts SET quiet_from = :start, quiet_to = :end WHERE id = :id"),
        {"start": start, "end": end, "id": contact_id},
    )
    return result.rowcount == 1


def in_quiet_hours(contact: Contact, now: datetime, timezone: str) -> bool:
    """Whether ``now`` falls in the contact's quiet hours, in the person's timezone."""
    if contact.quiet_from is None or contact.quiet_to is None:
        return False
    local = now.astimezone(ZoneInfo(timezone)).time()
    if contact.quiet_from < contact.quiet_to:
        return contact.quiet_from <= local < contact.quiet_to
    return local >= contact.quiet_from or local < contact.quiet_to  # crosses midnight
