"""Internal data model, independent of any particular phone app (ADR 0014).

Adapters (such as app/sensor_logger.py) translate each app's format into these
types. Everything after the adapter - storage, analysis, the agent - only sees these.
"""
from dataclasses import dataclass, field
from datetime import datetime

STEPS = "steps_total"  # running step count; resets at the start of a session or on reboot
LIGHT = "light_lux"    # ambient light in lux
BATTERY = "battery"    # level 0-1, plus whether the phone is charging


@dataclass(frozen=True)
class Reading:
    sensor: str
    at: datetime          # when it was recorded, in UTC
    value: float
    charging: bool | None = None  # battery readings only


@dataclass
class Batch:
    session_id: str
    batch_seq: int
    readings: list[Reading] = field(default_factory=list)
    received: int = 0     # raw items the phone sent
    ignored: int = 0      # unknown sensors or malformed items
