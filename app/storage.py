"""Saving batches of readings (ADR 0013).

Each batch is saved in one transaction:
  1. record the batch ID, skipping the batch if it was already processed (idempotency)
  2. drop implausible timestamps
  3. save step running totals (raw, they are sparse)
  4. add light and battery to per-minute summaries
  5. update the device's last_seen_at
If anything fails, the whole batch is rolled back, so the phone's retry starts clean.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app.readings import BATTERY, LIGHT, STEPS, Batch, Reading

# Readings stamped long before the rest of their batch are stale (Sensor Logger's first
# pedometer reading can be hours old). Readings from the future mean a wrong clock.
MAX_AGE_IN_BATCH = timedelta(minutes=10)
MAX_FUTURE = timedelta(minutes=5)


@dataclass(frozen=True)
class SaveResult:
    status: str        # "ok" or "duplicate"
    stored: int = 0
    ignored: int = 0   # unknown sensors or malformed items
    dropped: int = 0   # implausible timestamps


def filter_plausible(readings: list[Reading], now: datetime) -> tuple[list[Reading], int]:
    not_future = [r for r in readings if r.at <= now + MAX_FUTURE]
    if not not_future:
        return [], len(readings)
    newest = max(r.at for r in not_future)
    kept = [r for r in not_future if r.at >= newest - MAX_AGE_IN_BATCH]
    return kept, len(readings) - len(kept)


def save_batch(engine: Engine, device_id: uuid.UUID, batch: Batch, now: datetime) -> SaveResult:
    with engine.begin() as conn:
        if not _record_batch(conn, device_id, batch):
            return SaveResult(status="duplicate")
        readings, dropped = filter_plausible(batch.readings, now)
        _insert_steps(conn, device_id, batch.session_id, readings)
        _upsert_minutes(conn, device_id, readings)
        conn.execute(text("UPDATE devices SET last_seen_at = now() WHERE id = :id"), {"id": device_id})
    return SaveResult(status="ok", stored=len(readings), ignored=batch.ignored, dropped=dropped)


def _record_batch(conn: Connection, device_id: uuid.UUID, batch: Batch) -> bool:
    """Returns False if this batch was already processed."""
    row = conn.execute(
        text("""
            INSERT INTO ingested_batches (device_id, session_id, batch_seq, reading_count)
            VALUES (:device_id, :session_id, :batch_seq, :reading_count)
            ON CONFLICT DO NOTHING
            RETURNING 1
        """),
        {
            "device_id": device_id,
            "session_id": batch.session_id,
            "batch_seq": batch.batch_seq,
            "reading_count": batch.received,
        },
    ).first()
    return row is not None


def _insert_steps(conn: Connection, device_id: uuid.UUID, session_id: str, readings: list[Reading]) -> None:
    rows = [
        {"device_id": device_id, "session_id": session_id, "recorded_at": r.at, "steps_total": int(r.value)}
        for r in readings
        if r.sensor == STEPS
    ]
    if rows:
        conn.execute(
            text("""
                INSERT INTO step_readings (device_id, session_id, recorded_at, steps_total)
                VALUES (:device_id, :session_id, :recorded_at, :steps_total)
                ON CONFLICT DO NOTHING
            """),
            rows,
        )


_UPSERT_MINUTE = text("""
    INSERT INTO minute_summary (
        device_id, minute, light_sum, light_samples, light_max,
        battery_level, battery_charging, battery_at, readings, updated_at
    )
    VALUES (
        :device_id, :minute, :light_sum, :light_samples, :light_max,
        :battery_level, :battery_charging, :battery_at, :readings, now()
    )
    ON CONFLICT (device_id, minute) DO UPDATE SET
        light_sum     = minute_summary.light_sum + EXCLUDED.light_sum,
        light_samples = minute_summary.light_samples + EXCLUDED.light_samples,
        light_max     = GREATEST(minute_summary.light_max, EXCLUDED.light_max),
        -- Keep whichever battery reading is newest, whatever order batches arrive in.
        battery_level = CASE WHEN EXCLUDED.battery_at > minute_summary.battery_at
                               OR minute_summary.battery_at IS NULL
                             THEN COALESCE(EXCLUDED.battery_level, minute_summary.battery_level)
                             ELSE minute_summary.battery_level END,
        battery_charging = CASE WHEN EXCLUDED.battery_at > minute_summary.battery_at
                                  OR minute_summary.battery_at IS NULL
                                THEN COALESCE(EXCLUDED.battery_charging, minute_summary.battery_charging)
                                ELSE minute_summary.battery_charging END,
        battery_at    = GREATEST(minute_summary.battery_at, EXCLUDED.battery_at),
        readings      = minute_summary.readings + EXCLUDED.readings,
        updated_at    = now()
""")


def _upsert_minutes(conn: Connection, device_id: uuid.UUID, readings: list[Reading]) -> None:
    minutes: dict[datetime, dict] = {}
    for r in readings:
        minute = r.at.replace(second=0, microsecond=0)
        row = minutes.setdefault(minute, {
            "light_sum": 0.0, "light_samples": 0, "light_max": None,
            "battery_level": None, "battery_charging": None, "battery_at": None,
            "readings": 0,
        })
        row["readings"] += 1
        if r.sensor == LIGHT:
            row["light_sum"] += r.value
            row["light_samples"] += 1
            row["light_max"] = r.value if row["light_max"] is None else max(row["light_max"], r.value)
        elif r.sensor == BATTERY and (row["battery_at"] is None or r.at > row["battery_at"]):
            row["battery_level"] = r.value
            row["battery_charging"] = r.charging
            row["battery_at"] = r.at

    params = [{"device_id": device_id, "minute": minute, **values} for minute, values in minutes.items()]
    if params:
        conn.execute(_UPSERT_MINUTE, params)
