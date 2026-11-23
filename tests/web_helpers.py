"""Shared set-up for the web app tests: people with phones, users, signing in, alerts, and a client."""

import re
import uuid
from datetime import UTC, datetime, timedelta

from alert_helpers import add_activity
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import auth, devices, households, main, web
from app.settings import get_settings

TZ = "Australia/Brisbane"
LINK = re.compile(r"/signin/link/([A-Za-z0-9_-]+)")


def new_client() -> TestClient:
    """A browser-like client. https, so the Secure session cookie is sent back; redirects not followed."""
    return TestClient(main.app, base_url="https://testserver", follow_redirects=False)


def make_person(engine, name: str, phone: bool = True, activity_minutes_ago: int | None = 10):
    """A household with one person and, unless phone=False, an active phone that sent data 5 minutes ago.

    Returns:
        (household id, person id, device id or None)
    """
    now = datetime.now(UTC)
    with engine.begin() as conn:
        household = households.create_household(conn, f"Household of {name}")
        person = households.add_person(conn, household.id, name, TZ)
        device_id = None
        if phone:
            device, _ = devices.create_device(conn, f"{name}'s phone", TZ, person_id=person.id)
            device_id = device.id
            conn.execute(
                text("UPDATE devices SET last_seen_at = :t WHERE id = :id"),
                {"t": now - timedelta(minutes=5), "id": device.id},
            )
            if activity_minutes_ago is not None:
                add_activity(conn, device.id, now - timedelta(minutes=activity_minutes_ago))
    return household.id, person.id, device_id


def make_user(engine, email: str, name: str, memberships: list[tuple[uuid.UUID, str]]) -> auth.User:
    """A user who is a member of each (household id, role)."""
    with engine.begin() as conn:
        user = auth.add_user(conn, email, name)
        for household_id, role in memberships:
            auth.add_member(conn, user.id, household_id, role)
    return user


def sign_in(client: TestClient, engine, user: auth.User) -> str:
    """Start a session for the user, as if they had used a link, and return its CSRF token."""
    now = datetime.now(UTC)
    with engine.begin() as conn:
        session_id = auth.create_session(conn, user.id, now, get_settings())
        session = auth.find_session(conn, session_id, now)
    assert session is not None
    client.cookies.set(web.COOKIE, session_id)
    return session.csrf_token


def add_alert(
    engine,
    person_id: uuid.UUID,
    rule: str = "inactivity",
    status: str = "open",
    hours_ago: int = 5,
    by: str | None = None,
) -> uuid.UUID:
    """An alert about a person, as the alert check would have opened it."""
    now = datetime.now(UTC)
    with engine.begin() as conn:
        return conn.execute(
            text("""
                INSERT INTO alerts (person_id, rule, status, since, explanation, explained_by, opened_at,
                                    acknowledged_by, acknowledged_at, resolved_at)
                VALUES (:person, :rule, :status, :since, 'Test explanation.', 'template', :opened,
                        :by, :ack_at, :resolved_at)
                RETURNING id
            """),
            {
                "person": person_id,
                "rule": rule,
                "status": status,
                "since": now - timedelta(hours=hours_ago),
                "opened": now - timedelta(hours=1),
                "by": by,
                "ack_at": now - timedelta(minutes=10) if by else None,
                "resolved_at": now - timedelta(minutes=5) if status == "resolved" else None,
            },
        ).scalar_one()


def alert_status(engine, alert_id: uuid.UUID) -> tuple[str, str | None]:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT status, acknowledged_by FROM alerts WHERE id = :id"), {"id": alert_id}).one()
    return row.status, row.acknowledged_by
