"""End-to-end POST /v1/readings tests against a real Postgres database (ADR 0023, story C2b-1).

Verifies: EA-FR-ING-001, EA-FR-ING-002, EA-FR-ING-003, EA-FR-ING-004, EA-FR-ING-005, EA-FR-ING-006,
    EA-FR-ING-007, EA-FR-ING-008, EA-FR-ING-009, EA-NFR-REL-001, EA-NFR-SEC-004
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import devices, main

client = TestClient(main.app)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
# An hour ago, at the start of a minute: inside every plausibility limit.
T0 = (datetime.now(UTC) - timedelta(hours=1)).replace(second=0, microsecond=0)
PROBLEM = "application/problem+json"


def ms(seconds: float = 0) -> int:
    return int((T0 + timedelta(seconds=seconds) - EPOCH) / timedelta(milliseconds=1))


def batch(readings=(), summaries=(), seq=0, session="session-1"):
    return {
        "protocol": "phone-sensor-logger/v1",
        "session_id": session,
        "batch_seq": seq,
        "sent_at": ms(60),
        "timezone": "Australia/Brisbane",
        "app": {"name": "phone-sensor-logger", "version": "0.3.0"},
        "readings": list(readings),
        "summaries": list(summaries),
    }


def register(engine, pending_until=None):
    with engine.begin() as conn:
        return devices.create_device(conn, "Test phone", "UTC", pending_expires_at=pending_until)


def post(token, body):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/v1/readings", json=body, headers=headers)


def rows(engine, sql, **params):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def with_ingest(**changes):
    """main.settings with some ingest settings changed, for one test."""
    return main.settings.model_copy(update={"ingest": main.settings.ingest.model_copy(update=changes)})


# ---------- authentication (401) ----------


@pytest.mark.parametrize("token", ["", "not-a-real-token"])
def test_missing_or_unknown_token_is_401_problem(migrated_db, token):
    response = post(token, batch())
    assert response.status_code == 401
    assert response.headers["content-type"] == PROBLEM
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["status"] == 401


def test_revoked_device_is_401(migrated_db):
    device, token = register(migrated_db)
    with migrated_db.begin() as conn:
        devices.revoke_device(conn, device.id)
    assert post(token, batch()).status_code == 401


# ---------- pending phones (ADR 0024) ----------


def test_pending_phone_becomes_active_on_its_first_batch(migrated_db):
    device, token = register(migrated_db, pending_until=datetime.now(UTC) + timedelta(minutes=30))
    assert device.status == "pending"

    assert post(token, batch()).status_code == 200  # a heartbeat is enough

    [row] = rows(migrated_db, "SELECT status, pending_expires_at, last_seen_at FROM devices")
    assert row["status"] == "active"
    assert row["pending_expires_at"] is None
    assert row["last_seen_at"] is not None


def test_expired_pending_phone_is_401(migrated_db):
    _, token = register(migrated_db, pending_until=datetime.now(UTC) - timedelta(seconds=1))
    assert post(token, batch()).status_code == 401
    assert rows(migrated_db, "SELECT status FROM devices") == [{"status": "pending"}]


def test_active_phone_keeps_working_after_the_pending_time(migrated_db):
    _, token = register(migrated_db, pending_until=datetime.now(UTC) + timedelta(minutes=30))
    post(token, batch(seq=0))  # activates the phone
    later = datetime.now(UTC) + timedelta(days=1)  # long after the original expiry
    with migrated_db.connect() as conn:
        assert devices.find_device(conn, token, later) is not None


# ---------- storing ----------


def test_every_accepted_sensor_is_stored(migrated_db):
    device, token = register(migrated_db)
    readings = [
        {"sensor": "steps_total", "t": ms(0), "value": 12},
        {"sensor": "light_lux", "t": ms(1), "value": 10},
        {"sensor": "battery", "t": ms(2), "level": 0.8, "charging": True},
        {"sensor": "screen", "t": ms(3), "on": True},
        {"sensor": "activity", "t": ms(4), "type": "walking", "confidence": 90},
        {"sensor": "motion", "t": ms(5), "value": 1.5},
    ]
    summaries = [{"sensor": "light_lux", "minute": ms(0), "count": 4, "sum": 40.0, "min": 5, "max": 20}]

    response = post(token, batch(readings, summaries))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "stored": 7, "ignored": 0, "dropped": 0}
    assert rows(migrated_db, "SELECT steps_total FROM step_readings") == [{"steps_total": 12}]
    assert rows(migrated_db, "SELECT sensor, value, confidence FROM device_events ORDER BY recorded_at") == [
        {"sensor": "screen", "value": "on", "confidence": None},
        {"sensor": "activity", "value": "walking", "confidence": 90},
    ]
    [minute] = rows(migrated_db, "SELECT * FROM minute_summary WHERE device_id = :d", d=device.id)
    assert minute["minute"] == T0
    assert (minute["light_sum"], minute["light_samples"], minute["light_max"]) == (50, 5, 20)
    assert (minute["motion_sum"], minute["motion_samples"], minute["motion_max"]) == (1.5, 1, 1.5)
    assert minute["battery_level"] == pytest.approx(0.8)
    assert minute["battery_charging"] is True


def test_location_is_never_stored(migrated_db):
    _, token = register(migrated_db)
    location = {"sensor": "location", "t": ms(0), "lat": -27.47, "lon": 153.02, "accuracy_m": 1000}
    response = post(token, batch([location]))
    assert response.json() == {"status": "ok", "stored": 0, "ignored": 1, "dropped": 0}
    assert rows(migrated_db, "SELECT count(*) AS n FROM minute_summary") == [{"n": 0}]


def test_same_batch_twice_is_stored_once(migrated_db):
    _, token = register(migrated_db)
    body = batch([{"sensor": "steps_total", "t": ms(0), "value": 5}])
    assert post(token, body).json()["status"] == "ok"
    second = post(token, body)
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate", "stored": 0, "ignored": 0, "dropped": 0}
    assert rows(migrated_db, "SELECT count(*) AS n FROM step_readings") == [{"n": 1}]


def test_a_whole_upload_interval_is_kept(migrated_db):
    _, token = register(migrated_db)
    readings = [
        {"sensor": "steps_total", "t": ms(-15 * 60), "value": 1},
        {"sensor": "steps_total", "t": ms(0), "value": 9},
    ]
    assert post(token, batch(readings)).json()["dropped"] == 0


def test_future_readings_are_dropped(migrated_db):
    _, token = register(migrated_db)
    future = int((datetime.now(UTC) + timedelta(hours=1) - EPOCH) / timedelta(milliseconds=1))
    response = post(token, batch([{"sensor": "light_lux", "t": future, "value": 1}]))
    assert response.json()["dropped"] == 1


# ---------- rejecting (422, 413, 429) ----------


def test_invalid_batch_is_422_problem_naming_the_field(migrated_db):
    _, token = register(migrated_db)
    body = batch()
    body["sent_at"] = "yesterday"
    response = post(token, body)
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    assert "sent_at" in response.json()["detail"]
    assert rows(migrated_db, "SELECT count(*) AS n FROM ingested_batches") == [{"n": 0}]


def test_body_that_is_not_json_is_422(migrated_db):
    _, token = register(migrated_db)
    response = client.post(
        "/v1/readings",
        content=b"not json",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM


def test_too_many_items_is_413(migrated_db):
    _, token = register(migrated_db)
    readings = [{"sensor": "light_lux", "t": ms(0), "value": 1}] * (main.settings.ingest.max_items_per_batch + 1)
    response = post(token, batch(readings))
    assert response.status_code == 413
    assert response.headers["content-type"] == PROBLEM


def test_body_too_large_is_413_problem(migrated_db):
    _, token = register(migrated_db)
    body = json.dumps(batch()).encode() + b" " * (main.settings.ingest.max_body_bytes + 1)
    response = client.post(
        "/v1/readings", content=body, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert response.headers["content-type"] == PROBLEM


def test_too_many_batches_is_429_with_retry_after(migrated_db, monkeypatch):
    monkeypatch.setattr(main, "settings", with_ingest(batches_per_minute_per_device=2))
    _, token = register(migrated_db)
    _, other_token = register(migrated_db)

    assert [post(token, batch(seq=i)).status_code for i in range(2)] == [200, 200]
    refused = post(token, batch(seq=2))

    assert refused.status_code == 429
    assert refused.headers["content-type"] == PROBLEM
    assert int(refused.headers["retry-after"]) >= 1
    assert post(other_token, batch()).status_code == 200  # other phones are unaffected


def test_sensors_can_be_switched_off_in_settings(migrated_db, monkeypatch):
    monkeypatch.setattr(main, "settings", with_ingest(accepted_sensors=("steps_total",)))
    _, token = register(migrated_db)
    readings = [{"sensor": "steps_total", "t": ms(0), "value": 1}, {"sensor": "screen", "t": ms(0), "on": True}]
    assert post(token, batch(readings)).json() == {"status": "ok", "stored": 1, "ignored": 1, "dropped": 0}


def test_logs_never_contain_the_token_or_values(migrated_db, caplog):
    _, token = register(migrated_db)
    with caplog.at_level("INFO"):
        post(token, batch([{"sensor": "light_lux", "t": ms(0), "value": 123.456}]))
    assert token not in caplog.text
    assert "123.456" not in caplog.text
