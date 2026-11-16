"""Adapter: translate Sensor Logger's HTTP push format into our internal readings (ADR 0014).

When Sensor Logger is replaced by our own Android app, this file is deleted;
nothing else depends on Sensor Logger's format.
"""
import math
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from app.readings import BATTERY, LIGHT, STEPS, Batch, Reading

MAX_READINGS_PER_BATCH = 10_000  # far above a normal batch; stops oversized requests (ADR 0020)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
CHARGING_STATES = {"charging", "full"}


class SensorLoggerBatch(BaseModel):
    """One message from Sensor Logger's HTTP push."""
    messageId: int
    sessionId: str = Field(min_length=1, max_length=200)
    deviceId: str = Field(max_length=200)
    payload: list[dict] = Field(default_factory=list, max_length=MAX_READINGS_PER_BATCH)


def _time(ns: object) -> datetime:
    # Sensor Logger sends nanoseconds since 1970. Integer maths keeps microsecond precision.
    if isinstance(ns, bool) or not isinstance(ns, int):
        raise ValueError("time must be an integer number of nanoseconds")
    return EPOCH + timedelta(microseconds=ns // 1000)


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("not a finite number")
    return float(value)


def _reading(item: dict) -> Reading | None:
    """Convert one item. Returns None for sensors we don't use; raises for malformed items."""
    name = item.get("name")
    values = item.get("values")
    if name == "pedometer":
        steps = values["steps"]
        if isinstance(steps, bool) or not isinstance(steps, int) or steps < 0:
            raise ValueError("steps must be a non-negative integer")
        return Reading(STEPS, _time(item.get("time")), float(steps))
    if name == "light":
        lux = _number(values["lux"])
        if lux < 0:
            raise ValueError("lux cannot be negative")
        return Reading(LIGHT, _time(item.get("time")), lux)
    if name == "battery":
        level = _number(values["batteryLevel"])
        if not 0 <= level <= 1:
            raise ValueError("battery level must be between 0 and 1")
        charging = values.get("batteryState") in CHARGING_STATES
        return Reading(BATTERY, _time(item.get("time")), level, charging=charging)
    return None  # a sensor we don't use, e.g. "test" from Test Push, or accelerometer


def to_batch(raw: SensorLoggerBatch) -> Batch:
    readings: list[Reading] = []
    ignored = 0
    for item in raw.payload:
        try:
            reading = _reading(item)
        except (KeyError, TypeError, ValueError, OverflowError):
            reading = None
        if reading is None:
            ignored += 1
        else:
            readings.append(reading)
    return Batch(
        session_id=raw.sessionId,
        batch_seq=raw.messageId,
        readings=readings,
        received=len(raw.payload),
        ignored=ignored,
    )
