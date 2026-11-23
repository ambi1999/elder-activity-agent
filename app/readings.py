"""Internal data model, independent of any particular phone app (ADR 0014).

Adapters (``app/sensor_logger.py``, ``app/protocol_v1.py``) translate each app's
format into these types. Everything after an adapter (storage, analysis, the
agent) only sees these, so supporting another phone app never touches them.
"""

from dataclasses import dataclass, field
from datetime import datetime

# Sensor names, shared with phone-sensor-logger's protocol v1.
STEPS = "steps_total"  # running step count; resets at the start of a session or on reboot
LIGHT = "light_lux"  # ambient light in lux
BATTERY = "battery"  # level 0-1, plus whether the phone is charging
SCREEN = "screen"  # screen turned on or off
ACTIVITY = "activity"  # still, walking, running, ... from activity recognition
MOTION = "motion"  # acceleration without gravity, in m/s²


@dataclass(frozen=True)
class Reading:
    """One numeric value at one moment, stored raw or added to its minute.

    Attributes:
        sensor: One of STEPS, LIGHT, BATTERY or MOTION.
        at: When it was recorded, in UTC.
        value: The number (steps total, lux, battery level 0-1, or m/s²).
        charging: For battery readings only, whether the phone was charging.
    """

    sensor: str
    at: datetime
    value: float
    charging: bool | None = None


@dataclass(frozen=True)
class Event:
    """A change of state at one moment: the screen or the detected activity.

    Attributes:
        sensor: SCREEN or ACTIVITY.
        at: When it happened, in UTC.
        value: "on"/"off" for the screen; the activity type, e.g. "walking".
        confidence: For activity only, 0-100 when the phone reports it.
    """

    sensor: str
    at: datetime
    value: str
    confidence: int | None = None


@dataclass(frozen=True)
class MinuteSummary:
    """A numeric sensor aggregated by the phone over one UTC minute.

    Sums (not averages) are kept so several summaries for the same minute can
    be merged: average = total sum / total count.

    Attributes:
        sensor: LIGHT or MOTION.
        minute: Start of the minute, in UTC.
        count: Number of samples (at least 1).
        total: Sum of the samples.
        maximum: Largest sample.
    """

    sensor: str
    minute: datetime
    count: int
    total: float
    maximum: float


@dataclass
class Batch:
    """One upload from a phone, already translated into internal types.

    Attributes:
        session_id: The phone's logging session; with batch_seq, the batch's identity.
        batch_seq: Batch number within the session.
        readings: Numeric readings.
        events: Screen and activity changes.
        summaries: Per-minute aggregates computed on the phone.
        received: Raw items the phone sent.
        ignored: Items not used: unknown or not accepted sensors, or malformed items.
    """

    session_id: str
    batch_seq: int
    readings: list[Reading] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    summaries: list[MinuteSummary] = field(default_factory=list)
    received: int = 0
    ignored: int = 0
