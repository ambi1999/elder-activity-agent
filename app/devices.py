"""Phones (devices) and their tokens (ADR 0011).

Each phone gets its own random token. Only a SHA-256 hash of the token is stored,
so someone who reads the database still can't use the tokens. A plain hash is enough
because the tokens are long and random: they can't be guessed, unlike passwords.
"""
import hashlib
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class Device:
    id: uuid.UUID
    name: str
    timezone: str


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_device(conn: Connection, name: str, timezone: str) -> tuple[Device, str]:
    """Create a device. Returns it together with its token, which is never stored."""
    token = secrets.token_urlsafe(32)  # 256 bits of randomness
    row = conn.execute(
        text("""
            INSERT INTO devices (name, timezone, token_hash)
            VALUES (:name, :timezone, :token_hash)
            RETURNING id, name, timezone
        """),
        {"name": name, "timezone": timezone, "token_hash": hash_token(token)},
    ).one()
    return Device(*row), token


def find_device(conn: Connection, token: str) -> Device | None:
    """The active (not revoked) device that owns this token, if any."""
    if not token:
        return None
    row = conn.execute(
        text("""
            SELECT id, name, timezone FROM devices
            WHERE token_hash = :token_hash AND revoked_at IS NULL
        """),
        {"token_hash": hash_token(token)},
    ).first()
    return Device(*row) if row else None


def revoke_device(conn: Connection, device_id: uuid.UUID) -> bool:
    result = conn.execute(
        text("UPDATE devices SET revoked_at = now() WHERE id = :id AND revoked_at IS NULL"),
        {"id": device_id},
    )
    return result.rowcount == 1


def list_devices(conn: Connection) -> list[dict]:
    rows = conn.execute(
        text("""
            SELECT id, name, timezone, created_at, last_seen_at, revoked_at
            FROM devices ORDER BY created_at
        """)
    ).mappings().all()
    return [dict(row) for row in rows]
