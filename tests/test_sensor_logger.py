"""The Sensor Logger adapter (no database needed)."""

from datetime import UTC, datetime, timedelta

from app.readings import BATTERY, LIGHT, STEPS
from app.sensor_logger import SensorLoggerBatch, to_batch

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
T = datetime(2026, 11, 16, 3, 47, 23, 123456, tzinfo=UTC)


def ns(dt: datetime) -> int:
    return (dt - EPOCH) // timedelta(microseconds=1) * 1000


def convert(payload: list[dict]):
    return to_batch(SensorLoggerBatch(messageId=7, sessionId="sess", deviceId="dev", payload=payload))


def test_maps_known_sensors():
    batch = convert(
        [
            {"name": "pedometer", "time": ns(T), "values": {"steps": 15}},
            {"name": "light", "time": ns(T), "values": {"lux": 120.5}},
            {"name": "battery", "time": ns(T), "values": {"batteryLevel": 0.57, "batteryState": "charging"}},
        ]
    )
    assert [r.sensor for r in batch.readings] == [STEPS, LIGHT, BATTERY]
    assert [r.value for r in batch.readings] == [15.0, 120.5, 0.57]
    assert batch.readings[2].charging is True
    assert (batch.session_id, batch.batch_seq, batch.received, batch.ignored) == ("sess", 7, 3, 0)


def test_converts_nanoseconds_to_utc():
    batch = convert([{"name": "light", "time": ns(T), "values": {"lux": 1}}])
    assert batch.readings[0].at == T


def test_charging_states():
    def charging(state):
        values = {"batteryLevel": 0.5, "batteryState": state}
        return convert([{"name": "battery", "time": ns(T), "values": values}]).readings[0].charging

    assert charging("charging") is True
    assert charging("full") is True
    assert charging("unplugged") is False


def test_unknown_and_malformed_items_are_ignored():
    batch = convert(
        [
            {"name": "test", "time": ns(T), "values": {}},  # Test Push
            {"name": "accelerometer", "time": ns(T), "values": {"x": 1}},  # sensor we don't use
            {"name": "pedometer", "time": ns(T), "values": {"steps": -3}},  # negative steps
            {"name": "battery", "time": ns(T), "values": {"batteryLevel": 1.5}},  # level out of range
            {"name": "light", "time": "yesterday", "values": {"lux": 3}},  # bad timestamp
            {"name": "light", "time": ns(T)},  # no values
        ]
    )
    assert batch.readings == []
    assert batch.ignored == 6
