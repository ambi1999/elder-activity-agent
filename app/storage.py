"""Saving batches of readings (ADR 0013).

Each batch is saved in one transaction:
  1. record the batch's identity, skipping it if it was already processed (idempotency)
  2. drop implausible timestamps (rules depend on the phone app; see Plausibility)
  3. save step running totals raw (they are sparse)
  4. save screen and activity changes as events
  5. add light, motion and battery to per-minute summaries
  6. update the device's last_seen_at, and activate it if it was pending (ADR 0024)
If anything fails, the whole batch is rolled back, so the phone's retry starts clean.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app.readings import BATTERY, LIGHT, MOTION, STEPS, Batch, Event, MinuteSummary, Reading


@dataclass(frozen=True)
class Plausibility:
    """Which timestamps are believable. Items outside these limits are dropped.

    Attributes:
        max_future: Items stamped later than now + this are dropped (wrong clock).
        max_age_in_batch: If set, items older than the batch's newest item by
            more than this are dropped. Sensor Logger's first pedometer reading
            can be hours old, so its adapter uses this.
        max_age: If set, items older than now - this are dropped.
    """

    max_future: timedelta
    max_age_in_batch: timedelta | None = None
    max_age: timedelta | None = None


# Sensor Logger's rules, unchanged since Stage B.
SENSOR_LOGGER_RULES = Plausibility(max_future=timedelta(minutes=5), max_age_in_batch=timedelta(minutes=10))


@dataclass(frozen=True)
class SaveResult:
    """What happened to a batch, returned to the phone.

    Attributes:
        status: "ok", or "duplicate" if this batch was already stored.
        stored: Items stored.
        ignored: Items not used: unknown or not accepted sensors, or malformed.
        dropped: Items with implausible timestamps.
    """

    status: str
    stored: int = 0
    ignored: int = 0
    dropped: int = 0


def _time_of(item: Reading | Event | MinuteSummary) -> datetime:
    return item.minute if isinstance(item, MinuteSummary) else item.at


def filter_plausible[T: (Reading | Event | MinuteSummary)](
    items: list[T], now: datetime, rules: Plausibility, newest: datetime | None = None
) -> tuple[list[T], int]:
    """Keep the items whose timestamps are believable.

    Args:
        items: Readings, events or summaries.
        now: Current time in UTC, passed in so tests control the clock.
        rules: The limits to apply.
        newest: The newest believable time in the whole batch, for
            ``rules.max_age_in_batch``; worked out from ``items`` if not given.

    Returns:
        The kept items and how many were dropped.
    """
    kept = [item for item in items if _time_of(item) <= now + rules.max_future]
    if rules.max_age is not None:
        kept = [item for item in kept if _time_of(item) >= now - rules.max_age]
    if rules.max_age_in_batch is not None and kept:
        newest = newest or max(_time_of(item) for item in kept)
        kept = [item for item in kept if _time_of(item) >= newest - rules.max_age_in_batch]
    return kept, len(items) - len(kept)


def save_batch(
    engine: Engine, device_id: uuid.UUID, batch: Batch, now: datetime, rules: Plausibility = SENSOR_LOGGER_RULES
) -> SaveResult:
    """Store a batch once, in one transaction.

    Args:
        engine: Database engine.
        device_id: The authenticated device that sent the batch.
        batch: The batch, already translated by an adapter.
        now: Current time in UTC.
        rules: Which timestamps are believable for this phone app.

    Returns:
        Counts for the phone's response; status "duplicate" if already stored.
    """
    with engine.begin() as conn:
        if not _record_batch(conn, device_id, batch):
            return SaveResult(status="duplicate")

        # The newest believable time across the whole batch, so the in-batch
        # age rule treats readings, events and summaries alike.
        items: list[Reading | Event | MinuteSummary] = [*batch.readings, *batch.events, *batch.summaries]
        candidates = [_time_of(i) for i in items]
        believable = [t for t in candidates if t <= now + rules.max_future]
        newest = max(believable) if believable else None

        readings, dropped_r = filter_plausible(batch.readings, now, rules, newest)
        events, dropped_e = filter_plausible(batch.events, now, rules, newest)
        summaries, dropped_s = filter_plausible(batch.summaries, now, rules, newest)

        _insert_steps(conn, device_id, batch.session_id, readings)
        _insert_events(conn, device_id, events)
        _upsert_minutes(conn, device_id, readings, summaries)
        _mark_seen(conn, device_id)

    return SaveResult(
        status="ok",
        stored=len(readings) + len(events) + len(summaries),
        ignored=batch.ignored,
        dropped=dropped_r + dropped_e + dropped_s,
    )


def _record_batch(conn: Connection, device_id: uuid.UUID, batch: Batch) -> bool:
    """Record the batch's identity. Returns False if it was already processed."""
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


def _mark_seen(conn: Connection, device_id: uuid.UUID) -> None:
    # The first accepted batch turns a pending phone into an active one, so its
    # token no longer expires (ADR 0024). A revoked phone never gets this far.
    conn.execute(
        text("""
            UPDATE devices SET
                last_seen_at = now(),
                status = CASE WHEN status = 'pending' THEN 'active' ELSE status END,
                pending_expires_at = CASE WHEN status = 'pending' THEN NULL ELSE pending_expires_at END
            WHERE id = :id
        """),
        {"id": device_id},
    )


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


def _insert_events(conn: Connection, device_id: uuid.UUID, events: list[Event]) -> None:
    rows = [
        {"device_id": device_id, "sensor": e.sensor, "recorded_at": e.at, "value": e.value, "confidence": e.confidence}
        for e in events
    ]
    if rows:
        conn.execute(
            text("""
                INSERT INTO device_events (device_id, sensor, recorded_at, value, confidence)
                VALUES (:device_id, :sensor, :recorded_at, :value, :confidence)
                ON CONFLICT DO NOTHING
            """),
            rows,
        )


_UPSERT_MINUTE = text("""
    INSERT INTO minute_summary (
        device_id, minute, light_sum, light_samples, light_max,
        motion_sum, motion_samples, motion_max,
        battery_level, battery_charging, battery_at, readings, updated_at
    )
    VALUES (
        :device_id, :minute, :light_sum, :light_samples, :light_max,
        :motion_sum, :motion_samples, :motion_max,
        :battery_level, :battery_charging, :battery_at, :readings, now()
    )
    ON CONFLICT (device_id, minute) DO UPDATE SET
        light_sum      = minute_summary.light_sum + EXCLUDED.light_sum,
        light_samples  = minute_summary.light_samples + EXCLUDED.light_samples,
        light_max      = GREATEST(minute_summary.light_max, EXCLUDED.light_max),
        motion_sum     = minute_summary.motion_sum + EXCLUDED.motion_sum,
        motion_samples = minute_summary.motion_samples + EXCLUDED.motion_samples,
        motion_max     = GREATEST(minute_summary.motion_max, EXCLUDED.motion_max),
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


def _empty_minute() -> dict[str, Any]:
    return {
        "light_sum": 0.0,
        "light_samples": 0,
        "light_max": None,
        "motion_sum": 0.0,
        "motion_samples": 0,
        "motion_max": None,
        "battery_level": None,
        "battery_charging": None,
        "battery_at": None,
        "readings": 0,
    }


def _add(row: dict[str, Any], prefix: str, count: int, total: float, maximum: float) -> None:
    """Add samples of light or motion to one minute's row."""
    row[f"{prefix}_sum"] += total
    row[f"{prefix}_samples"] += count
    current = row[f"{prefix}_max"]
    row[f"{prefix}_max"] = maximum if current is None else max(current, maximum)
    row["readings"] += count


def _upsert_minutes(
    conn: Connection, device_id: uuid.UUID, readings: list[Reading], summaries: list[MinuteSummary]
) -> None:
    """Merge readings and phone-computed summaries into per-minute rows."""
    minutes: dict[datetime, dict[str, Any]] = {}
    for r in readings:
        row = minutes.setdefault(r.at.replace(second=0, microsecond=0), _empty_minute())
        if r.sensor == LIGHT:
            _add(row, "light", 1, r.value, r.value)
        elif r.sensor == MOTION:
            _add(row, "motion", 1, r.value, r.value)
        elif r.sensor == BATTERY:
            row["readings"] += 1
            if row["battery_at"] is None or r.at > row["battery_at"]:
                row["battery_level"] = r.value
                row["battery_charging"] = r.charging
                row["battery_at"] = r.at
        else:
            row["readings"] += 1  # steps: stored raw, but still counted in the minute
    for s in summaries:
        row = minutes.setdefault(s.minute, _empty_minute())
        _add(row, "light" if s.sensor == LIGHT else "motion", s.count, s.total, s.maximum)

    params = [{"device_id": device_id, "minute": minute, **values} for minute, values in minutes.items()]
    if params:
        conn.execute(_UPSERT_MINUTE, params)
