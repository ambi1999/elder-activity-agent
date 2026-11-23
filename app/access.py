"""What a signed-in user may see: the set of people in their households (ADR 0028, story C3-5).

Every web page about a person or an alert goes through this module. Each query
joins through ``members``, so a person or alert outside the user's households
is simply not found, and the page answers 404, exactly as if it didn't exist.
Nothing here trusts an id from the browser on its own.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class VisiblePerson:
    """A person the user may see, with the user's role in that person's household."""

    id: uuid.UUID
    household_id: uuid.UUID
    household_name: str
    display_name: str
    timezone: str
    role: str  # "owner" or "viewer"
    has_phone: bool  # at least one active phone

    @property
    def is_owner(self) -> bool:
        """Whether the user may change this person's settings (step D2)."""
        return self.role == "owner"


@dataclass(frozen=True)
class AlertView:
    """One alert, as the web app shows it."""

    id: uuid.UUID
    person: VisiblePerson
    rule: str
    status: str
    since: datetime
    explanation: str
    explained_by: str
    opened_at: datetime
    acknowledged_by: str | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None


# Columns of VisiblePerson, in order, for the queries below.
_PERSON_COLUMNS = """
    p.id, p.household_id, h.name, p.display_name, p.timezone, m.role,
    EXISTS (SELECT 1 FROM devices d WHERE d.person_id = p.id AND d.status = 'active')
"""


def people_for(conn: Connection, user_id: uuid.UUID) -> list[VisiblePerson]:
    """Everyone in every household the user is a member of, by name."""
    rows = conn.execute(
        text(f"""
            SELECT {_PERSON_COLUMNS}
            FROM members m JOIN households h ON h.id = m.household_id JOIN people p ON p.household_id = h.id
            WHERE m.user_id = :user
            ORDER BY lower(p.display_name), p.created_at
        """),  # noqa: S608 (the f-string only inserts the fixed column list above)
        {"user": user_id},
    ).all()
    return [VisiblePerson(*row) for row in rows]


def person_for(conn: Connection, user_id: uuid.UUID, person_id: uuid.UUID) -> VisiblePerson | None:
    """One person, if the user may see them; otherwise None (the page answers 404)."""
    row = conn.execute(
        text(f"""
            SELECT {_PERSON_COLUMNS}
            FROM members m JOIN households h ON h.id = m.household_id JOIN people p ON p.household_id = h.id
            WHERE m.user_id = :user AND p.id = :person
        """),  # noqa: S608 (the f-string only inserts the fixed column list above)
        {"user": user_id, "person": person_id},
    ).first()
    return VisiblePerson(*row) if row else None


def alerts_for(
    conn: Connection, user_id: uuid.UUID, resolved_since: datetime, person_id: uuid.UUID | None = None
) -> list[AlertView]:
    """The user's alerts: every unresolved one, and those resolved after ``resolved_since``, newest first.

    Args:
        conn: Open connection.
        user_id: The signed-in user.
        resolved_since: How far back to include closed alerts.
        person_id: Only this person's alerts (already checked to be visible), or everyone's.
    """
    people = {p.id: p for p in people_for(conn, user_id)}
    if person_id is not None:
        people = {k: v for k, v in people.items() if k == person_id}
    if not people:
        return []
    rows = conn.execute(
        text("""
            SELECT id, person_id, rule, status, since, explanation, explained_by, opened_at,
                   acknowledged_by, acknowledged_at, resolved_at
            FROM alerts
            WHERE person_id = ANY(:people) AND (status <> 'resolved' OR resolved_at > :since)
            ORDER BY opened_at DESC
        """),
        {"people": list(people), "since": resolved_since},
    ).all()
    return [AlertView(row[0], people[row[1]], *row[2:]) for row in rows]


def alert_for(conn: Connection, user_id: uuid.UUID, alert_id: uuid.UUID) -> AlertView | None:
    """One alert, if it is about someone the user may see; otherwise None."""
    row = conn.execute(
        text("""
            SELECT a.id, a.person_id, a.rule, a.status, a.since, a.explanation, a.explained_by, a.opened_at,
                   a.acknowledged_by, a.acknowledged_at, a.resolved_at
            FROM alerts a JOIN people p ON p.id = a.person_id
            JOIN members m ON m.household_id = p.household_id AND m.user_id = :user
            WHERE a.id = :alert
        """),
        {"user": user_id, "alert": alert_id},
    ).first()
    if row is None:
        return None
    person = person_for(conn, user_id, row[1])
    return AlertView(row[0], person, *row[2:]) if person else None


def open_alert_count(conn: Connection, user_id: uuid.UUID) -> int:
    """How many alerts about the user's people nobody has acknowledged yet (the Alerts tab's badge)."""
    value = conn.execute(
        text("""
            SELECT count(*) FROM alerts a JOIN people p ON p.id = a.person_id
            JOIN members m ON m.household_id = p.household_id AND m.user_id = :user
            WHERE a.status = 'open'
        """),
        {"user": user_id},
    ).scalar()
    return int(value or 0)


@dataclass(frozen=True)
class Phone:
    """One of a person's phones, as the Phones page shows it."""

    id: uuid.UUID
    name: str
    status: str  # "pending", "active" or "revoked"
    last_seen_at: datetime | None
    pending_expires_at: datetime | None
    created_at: datetime


def phones_for(conn: Connection, person_id: uuid.UUID) -> list[Phone]:
    """A person's phones that are connected or waiting to connect, newest first (the person is already checked)."""
    rows = conn.execute(
        text("""
            SELECT id, name, status, last_seen_at, pending_expires_at, created_at FROM devices
            WHERE person_id = :person AND status <> 'revoked' ORDER BY created_at DESC
        """),
        {"person": person_id},
    ).all()
    return [Phone(*row) for row in rows]


def phone_for(conn: Connection, person_id: uuid.UUID, device_id: uuid.UUID) -> Phone | None:
    """One phone, only if it belongs to this (already checked) person."""
    row = conn.execute(
        text("""
            SELECT id, name, status, last_seen_at, pending_expires_at, created_at FROM devices
            WHERE id = :device AND person_id = :person
        """),
        {"device": device_id, "person": person_id},
    ).first()
    return Phone(*row) if row else None


@dataclass(frozen=True)
class OwnedHousehold:
    """A household the user owns, for adding a person to it."""

    id: uuid.UUID
    name: str


def households_owned(conn: Connection, user_id: uuid.UUID) -> list[OwnedHousehold]:
    """The households where the user is an owner, by name."""
    rows = conn.execute(
        text("""
            SELECT h.id, h.name FROM members m JOIN households h ON h.id = m.household_id
            WHERE m.user_id = :user AND m.role = 'owner' ORDER BY lower(h.name)
        """),
        {"user": user_id},
    ).all()
    return [OwnedHousehold(*row) for row in rows]


def user_summary(conn: Connection, user_id: uuid.UUID) -> list[tuple[str, str, list[str]]]:
    """For scripts/household.py user: each household of the user, their role there and its people."""
    rows = conn.execute(
        text("""
            SELECT h.id, h.name, m.role, p.display_name
            FROM members m JOIN households h ON h.id = m.household_id
            LEFT JOIN people p ON p.household_id = h.id
            WHERE m.user_id = :user ORDER BY lower(h.name), lower(p.display_name)
        """),
        {"user": user_id},
    ).all()
    summary: dict[uuid.UUID, tuple[str, str, list[str]]] = {}
    for household_id, name, role, person in rows:
        entry = summary.setdefault(household_id, (name, role, []))
        if person:
            entry[2].append(person)
    return list(summary.values())
