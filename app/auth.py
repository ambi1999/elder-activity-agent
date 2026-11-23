"""Signing in to the web app: users, members, one-time email links and sessions (ADR 0025, story C3-1).

How sign-in works:

1. Someone types their email address. If it belongs to a user, a one-time link
   is emailed to it (``create_signin_link``). Either way the same "check your
   email" page is shown, so the page can't be used to find out who has an account.
2. Opening the link shows a "Sign in" button; pressing it uses the link
   (``use_signin_link``). A link works once, for ``web.signin_link_minutes``.
   The button is there because email security scanners open links by themselves.
3. A session is created (``create_session``) and its id is put in a cookie. The
   database stores only hashes of link tokens and session ids, so someone who
   could read the database still couldn't sign in.
4. Every form carries the session's CSRF token, so another website can't make
   a signed-in browser submit forms (``csrf_matches``).

While testing, accounts are invite only: users are added with
``scripts/household.py add-member`` (and in step D2 by invitation).
"""

import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.devices import hash_token
from app.emails import looks_like_email
from app.settings import Settings

ROLES = ("owner", "viewer")


@dataclass(frozen=True)
class User:
    """Someone who signs in to the web app (a family member or a nurse)."""

    id: uuid.UUID
    email: str
    display_name: str


@dataclass(frozen=True)
class Session:
    """A signed-in browser: who it is, and the token its forms must send back."""

    user: User
    csrf_token: str


@dataclass(frozen=True)
class Member:
    """A user's membership of a household, for listing members."""

    user: User
    role: str


def normalize_email(email: str) -> str:
    """The address trimmed and in lower case, as stored.

    Raises:
        ValueError: If it doesn't look like an email address.
    """
    cleaned = email.strip().lower()
    if not looks_like_email(cleaned):
        raise ValueError("Enter an email address like name@example.com.")
    return cleaned


# ---------------------------------------------------------------------------
# Users and members
# ---------------------------------------------------------------------------


def find_user(conn: Connection, email: str) -> User | None:
    """The user with this (already normalised) email address, or None."""
    row = conn.execute(text("SELECT id, email, display_name FROM users WHERE email = :email"), {"email": email}).first()
    return User(*row) if row else None


def add_user(conn: Connection, email: str, display_name: str) -> User:
    """Create a user, or return the existing one with this address (its name is kept).

    Raises:
        ValueError: If the email address or the name isn't valid.
    """
    email = normalize_email(email)
    name = display_name.strip()
    if not 1 <= len(name) <= 60:
        raise ValueError("A name must be 1 to 60 characters.")
    row = conn.execute(
        text("""
            INSERT INTO users (email, display_name) VALUES (:email, :name)
            ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
            RETURNING id, email, display_name
        """),
        {"email": email, "name": name},
    ).one()
    return User(*row)


def add_member(conn: Connection, user_id: uuid.UUID, household_id: uuid.UUID, role: str) -> None:
    """Make a user a member of a household, or change their role there.

    Raises:
        ValueError: If the role isn't "owner" or "viewer".
    """
    if role not in ROLES:
        raise ValueError(f"A role must be one of {', '.join(ROLES)}.")
    conn.execute(
        text("""
            INSERT INTO members (user_id, household_id, role) VALUES (:user, :household, :role)
            ON CONFLICT (user_id, household_id) DO UPDATE SET role = EXCLUDED.role
        """),
        {"user": user_id, "household": household_id, "role": role},
    )


def remove_member(conn: Connection, user_id: uuid.UUID, household_id: uuid.UUID) -> bool:
    """Remove a user from a household. Returns False if they weren't a member."""
    result = conn.execute(
        text("DELETE FROM members WHERE user_id = :user AND household_id = :household"),
        {"user": user_id, "household": household_id},
    )
    return result.rowcount == 1


def list_members(conn: Connection, household_id: uuid.UUID) -> list[Member]:
    """A household's members, owners first."""
    rows = conn.execute(
        text("""
            SELECT u.id, u.email, u.display_name, m.role FROM members m JOIN users u ON u.id = m.user_id
            WHERE m.household_id = :household ORDER BY m.role, u.display_name
        """),
        {"household": household_id},
    ).all()
    return [Member(User(row[0], row[1], row[2]), row[3]) for row in rows]


# ---------------------------------------------------------------------------
# One-time sign-in links
# ---------------------------------------------------------------------------


def create_signin_link(
    conn: Connection, user: User, now: datetime, settings: Settings, lifetime: timedelta | None = None
) -> str:
    """Create a one-time sign-in link for a user and return its URL (secret: email it, never log it).

    Args:
        conn: Open connection; the caller commits.
        user: Who the link signs in.
        now: Current time (UTC).
        settings: For the public URL and the normal lifetime.
        lifetime: How long it works; default ``web.signin_link_minutes`` (invitations last longer).
    """
    token = secrets.token_urlsafe(32)
    expires = now + (lifetime or settings.web.signin_link_expiry)
    conn.execute(
        text("INSERT INTO signin_links (token_hash, user_id, expires_at) VALUES (:hash, :user, :expires)"),
        {"hash": hash_token(token), "user": user.id, "expires": expires},
    )
    return f"{settings.server.public_url}/signin/link/{token}"


def signin_link_is_valid(conn: Connection, token: str, now: datetime) -> bool:
    """Whether a link could still be used, without using it (for the page with the button)."""
    row = conn.execute(
        text("SELECT 1 FROM signin_links WHERE token_hash = :hash AND used_at IS NULL AND expires_at > :now"),
        {"hash": hash_token(token), "now": now},
    ).first()
    return row is not None


def use_signin_link(conn: Connection, token: str, now: datetime) -> User | None:
    """Use a sign-in link: returns its user once, then None for ever (also None if expired or unknown)."""
    # One UPDATE both checks and marks the link, so two presses at once can't both succeed.
    row = conn.execute(
        text("""
            UPDATE signin_links SET used_at = :now
            WHERE token_hash = :hash AND used_at IS NULL AND expires_at > :now
            RETURNING user_id
        """),
        {"hash": hash_token(token), "now": now},
    ).first()
    if row is None:
        return None
    user = conn.execute(
        text("UPDATE users SET last_signin_at = :now WHERE id = :id RETURNING id, email, display_name"),
        {"now": now, "id": row.user_id},
    ).one()
    return User(*user)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def create_session(conn: Connection, user_id: uuid.UUID, now: datetime, settings: Settings) -> str:
    """Sign a browser in. Returns the session id for its cookie (secret)."""
    session_id = secrets.token_urlsafe(32)
    # Tidy up this user's expired sessions while we're here.
    conn.execute(
        text("DELETE FROM sessions WHERE user_id = :user AND expires_at <= :now"), {"user": user_id, "now": now}
    )
    conn.execute(
        text("""
            INSERT INTO sessions (id_hash, user_id, csrf_token, expires_at)
            VALUES (:hash, :user, :csrf, :expires)
        """),
        {
            "hash": hash_token(session_id),
            "user": user_id,
            "csrf": secrets.token_urlsafe(24),
            "expires": now + settings.web.session_length,
        },
    )
    return session_id


def find_session(conn: Connection, session_id: str, now: datetime) -> Session | None:
    """The signed-in user for a cookie's session id, or None if it's unknown, ended or expired."""
    if not session_id:
        return None
    row = conn.execute(
        text("""
            SELECT u.id, u.email, u.display_name, s.csrf_token
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.id_hash = :hash AND s.expires_at > :now
        """),
        {"hash": hash_token(session_id), "now": now},
    ).first()
    return Session(User(row[0], row[1], row[2]), row[3]) if row else None


def end_session(conn: Connection, session_id: str) -> None:
    """Sign a browser out: its session can't be used again."""
    conn.execute(text("DELETE FROM sessions WHERE id_hash = :hash"), {"hash": hash_token(session_id)})


def csrf_matches(session: Session, given: str) -> bool:
    """Whether a form's CSRF token is this session's (compared in constant time)."""
    return hmac.compare_digest(given.encode(), session.csrf_token.encode())


def rename_user(conn: Connection, user_id: uuid.UUID, display_name: str) -> None:
    """Change how a user is shown to others, e.g. in "Daughter is checking".

    Raises:
        ValueError: If the name is empty or longer than 60 characters.
    """
    name = display_name.strip()
    if not 1 <= len(name) <= 60:
        raise ValueError("A name must be 1 to 60 characters.")
    conn.execute(text("UPDATE users SET display_name = :name WHERE id = :id"), {"name": name, "id": user_id})


def owner_count(conn: Connection, household_id: uuid.UUID) -> int:
    """How many owners a household has (it must always keep at least one)."""
    value = conn.execute(
        text("SELECT count(*) FROM members WHERE household_id = :household AND role = 'owner'"),
        {"household": household_id},
    ).scalar()
    return int(value or 0)
