"""The overview's words and order, and a day's activity by hour (ADR 0028, stories D-1, D-2, D-5)."""

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app import overview
from app.access import AlertView, VisiblePerson

TZ = "Australia/Brisbane"
NOW = datetime(2026, 11, 23, 3, 10, tzinfo=UTC)  # 1:10 pm in Brisbane
PERSON = VisiblePerson(uuid.uuid4(), uuid.uuid4(), "Household 1", "Mum", TZ, "owner", True)


def local(hour: int, minute: int = 0, day: int = 23) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=ZoneInfo(TZ)).astimezone(UTC)


def alert(status: str = "open", by: str | None = None) -> AlertView:
    return AlertView(
        uuid.uuid4(), PERSON, "inactivity", status, local(9, 5), "Text.", "template", local(13, 5), by, None, None
    )


# ---------- words (no database) ----------


def test_times_are_said_in_the_persons_timezone():
    assert overview.when(local(9, 5), TZ, NOW) == "9:05 am"
    assert overview.when(local(21, 30, day=22), TZ, NOW) == "yesterday 9:30 pm"
    assert overview.when(local(8, 0, day=20), TZ, NOW) == "Fri 20 Nov, 8:00 am"


def test_ago_is_rough_and_readable():
    assert overview.ago(NOW, NOW) == "just now"
    assert overview.ago(NOW - timedelta(minutes=14), NOW) == "14 min ago"
    assert overview.ago(NOW - timedelta(hours=3, minutes=40), NOW) == "3 h ago"
    assert overview.ago(NOW - timedelta(days=2, hours=1), NOW) == "2 days ago"
    assert overview.ago(NOW - timedelta(days=1, hours=1), NOW) == "1 day ago"


def test_who_is_checking():
    assert overview.checking(alert(), "Nurse") == ""
    assert overview.checking(alert("acknowledged", "Sam"), "Nurse") == " · Sam is checking"
    assert overview.checking(alert("acknowledged", "Nurse"), "Nurse") == " · You're checking"


def test_order_is_attention_first_then_longest_waiting():
    def status(level: str, name: str, since_hours: int | None = None, active_minutes: int | None = None):
        a = replace(alert(), since=NOW - timedelta(hours=since_hours)) if since_hours else None
        last = NOW - timedelta(minutes=active_minutes) if active_minutes is not None else None
        person = replace(PERSON, display_name=name)
        return overview.Status(person, level, "", a, last, None, None, None)

    statuses = [
        status("green", "Ahmed", active_minutes=30),
        status("none", "Tom"),
        status("red", "Margaret", since_hours=4),
        status("amber", "Rosa", since_hours=10),
        status("green", "Lin", active_minutes=5),
        status("red", "Joseph", since_hours=6),
    ]
    ordered = [s.person.display_name for s in sorted(statuses, key=overview._sort_key)]
    assert ordered == ["Joseph", "Margaret", "Rosa", "Lin", "Ahmed", "Tom"]
    assert overview.counts(statuses) == {"red": 2, "amber": 1, "green": 2, "none": 1}


def test_day_bounds_follow_the_local_day():
    start, end = overview.local_day_bounds(date(2026, 11, 23), TZ)
    assert start.astimezone(UTC) == datetime(2026, 11, 22, 14, 0, tzinfo=UTC)  # Brisbane is UTC+10
    assert end - start == timedelta(days=1)


# ---------- a day's activity (database) ----------


def test_steps_by_local_hour_and_active_hours(migrated_db):
    from web_helpers import make_person

    _, person_id, device_id = make_person(migrated_db, "Mum", activity_minutes_ago=None)
    readings = [
        (local(21, 50, day=22), 900),  # yesterday evening's last count, in the same session
        (local(8, 10), 1000),  # +100 in the 8 am hour (compared with the reading before the day)
        (local(8, 40), 1300),  # +300 in the 8 am hour
        (local(13, 5), 1350),  # +50 in the 1 pm hour
    ]
    with migrated_db.begin() as conn:
        for at, total in readings:
            conn.execute(
                text("""
                    INSERT INTO step_readings (device_id, session_id, recorded_at, steps_total)
                    VALUES (:d, 's1', :t, :n)
                """),
                {"d": device_id, "t": at, "n": total},
            )
        # Screen use at 6 am counts as an active hour, though there were no steps then.
        conn.execute(
            text("INSERT INTO device_events (device_id, sensor, recorded_at, value) VALUES (:d, 'screen', :t, 'on')"),
            {"d": device_id, "t": local(6, 30)},
        )
    person = replace(PERSON, id=person_id)
    with migrated_db.connect() as conn:
        day = overview.day_activity(conn, person, date(2026, 11, 23))
    assert day.steps_by_hour[8] == 400
    assert day.steps_by_hour[13] == 50
    assert day.steps == 450
    assert day.active_hours == 3  # 6 am (screen), 8 am, 1 pm
