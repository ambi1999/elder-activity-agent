"""Phones (devices) and their tokens (ADR 0011, ADR 0024).

Each phone gets its own random token. Only a SHA-256 hash of the token is stored,
so someone who reads the database still can't use the tokens. A plain hash is enough
because the tokens are long and random: they can't be guessed, unlike passwords.

A device is pending, active or revoked. A phone added to a household starts
pending: its token works only until ``pending_expires_at``, unless its first
batch arrives before then, which makes it active (see ``storage._mark_seen``).
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class Device:
    """A phone that may send data.

    Attributes:
        id: The device's ID.
        name: A nickname such as "Mum's phone" (not a full name, ADR 0022).
        timezone: IANA timezone, e.g. "Australia/Brisbane".
        status: "pending", "active" or "revoked".
    """

    id: uuid.UUID
    name: str
    timezone: str
    status: str = "active"


def hash_token(token: str) -> str:
    """The SHA-256 hash stored in place of a token."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_device(
    conn: Connection,
    name: str,
    timezone: str,
    person_id: uuid.UUID | None = None,
    pending_expires_at: datetime | None = None,
) -> tuple[Device, str]:
    """Create a device and its token.

    Args:
        conn: Open connection; the caller commits.
        name: Nickname for the phone.
        timezone: IANA timezone of the phone's owner.
        person_id: The person who carries it, for phones added to a household.
        pending_expires_at: If given, the device starts pending and its token
            stops working at this time unless its first batch arrives first.

    Returns:
        The device and its token. The token is returned only here and never
        stored: the database keeps its hash.
    """
    token = secrets.token_urlsafe(32)  # 256 bits of randomness
    status = "pending" if pending_expires_at else "active"
    row = conn.execute(
        text("""
            INSERT INTO devices (name, timezone, token_hash, person_id, status, pending_expires_at)
            VALUES (:name, :timezone, :token_hash, :person_id, :status, :pending_expires_at)
            RETURNING id, name, timezone, status
        """),
        {
            "name": name,
            "timezone": timezone,
            "token_hash": hash_token(token),
            "person_id": person_id,
            "status": status,
            "pending_expires_at": pending_expires_at,
        },
    ).one()
    return Device(*row), token


def find_device(conn: Connection, token: str, now: datetime) -> Device | None:
    """The device that owns this token, if the token currently works.

    A token works if its device is active, or pending and not yet expired.

    Args:
        conn: Open connection.
        token: The bearer token the phone sent.
        now: Current time in UTC, passed in so tests control the clock.

    Returns:
        The device, or None for an empty, unknown, revoked or expired token.
    """
    if not token:
        return None
    row = conn.execute(
        text("""
            SELECT id, name, timezone, status FROM devices
            WHERE token_hash = :token_hash
              AND (status = 'active' OR (status = 'pending' AND pending_expires_at > :now))
        """),
        {"token_hash": hash_token(token), "now": now},
    ).first()
    return Device(*row) if row else None


def revoke_device(conn: Connection, device_id: uuid.UUID) -> bool:
    """Stop a device's token from working. Returns False if it was already revoked."""
    result = conn.execute(
        text("""
            UPDATE devices SET status = 'revoked', revoked_at = now(), pending_expires_at = NULL
            WHERE id = :id AND status <> 'revoked'
        """),
        {"id": device_id},
    )
    return result.rowcount == 1


def list_devices(conn: Connection) -> list[dict[str, Any]]:
    """All devices with their status, oldest first, for the command-line tools."""
    rows = (
        conn.execute(
            text("""
                SELECT id, name, timezone, status, person_id, created_at, last_seen_at,
                       pending_expires_at, revoked_at
                FROM devices ORDER BY created_at
            """)
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]
