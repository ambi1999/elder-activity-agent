"""The alert rules, without a database: every case decided exactly (ADR 0026, stories E-1, E-2)."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.rules import INACTIVITY, PHONE_SILENT, AlertTiming, PersonState, evaluate, is_cleared

TZ = "Australia/Brisbane"  # UTC+10, no daylight saving: 10:00 local is 00:00 UTC
TIMING = AlertTiming(waking_from=time(8), waking_to=time(21), inactive_hours=4, silent_hours=6)


def local(hour: int, minute: int = 0, day: int = 23) -> datetime:
    """A local time in Brisbane, as UTC."""
    return datetime(2026, 11, day, hour, minute, tzinfo=ZoneInfo(TZ)).astimezone(UTC)


def state(last_data=None, last_activity=None, timing=TIMING):
    return PersonState(TZ, timing, last_data, last_activity)


def test_local_helper_is_right():
    assert local(13) == datetime(2026, 11, 23, 3, 0, tzinfo=UTC)
    assert local(8) == datetime(2026, 11, 22, 22, 0, tzinfo=UTC)


def test_recent_activity_is_normal():
    now = local(13)
    assert evaluate(state(now - timedelta(minutes=5), local(12, 30)), now) == []


def test_four_hours_without_activity_fires_inactivity():
    now = local(13, 10)
    findings = evaluate(state(last_data=now - timedelta(minutes=5), last_activity=local(9, 5)), now)
    assert [(f.rule, f.since, f.since_is_wake_start) for f in findings] == [(INACTIVITY, local(9, 5), False)]


def test_no_activity_since_waking_counts_from_wake_start():
    now = local(12, 5)
    findings = evaluate(state(last_data=now, last_activity=local(20, day=22)), now)
    assert [(f.rule, f.since, f.since_is_wake_start) for f in findings] == [(INACTIVITY, local(8), True)]


def test_only_reported_time_counts():
    # Last activity 9:05, but the phone's data only covers until 12:00: not 4 hours yet.
    now = local(13, 30)
    assert evaluate(state(last_data=local(12), last_activity=local(9, 5)), now) == []


def test_no_inactivity_alert_outside_waking_hours():
    now = local(22)
    assert evaluate(state(last_data=now, last_activity=local(14)), now) == []
    early = local(7, 59)
    assert evaluate(state(last_data=early, last_activity=None), early) == []


def test_phone_silent_fires_at_any_time_and_hides_inactivity():
    now = local(23, 30)
    findings = evaluate(state(last_data=local(17), last_activity=local(9)), now)
    assert [(f.rule, f.since) for f in findings] == [(PHONE_SILENT, local(17))]


def test_no_data_ever_means_nothing_to_judge():
    assert evaluate(state(), local(13)) == []


def test_thresholds_come_from_the_settings():
    timing = AlertTiming(time(8), time(21), inactive_hours=1, silent_hours=2)
    now = local(10, 1)
    assert [f.rule for f in evaluate(state(now, local(9), timing), now)] == [INACTIVITY]
    assert [f.rule for f in evaluate(state(now - timedelta(hours=2), None, timing), now)] == [PHONE_SILENT]


def test_alerts_clear_when_the_cause_goes_away():
    since = local(9, 5)
    assert is_cleared(INACTIVITY, since, state(local(13), local(13))) is True
    assert is_cleared(INACTIVITY, since, state(local(13), since)) is False
    assert is_cleared(PHONE_SILENT, local(17), state(local(23), None)) is True
    assert is_cleared(PHONE_SILENT, local(17), state(local(17), None)) is False
