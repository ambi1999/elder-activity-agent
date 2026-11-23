"""Households, the people in them, and adding their phones (ADR 0024, story A-2).

A household is the unit of isolation: everything about a person and their
phones belongs to exactly one household. Until the family web app exists
(step D), households are managed with ``scripts/household.py``.

Adding a phone creates a pending device and returns the contents of its setup
QR code, in phone-sensor-logger's provisioning v1 format. The QR code contains
the device token, so it is a secret: it is shown once and never stored or logged.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import devices
from app.settings import Settings

PROVISIONING_TYPE = "phone-sensor-logger/provisioning"
PROVISIONING_VERSION = 1
MAX_DEVICE_NAME = 100  # the provisioning schema's limit


@dataclass(frozen=True)
class Household:
    """A family using the service."""

    id: uuid.UUID
    name: str


@dataclass(frozen=True)
class Person:
    """The person being looked after, who carries the phone."""

    id: uuid.UUID
    household_id: uuid.UUID
    display_name: str
    timezone: str


@dataclass(frozen=True)
class NewPhone:
    """A phone just added to a household, with what its owner needs to connect it.

    Attributes:
        device: The pending device.
        expires_at: When the token stops working if no batch has arrived.
        provisioning: The setup QR code's contents (contains the token: secret).
    """

    device: devices.Device
    expires_at: datetime
    provisioning: dict[str, Any]


def check_timezone(timezone: str) -> None:
    """Raise ValueError unless ``timezone`` is a known IANA name such as Europe/London."""
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as err:
        raise ValueError(f"Unknown timezone {timezone!r}. Use an IANA name such as Australia/Brisbane.") from err


def create_household(conn: Connection, name: str) -> Household:
    """Create a household. The caller commits."""
    row = conn.execute(
        text("INSERT INTO households (name) VALUES (:name) RETURNING id, name"),
        {"name": name},
    ).one()
    return Household(*row)


def add_person(conn: Connection, household_id: uuid.UUID, display_name: str, timezone: str) -> Person:
    """Add the person being looked after to a household.

    Raises:
        ValueError: If the timezone is unknown.
    """
    check_timezone(timezone)
    row = conn.execute(
        text("""
            INSERT INTO people (household_id, display_name, timezone)
            VALUES (:household_id, :display_name, :timezone)
            RETURNING id, household_id, display_name, timezone
        """),
        {"household_id": household_id, "display_name": display_name, "timezone": timezone},
    ).one()
    return Person(*row)


def find_person(conn: Connection, person_id: uuid.UUID) -> Person | None:
    """The person with this ID, or None."""
    row = conn.execute(
        text("SELECT id, household_id, display_name, timezone FROM people WHERE id = :id"),
        {"id": person_id},
    ).first()
    return Person(*row) if row else None


def provisioning_payload(endpoint: str, token: str, device_name: str, profile: str) -> dict[str, Any]:
    """The setup QR code's contents, in phone-sensor-logger's provisioning v1 format.

    Args:
        endpoint: HTTPS upload URL, e.g. https://example.com/v1/readings.
        token: The device token (secret).
        device_name: Shown on the phone's consent screen as the receiver's label.
        profile: The logger profile to recommend, e.g. "activity".
    """
    return {
        "type": PROVISIONING_TYPE,
        "version": PROVISIONING_VERSION,
        "endpoint": endpoint,
        "token": token,
        "device_name": device_name,
        "profile": profile,
    }


def add_phone(conn: Connection, person: Person, device_name: str, now: datetime, settings: Settings) -> NewPhone:
    """Add a pending phone for a person and build its setup QR code contents.

    Args:
        conn: Open connection; the caller commits.
        person: Who will carry the phone.
        device_name: Nickname, e.g. "Mum's phone".
        now: Current time in UTC.
        settings: For the endpoint, the expiry and the recommended profile.

    Returns:
        The pending device, when its token expires, and the QR code contents.

    Raises:
        ValueError: If the phone's name is empty or longer than the QR format allows.
    """
    if not 1 <= len(device_name) <= MAX_DEVICE_NAME:
        raise ValueError(f"A phone's name must be 1 to {MAX_DEVICE_NAME} characters.")
    expires_at = now + settings.pairing.pending_token_expiry
    device, token = devices.create_device(
        conn, device_name, person.timezone, person_id=person.id, pending_expires_at=expires_at
    )
    payload = provisioning_payload(
        settings.server.readings_endpoint, token, device_name, settings.pairing.device_profile
    )
    return NewPhone(device=device, expires_at=expires_at, provisioning=payload)


def find_household(conn: Connection, household_id: uuid.UUID) -> Household | None:
    """The household with this ID, or None."""
    row = conn.execute(
        text("SELECT id, name FROM households WHERE id = :id"),
        {"id": household_id},
    ).first()
    return Household(*row) if row else None


def count_household_data(conn: Connection, household_id: uuid.UUID) -> dict[str, int]:
    """How much would be deleted with a household: people, phones and stored data rows."""
    row = (
        conn.execute(
            text("""
                SELECT
                    (SELECT count(*) FROM people WHERE household_id = :id) AS people,
                    (SELECT count(*) FROM devices d JOIN people p ON p.id = d.person_id
                      WHERE p.household_id = :id) AS phones,
                    (SELECT count(*) FROM minute_summary m JOIN devices d ON d.id = m.device_id
                      JOIN people p ON p.id = d.person_id WHERE p.household_id = :id)
                  + (SELECT count(*) FROM step_readings s JOIN devices d ON d.id = s.device_id
                      JOIN people p ON p.id = d.person_id WHERE p.household_id = :id)
                  + (SELECT count(*) FROM device_events e JOIN devices d ON d.id = e.device_id
                      JOIN people p ON p.id = d.person_id WHERE p.household_id = :id) AS data_rows
            """),
            {"id": household_id},
        )
        .mappings()
        .one()
    )
    return dict(row)


def delete_household(conn: Connection, household_id: uuid.UUID) -> bool:
    """Delete a household and, through the database's cascades, everything about it.

    Its people, their phones (whose tokens stop working), and every reading,
    event and summary from those phones are removed. This cannot be undone.

    Returns:
        False if there was no such household.
    """
    result = conn.execute(text("DELETE FROM households WHERE id = :id"), {"id": household_id})
    return result.rowcount == 1


def list_households(conn: Connection) -> list[dict[str, Any]]:
    """Every household with its people and their phones, for the command line.

    Tokens are never included: the database doesn't have them.
    """
    rows = (
        conn.execute(
            text("""
                SELECT h.id AS household_id, h.name AS household,
                       p.id AS person_id, p.display_name AS person, p.timezone,
                       d.id AS device_id, d.name AS device, d.status, d.last_seen_at, d.pending_expires_at
                FROM households h
                LEFT JOIN people p ON p.household_id = h.id
                LEFT JOIN devices d ON d.person_id = p.id
                ORDER BY h.created_at, p.created_at, d.created_at
            """)
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]
