"""Shared set-up for the alert tests: a household with Mum, her phone, contacts, and fake notifiers."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app import alerts, contacts, devices, households
from app.explain import Explanation
from app.messages import Message
from app.settings import load_settings

TZ = "Australia/Brisbane"
SETTINGS = load_settings(environ={"TELEGRAM__BOT_USERNAME": "family_alerts_bot"})


def local(hour: int, minute: int = 0, day: int = 23) -> datetime:
    """A local time in Brisbane, as UTC."""
    return datetime(2026, 11, day, hour, minute, tzinfo=ZoneInfo(TZ)).astimezone(UTC)


NOW = local(13, 10)


class FakeNotifier:
    """Records messages instead of sending them."""

    def __init__(self, channel: str, ok: bool = True) -> None:
        self.channel = channel
        self.ok = ok
        self.sent: list[tuple[str, Message]] = []

    def send(self, address: str, message: Message) -> bool:
        self.sent.append((address, message))
        return self.ok

    @property
    def subjects(self) -> list[str]:
        return [m.subject for _, m in self.sent]


def fakes(ok: bool = True) -> dict[str, FakeNotifier]:
    return {"email": FakeNotifier("email", ok), "telegram": FakeNotifier("telegram", ok)}


def template_only(finding, facts, template, timeout):  # same arguments as alerts.Explainer
    return Explanation(template, "template")


@dataclass
class Family:
    household_id: uuid.UUID
    person: alerts.Person
    device_id: uuid.UUID
    son: contacts.Contact


def token_of(link: str) -> str:
    return link.rstrip("/").split("/")[-1].split("start=")[-1]


def make_family(engine, last_data: datetime | None = NOW - timedelta(minutes=5), activity: datetime | None = None):
    """Mum with an active phone, and Son as a confirmed email contact."""
    with engine.begin() as conn:
        household = households.create_household(conn, "Family 1")
        person = households.add_person(conn, household.id, "Mum", TZ)
        device, _ = devices.create_device(conn, "Mum's phone", TZ, person_id=person.id)
        conn.execute(text("UPDATE devices SET last_seen_at = :t WHERE id = :id"), {"t": last_data, "id": device.id})
        if activity is not None:
            add_activity(conn, device.id, activity)
        new = contacts.add_contact(conn, household.id, "Son", "email", NOW, SETTINGS, email="son@example.com")
        son = contacts.confirm(conn, token_of(new.link), NOW)
    assert son is not None
    return Family(household.id, alerts.Person(person.id, household.id, "Mum", TZ), device.id, son)


def add_activity(conn, device_id: uuid.UUID, at: datetime) -> None:
    conn.execute(
        text("INSERT INTO device_events (device_id, sensor, recorded_at, value) VALUES (:d, 'screen', :t, 'on')"),
        {"d": device_id, "t": at},
    )


def check(engine, family: Family, now: datetime, notifiers, settings=SETTINGS) -> dict[str, int]:
    with engine.begin() as conn:
        return alerts.check_person(conn, family.person, now, settings, notifiers, template_only)
