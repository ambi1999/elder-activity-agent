"""Adapter: phone-sensor-logger's protocol v1 batches to internal readings (ADR 0023).

The protocol (``protocol/phone-sensor-logger-v1/v1.md``) has two levels of checking:

- **The envelope** (protocol, session_id, batch_seq, sent_at, timezone, readings,
  summaries) must be valid, or the whole batch is rejected with 422, because
  without it the batch can't be identified or stored once.
- **Each item** inside a valid envelope is checked on its own. A bad item, or
  one for a sensor that isn't accepted, is counted as ignored and the rest of
  the batch is kept, so one bad reading never loses a whole batch.

Unknown fields are ignored at every level, so newer phones keep working.
Location is never accepted, whatever arrives (ADR 0022).
"""

import math
from collections.abc import Callable, Collection
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.readings import ACTIVITY, BATTERY, LIGHT, MOTION, SCREEN, STEPS, Batch, Event, MinuteSummary, Reading

PROTOCOL = "phone-sensor-logger/v1"
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
MAX_TIMESTAMP_MS = 4_102_444_800_000  # 2100-01-01, as in the protocol's schema
MAX_BATCH_SEQ = 9_007_199_254_740_991  # largest integer JSON numbers hold exactly
ACTIVITY_TYPES = {"still", "walking", "running", "on_bicycle", "in_vehicle", "tilting", "unknown"}
SUMMARISABLE = {LIGHT, MOTION}

Timestamp = Annotated[int, Field(strict=True, ge=0, le=MAX_TIMESTAMP_MS)]


class BatchEnvelope(BaseModel):
    """The top level of a protocol v1 batch. Any error here rejects the batch (422).

    Strict types: a timestamp sent as text, or a number where a list belongs, is
    an error rather than being converted, as the protocol requires.
    """

    model_config = ConfigDict(extra="ignore")

    protocol: Literal["phone-sensor-logger/v1"]
    session_id: Annotated[
        str, StringConstraints(strict=True, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    ]
    batch_seq: Annotated[int, Field(strict=True, ge=0, le=MAX_BATCH_SEQ)]
    sent_at: Timestamp
    timezone: Annotated[
        str,
        StringConstraints(strict=True, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+)*$"),
    ]
    readings: Annotated[list[Any], Field(strict=True)]
    summaries: Annotated[list[Any], Field(strict=True)]


class InvalidItem(ValueError):
    """One reading or summary is malformed; it is ignored, not the batch."""


def _time(value: object) -> datetime:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_TIMESTAMP_MS:
        raise InvalidItem("timestamps are integer milliseconds since 1970")
    return EPOCH + timedelta(milliseconds=value)


def _number(value: object, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise InvalidItem("not a finite number")
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise InvalidItem("number out of range")
    return float(value)


def _steps(item: dict[str, Any], at: datetime) -> Reading:
    value = item.get("value")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidItem("steps_total is a non-negative integer")
    return Reading(STEPS, at, float(value))


def _battery(item: dict[str, Any], at: datetime) -> Reading:
    charging = item.get("charging")
    if not isinstance(charging, bool):
        raise InvalidItem("battery needs charging true or false")
    return Reading(BATTERY, at, _number(item.get("level"), 0, 1), charging=charging)


def _screen(item: dict[str, Any], at: datetime) -> Event:
    on = item.get("on")
    if not isinstance(on, bool):
        raise InvalidItem("screen needs on true or false")
    return Event(SCREEN, at, "on" if on else "off")


def _activity(item: dict[str, Any], at: datetime) -> Event:
    kind = item.get("type")
    if kind not in ACTIVITY_TYPES:
        raise InvalidItem("unknown activity type")
    confidence = item.get("confidence")
    if confidence is not None and (
        isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 100
    ):
        raise InvalidItem("confidence is an integer 0-100")
    return Event(ACTIVITY, at, str(kind), confidence)


# How each accepted sensor's reading is converted. Location is deliberately absent.
_READING_PARSERS: dict[str, Callable[[dict[str, Any], datetime], Reading | Event]] = {
    STEPS: _steps,
    LIGHT: lambda item, at: Reading(LIGHT, at, _number(item.get("value"), minimum=0)),
    BATTERY: _battery,
    SCREEN: _screen,
    ACTIVITY: _activity,
    MOTION: lambda item, at: Reading(MOTION, at, _number(item.get("value"), minimum=0)),
}


def parse_reading(item: object, accepted: Collection[str]) -> Reading | Event | None:
    """Convert one reading.

    Args:
        item: One element of the batch's ``readings`` array.
        accepted: Sensors this service stores (``ingest.accepted_sensors``).

    Returns:
        The reading or event, or None if its sensor isn't accepted.

    Raises:
        InvalidItem: If the item is malformed.
    """
    if not isinstance(item, dict):
        raise InvalidItem("a reading is an object")
    sensor = item.get("sensor")
    at = _time(item.get("t"))
    if not isinstance(sensor, str) or sensor not in accepted or sensor not in _READING_PARSERS:
        return None
    return _READING_PARSERS[sensor](item, at)


def parse_summary(item: object, accepted: Collection[str]) -> MinuteSummary | None:
    """Convert one per-minute summary.

    Args:
        item: One element of the batch's ``summaries`` array.
        accepted: Sensors this service stores.

    Returns:
        The summary, or None if its sensor isn't accepted.

    Raises:
        InvalidItem: If the item is malformed, including a known sensor that may
            not be summarised (such as steps_total) or a minute that isn't whole.
    """
    if not isinstance(item, dict):
        raise InvalidItem("a summary is an object")
    sensor = item.get("sensor")
    minute = item.get("minute")
    if not isinstance(sensor, str):
        raise InvalidItem("summary without a sensor")
    if sensor in _READING_PARSERS and sensor not in SUMMARISABLE:
        raise InvalidItem(f"{sensor} is never sent as a summary")
    at = _time(minute)
    if isinstance(minute, int) and minute % 60_000 != 0:
        raise InvalidItem("minute must be the start of a minute")
    if sensor not in accepted or sensor not in SUMMARISABLE:
        return None
    count = item.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise InvalidItem("count is an integer of at least 1")
    total = _number(item.get("sum"), minimum=0)
    smallest = _number(item.get("min"), minimum=0)
    largest = _number(item.get("max"), minimum=0)
    if smallest > largest:
        raise InvalidItem("min is larger than max")
    return MinuteSummary(sensor, at, count, total, largest)


def to_batch(envelope: BatchEnvelope, accepted: Collection[str]) -> Batch:
    """Translate a validated envelope into a batch, ignoring bad or unaccepted items.

    Args:
        envelope: The batch's validated top level.
        accepted: Sensors this service stores.

    Returns:
        The batch, with counts of received and ignored items.
    """
    batch = Batch(session_id=envelope.session_id, batch_seq=envelope.batch_seq)
    batch.received = len(envelope.readings) + len(envelope.summaries)
    for raw in envelope.readings:
        try:
            converted = parse_reading(raw, accepted)
        except InvalidItem:
            converted = None
        if isinstance(converted, Reading):
            batch.readings.append(converted)
        elif isinstance(converted, Event):
            batch.events.append(converted)
        else:
            batch.ignored += 1
    for raw in envelope.summaries:
        try:
            summary = parse_summary(raw, accepted)
        except InvalidItem:
            summary = None
        if summary is None:
            batch.ignored += 1
        else:
            batch.summaries.append(summary)
    return batch
