"""Which timestamps are believable (storage.filter_plausible), without a database."""

from datetime import UTC, datetime, timedelta

from app.readings import Event, MinuteSummary, Reading
from app.storage import SENSOR_LOGGER_RULES, Plausibility, filter_plausible

NOW = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
V1_RULES = Plausibility(max_future=timedelta(minutes=5), max_age=timedelta(days=7))


def light(at):
    return Reading("light_lux", at, 1.0)


def test_protocol_v1_keeps_a_whole_upload_interval():
    # A 15-minute batch must keep its oldest readings (unlike Sensor Logger's in-batch rule).
    items = [light(NOW - timedelta(minutes=15)), light(NOW)]
    assert filter_plausible(items, NOW, V1_RULES) == (items, 0)


def test_protocol_v1_drops_future_and_very_old_items():
    future, old, ok = light(NOW + timedelta(minutes=6)), light(NOW - timedelta(days=8)), light(NOW)
    assert filter_plausible([future, old, ok], NOW, V1_RULES) == ([ok], 2)


def test_sensor_logger_drops_readings_far_older_than_their_batch():
    stale, fresh = light(NOW - timedelta(minutes=30)), light(NOW)
    assert filter_plausible([stale, fresh], NOW, SENSOR_LOGGER_RULES) == ([fresh], 1)


def test_events_and_summaries_are_filtered_by_their_time():
    event = Event("screen", NOW + timedelta(hours=1), "on")
    summary = MinuteSummary("motion", NOW - timedelta(days=9), 1, 1.0, 1.0)
    assert filter_plausible([event], NOW, V1_RULES) == ([], 1)
    assert filter_plausible([summary], NOW, V1_RULES) == ([], 1)
