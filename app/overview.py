"""What the web app shows about people: the care overview's statuses and a day's activity (ADR 0028, D-1, D-5).

The overview's colour for each person comes from their alerts, never from its
own rules, so rules added later appear here without changing this module:

- red, "Needs attention": an open or acknowledged no-activity alert;
- amber, "Phone not sending": an open or acknowledged phone-silent alert (a
  phone problem, kept apart from concern about the person);
- green, "All OK": no unresolved alert;
- grey, "No phone yet": nobody's phone is connected, so there is nothing to show.

Every status has an icon and words as well as a colour (WCAG 1.4.1).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import alerts, rules
from app.access import AlertView, VisiblePerson
from app.messages import clock
from app.settings import Settings

# Order on the overview: attention first (ADR 0028).
LEVELS = ("red", "amber", "green", "none")
WORDS = {"red": "Needs attention", "amber": "Phone not sending", "green": "All OK", "none": "No phone yet"}
STALE_DATA = timedelta(hours=1)  # the Today page warns if the phone hasn't sent for longer (story D-1)


@dataclass(frozen=True)
class Status:
    """One person's line on the overview, and the facts for their Today page."""

    person: VisiblePerson
    level: str  # one of LEVELS
    detail: str  # e.g. "No activity since 9:05 am · Sam is checking"
    alert: AlertView | None  # the alert behind red or amber
    last_activity_at: datetime | None
    last_data_at: datetime | None
    steps_today: int | None
    battery: float | None  # 0 to 1

    @property
    def words(self) -> str:
        """The status in words, e.g. "Needs attention"."""
        return WORDS[self.level]


@dataclass(frozen=True)
class Day:
    """A person's activity on one local day."""

    day: date
    steps_by_hour: list[int]  # 24 values, local hours 0 to 23
    active_hours: int  # hours with any steps, screen use or walking

    @property
    def steps(self) -> int:
        """Steps in the whole day."""
        return sum(self.steps_by_hour)


# ---------------------------------------------------------------------------
# Words for times
# ---------------------------------------------------------------------------


def when(moment: datetime, timezone: str, now: datetime) -> str:
    """A time in the person's timezone, with the day if it isn't today: "9:05 am", "yesterday 9:05 am"."""
    zone = ZoneInfo(timezone)
    days = (now.astimezone(zone).date() - moment.astimezone(zone).date()).days
    if days == 0:
        return clock(moment, timezone)
    if days == 1:
        return f"yesterday {clock(moment, timezone)}"
    return f"{moment.astimezone(zone).strftime('%a %d %b').replace(' 0', ' ')}, {clock(moment, timezone)}"


def ago(moment: datetime, now: datetime) -> str:
    """How long ago, roughly: "just now", "14 min ago", "3 h ago", "2 days ago"."""
    minutes = int((now - moment).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    if minutes < 24 * 60:
        return f"{minutes // 60} h ago"
    days = minutes // (24 * 60)
    return f"{days} day{'s' if days > 1 else ''} ago"


def checking(alert: AlertView, me: str) -> str:
    """Who is checking, if anyone: "", " · You're checking" or " · Sam is checking"."""
    if alert.status != "acknowledged" or not alert.acknowledged_by:
        return ""
    return " · You're checking" if alert.acknowledged_by == me else f" · {alert.acknowledged_by} is checking"


# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------


def person_status(
    conn: Connection, person: VisiblePerson, unresolved: list[AlertView], now: datetime, settings: Settings, me: str
) -> Status:
    """One person's status, from their unresolved alerts and their phones' latest data.

    Args:
        conn: Open connection.
        person: Someone the user may see.
        unresolved: That person's open or acknowledged alerts.
        now: Current time (UTC).
        settings: For the person's alert settings' defaults.
        me: The signed-in user's name, to say "You're checking".
    """
    who = alerts.Person(person.id, person.household_id, person.display_name, person.timezone)
    snap = alerts.snapshot(conn, who, alerts.get_timing(conn, person.id, settings), now)
    by_rule = {a.rule: a for a in unresolved}
    alert = by_rule.get(rules.INACTIVITY) or by_rule.get(rules.PHONE_SILENT)
    if alert is not None and alert.rule == rules.INACTIVITY:
        level, detail = "red", f"No activity since {when(alert.since, person.timezone, now)}{checking(alert, me)}"
    elif alert is not None:
        level, detail = "amber", f"Phone silent since {when(alert.since, person.timezone, now)}{checking(alert, me)}"
    elif not person.has_phone:
        level, detail = "none", "No phone connected yet"
    else:
        last = snap.state.last_activity_at
        level, detail = "green", f"Active {ago(last, now)}" if last else "No activity in the last 2 days"
    return Status(
        person=person,
        level=level,
        detail=detail,
        alert=alert,
        last_activity_at=snap.state.last_activity_at,
        last_data_at=snap.state.last_data_at,
        steps_today=snap.steps_today,
        battery=snap.battery,
    )


def _sort_key(status: Status) -> tuple[int, float, str]:
    # Attention first; within red and amber the longest-running alert first;
    # within green the most recently active first; then by name.
    level = LEVELS.index(status.level)
    if status.alert is not None:
        moment = status.alert.since.timestamp()
    elif status.last_activity_at is not None:
        moment = -status.last_activity_at.timestamp()
    else:
        moment = 0.0
    return level, moment, status.person.display_name.lower()


def overview(
    conn: Connection,
    people: list[VisiblePerson],
    all_alerts: list[AlertView],
    now: datetime,
    settings: Settings,
    me: str,
) -> list[Status]:
    """Everyone's status, needs attention first (story D-5)."""
    statuses = [
        person_status(
            conn, p, [a for a in all_alerts if a.person.id == p.id and a.status != "resolved"], now, settings, me
        )
        for p in people
    ]
    return sorted(statuses, key=_sort_key)


def counts(statuses: list[Status]) -> dict[str, int]:
    """How many people have each status, for the summary line."""
    return {level: sum(1 for s in statuses if s.level == level) for level in LEVELS}


# ---------------------------------------------------------------------------
# A day's activity
# ---------------------------------------------------------------------------


def local_day_bounds(day: date, timezone: str) -> tuple[datetime, datetime]:
    """The start and end of a local day, as aware datetimes (handles daylight saving)."""
    zone = ZoneInfo(timezone)
    return datetime.combine(day, time(), zone), datetime.combine(day + timedelta(days=1), time(), zone)


def day_activity(conn: Connection, person: VisiblePerson, day: date) -> Day:
    """Steps by local hour, and the number of active hours, for one local day (stories D-1, D-2).

    Every phone the person has had counts (past data stays when a phone is
    removed); phones never connected (pending) have no data anyway.
    """
    start, end = local_day_bounds(day, person.timezone)
    params = {
        "person": person.id,
        "tz": person.timezone,
        "start": start,
        "end": end,
        # Readings before the day starts, so the first step count of the day has one to compare with.
        "lookback": start - timedelta(hours=6),
        "types": list(rules.ACTIVE_TYPES),
    }
    steps = conn.execute(
        text("""
            WITH phones AS (SELECT id FROM devices WHERE person_id = :person AND status <> 'pending'),
            steps AS (
                SELECT recorded_at,
                       steps_total - lag(steps_total) OVER (
                           PARTITION BY device_id, session_id ORDER BY recorded_at) AS delta
                FROM step_readings
                WHERE device_id IN (SELECT id FROM phones) AND recorded_at >= :lookback AND recorded_at < :end
            )
            SELECT extract(hour FROM recorded_at AT TIME ZONE :tz)::int AS hour, sum(delta)::bigint AS steps
            FROM steps WHERE delta > 0 AND recorded_at >= :start
            GROUP BY 1
        """),
        params,
    ).all()
    other = conn.execute(
        text("""
            SELECT DISTINCT extract(hour FROM recorded_at AT TIME ZONE :tz)::int AS hour
            FROM device_events
            WHERE device_id IN (SELECT id FROM devices WHERE person_id = :person AND status <> 'pending')
              AND recorded_at >= :start AND recorded_at < :end
              AND (sensor = 'screen' OR (sensor = 'activity' AND value = ANY(:types)))
        """),
        params,
    ).all()
    by_hour = [0] * 24
    for row in steps:
        by_hour[row.hour] += int(row.steps)
    active = {h for h, n in enumerate(by_hour) if n > 0} | {row.hour for row in other}
    return Day(day=day, steps_by_hour=by_hour, active_hours=len(active))


def today(now: datetime, timezone: str) -> date:
    """Today's date where the person lives."""
    return now.astimezone(ZoneInfo(timezone)).date()
