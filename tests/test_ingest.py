"""End-to-end /ingest tests against a real Postgres database."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import devices, main, storage

client = TestClient(main.app)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
# An hour ago, at the start of a minute, so test readings fall in one minute and are never "future".
T0 = (datetime.now(UTC) - timedelta(hours=1)).replace(second=0, microsecond=0)


def ns(dt: datetime) -> int:
    return (dt - EPOCH) // timedelta(microseconds=1) * 1000


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def light(when, lux):
    return {"name": "light", "time": ns(when), "values": {"lux": lux}, "accuracy": 3}


def steps(when, total):
    return {"name": "pedometer", "time": ns(when), "values": {"steps": total}}


def battery(when, level, state="unplugged"):
    return {"name": "battery", "time": ns(when), "values": {"batteryLevel": level, "batteryState": state}}


def batch(seq, payload, session="session-1"):
    return {"messageId": seq, "sessionId": session, "deviceId": "sensor-logger-id", "payload": payload}


def register(engine, name="Test phone"):
    with engine.begin() as conn:
        return devices.create_device(conn, name, "UTC")


def post(token, body):
    return client.post("/ingest", json=body, headers={"Authorization": f"Bearer {token}"})


def rows(engine, sql, **params):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def minute_rows(engine, device_id):
    found = rows(engine, "SELECT * FROM minute_summary WHERE device_id = :d ORDER BY minute", d=device_id)
    return [{k: v for k, v in r.items() if k not in ("device_id", "updated_at")} for r in found]


def count(engine, table):
    return rows(engine, f"SELECT count(*) AS n FROM {table}")[0]["n"]


# ---------- authentication ----------


def test_unknown_token_is_rejected(migrated_db):
    assert post("not-a-real-token", batch(1, [])).status_code == 401


def test_revoked_device_is_rejected(migrated_db):
    device, token = register(migrated_db)
    with migrated_db.begin() as conn:
        devices.revoke_device(conn, device.id)
    assert post(token, batch(1, [])).status_code == 401


def test_tokens_are_stored_only_as_hashes(migrated_db):
    _, token = register(migrated_db)
    stored = rows(migrated_db, "SELECT token_hash FROM devices")[0]["token_hash"]
    assert stored == devices.hash_token(token)
    assert token not in stored


# ---------- saving ----------


def test_valid_batch_is_saved(migrated_db):
    device, token = register(migrated_db)
    response = post(token, batch(1, [steps(at(0), 5), light(at(0), 10), light(at(1), 20), battery(at(2), 0.8)]))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "stored": 4, "ignored": 0, "dropped": 0}

    [row] = minute_rows(migrated_db, device.id)
    assert row["minute"] == T0
    assert (row["light_sum"], row["light_samples"], row["light_max"]) == (30, 2, 20)
    assert row["battery_level"] == pytest.approx(0.8)
    assert row["battery_charging"] is False
    assert row["readings"] == 4
    assert rows(migrated_db, "SELECT steps_total FROM step_readings") == [{"steps_total": 5}]
    assert rows(migrated_db, "SELECT last_seen_at FROM devices")[0]["last_seen_at"] is not None


def test_same_batch_twice_is_stored_once(migrated_db):
    device, token = register(migrated_db)
    body = batch(1, [light(at(0), 10)])

    assert post(token, body).json()["status"] == "ok"
    second = post(token, body)

    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert minute_rows(migrated_db, device.id)[0]["light_samples"] == 1


def test_batch_order_does_not_change_the_result(migrated_db):
    a = batch(1, [light(at(0), 10), light(at(5), 20), battery(at(10), 0.5)])
    b = batch(2, [light(at(20), 30), battery(at(30), 0.4, "charging")])

    in_order, token1 = register(migrated_db, "In order")
    reversed_order, token2 = register(migrated_db, "Reversed")
    post(token1, a)
    post(token1, b)
    post(token2, b)
    post(token2, a)

    first, second = minute_rows(migrated_db, in_order.id), minute_rows(migrated_db, reversed_order.id)
    assert first == second
    [row] = first
    assert (row["light_sum"], row["light_samples"], row["light_max"]) == (60, 3, 30)
    assert row["battery_level"] == pytest.approx(0.4)  # the newest battery reading wins
    assert row["battery_charging"] is True


def test_unknown_sensors_are_ignored(migrated_db):
    device, token = register(migrated_db)
    response = post(token, batch(1, [{"name": "test", "time": ns(at(0)), "values": {}}]))
    assert response.json() == {"status": "ok", "stored": 0, "ignored": 1, "dropped": 0}
    assert minute_rows(migrated_db, device.id) == []


def test_stale_and_future_readings_are_dropped(migrated_db):
    device, token = register(migrated_db)
    stale = steps(T0 - timedelta(minutes=110), 0)  # like Sensor Logger's first pedometer reading
    future = light(datetime.now(UTC) + timedelta(hours=1), 5)
    response = post(token, batch(1, [stale, light(at(0), 10), future]))

    assert response.json() == {"status": "ok", "stored": 1, "ignored": 0, "dropped": 2}
    assert count(migrated_db, "step_readings") == 0


def test_failure_mid_batch_saves_nothing_and_retry_works(migrated_db, monkeypatch):
    _, token = register(migrated_db)
    body = batch(1, [steps(at(0), 3), light(at(0), 10)])

    def fail(*args, **kwargs):
        raise SQLAlchemyError("simulated database failure")

    monkeypatch.setattr(storage, "_upsert_minutes", fail)
    assert post(token, body).status_code == 503
    assert count(migrated_db, "ingested_batches") == 0  # rolled back, so a retry isn't a "duplicate"
    assert count(migrated_db, "step_readings") == 0

    monkeypatch.undo()
    retry = post(token, body)
    assert retry.json() == {"status": "ok", "stored": 2, "ignored": 0, "dropped": 0}
