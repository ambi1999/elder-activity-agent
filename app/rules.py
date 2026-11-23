"""When to alert: the rules decide, deterministically (ADR 0026, stories E-1, E-2).

Pure functions with no database or clock of their own, so every case can be
tested exactly. ``app/alerts.py`` gathers a person's state and acts on the result.

Two rules:

- **phone_silent**: the phone has sent nothing for ``silent_hours``. Checked at
  any time of day; worded as a phone problem, not a concern about the person.
- **inactivity**: during waking hours, the data the phone *has* sent shows no
  activity for ``inactive_hours``. Only what the phone has reported counts, so a
  phone that is slow to upload never causes an inactivity alert by itself.

Activity means: steps increasing, the screen turning on or off, or the phone
detecting walking, running or cycling.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

INACTIVITY = "inactivity"
PHONE_SILENT = "phone_silent"
RULES = (PHONE_SILENT, INACTIVITY)

# Activity types (from the phone's activity recognition) that count as activity.
ACTIVE_TYPES = ("walking", "running", "on_bicycle")


@dataclass(frozen=True)
class AlertTiming:
    """One person's alert settings.

    Attributes:
        waking_from: Start of waking hours, local time.
        waking_to: End of waking hours, local time (later than waking_from).
        inactive_hours: Hours without activity, during waking hours, before alerting.
        silent_hours: Hours without any data from the phone before alerting.
    """

    waking_from: time
    waking_to: time
    inactive_hours: int
    silent_hours: int


@dataclass(frozen=True)
class PersonState:
    """What the data says about one person, as of ``now``.

    Attributes:
        timezone: The person's IANA timezone.
        timing: Their alert settings.
        last_data_at: When any of their phones last sent a batch (UTC), or None.
        last_activity_at: The latest activity in that data (UTC), or None.
    """

    timezone: str
    timing: AlertTiming
    last_data_at: datetime | None
    last_activity_at: datetime | None


@dataclass(frozen=True)
class Finding:
    """A rule that fires.

    Attributes:
        rule: INACTIVITY or PHONE_SILENT.
        since: When the quiet period began: the last activity, the start of
            waking hours if there was none today, or the last data (phone_silent).
        since_is_wake_start: True if ``since`` is the start of waking hours
            because there has been no activity since then.
    """

    rule: str
    since: datetime
    since_is_wake_start: bool = False


def waking_window(now: datetime, timezone: str, timing: AlertTiming) -> tuple[datetime, datetime]:
    """Today's waking hours (in the person's timezone), as UTC-aware datetimes."""
    zone = ZoneInfo(timezone)
    today = now.astimezone(zone).date()
    start = datetime.combine(today, timing.waking_from, tzinfo=zone)
    end = datetime.combine(today, timing.waking_to, tzinfo=zone)
    return start, end


def evaluate(state: PersonState, now: datetime) -> list[Finding]:
    """Which rules fire now. At most one: a silent phone hides inactivity.

    Args:
        state: The person's data and settings.
        now: Current time (timezone-aware).

    Returns:
        The findings, empty if all looks normal or there is no data at all.
    """
    if state.last_data_at is None:
        return []  # a phone that has never sent anything can't be judged
    if now - state.last_data_at >= timedelta(hours=state.timing.silent_hours):
        return [Finding(PHONE_SILENT, since=state.last_data_at)]

    wake_start, wake_end = waking_window(now, state.timezone, state.timing)
    if not wake_start <= now <= wake_end:
        return []

    activity = state.last_activity_at
    since_wake_start = activity is None or activity < wake_start
    quiet_since = wake_start if since_wake_start else activity
    assert quiet_since is not None  # noqa: S101 - for the type checker
    # Judge only the time the phone has reported on, never beyond its last data.
    covered_until = min(now, state.last_data_at)
    if covered_until - quiet_since >= timedelta(hours=state.timing.inactive_hours):
        return [Finding(INACTIVITY, since=quiet_since, since_is_wake_start=since_wake_start)]
    return []


def is_cleared(rule: str, since: datetime, state: PersonState) -> bool:
    """Whether an open alert's cause has gone away.

    Args:
        rule: The alert's rule.
        since: The alert's ``since`` time.
        state: The person's current data.

    Returns:
        True once there is activity after ``since`` (inactivity) or data after
        it (phone_silent).
    """
    if rule == PHONE_SILENT:
        return state.last_data_at is not None and state.last_data_at > since
    return state.last_activity_at is not None and state.last_activity_at > since
