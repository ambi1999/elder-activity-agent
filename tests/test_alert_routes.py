"""Alert routes: the scheduled check, the Telegram webhook and the email pages (ADR 0026)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alert_helpers import NOW, SETTINGS, fakes, local, make_family, token_of
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import alert_routes, alerts, contacts, main

client = TestClient(main.app)


@pytest.fixture
def notifiers(monkeypatch):
    fake = fakes()
    monkeypatch.setattr(alert_routes, "get_notifiers", lambda: fake)
    monkeypatch.setattr(alert_routes, "get_settings", lambda: SETTINGS)
    return fake


def open_alert(engine, notifiers):
    family = make_family(engine, activity=local(9, 5))
    with engine.begin() as conn:
        alerts.check_person(
            conn, family.person, NOW, SETTINGS, notifiers, lambda *a: alerts.explain.Explanation(a[2], "template")
        )
    return family


# ---------- /jobs/check-alerts ----------


def test_job_needs_its_token(migrated_db, monkeypatch, notifiers):
    monkeypatch.delenv("JOBS_TOKEN", raising=False)
    assert client.post("/jobs/check-alerts").status_code == 503
    monkeypatch.setenv("JOBS_TOKEN", "job-token-for-tests")
    assert client.post("/jobs/check-alerts", headers={"Authorization": "Bearer wrong"}).status_code == 401
    response = client.post("/jobs/check-alerts", headers={"Authorization": "Bearer job-token-for-tests"})
    assert response.status_code == 200
    assert set(response.json()) == {"people", "opened", "resolved", "sent", "failed"}


def test_job_runs_the_check(migrated_db, monkeypatch, notifiers):
    monkeypatch.setenv("JOBS_TOKEN", "job-token-for-tests")
    make_family(migrated_db, last_data=datetime.now(UTC) - timedelta(hours=7))
    response = client.post("/jobs/check-alerts", headers={"Authorization": "Bearer job-token-for-tests"})
    assert response.json()["opened"] == 1
    assert notifiers["email"].subjects == ["Mum's phone has stopped sending"]


# ---------- /telegram/webhook ----------

SECRET = {"X-Telegram-Bot-Api-Secret-Token": "webhook-secret-for-tests"}


def test_webhook_needs_the_secret(migrated_db, monkeypatch, notifiers):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret-for-tests")
    assert (
        client.post("/telegram/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "no"}).status_code == 401
    )


def test_start_links_the_chat(migrated_db, monkeypatch, notifiers):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret-for-tests")
    family = make_family(migrated_db)
    with migrated_db.begin() as conn:
        new = contacts.add_contact(conn, family.household_id, "Daughter", "telegram", datetime.now(UTC), SETTINGS)
    update = {"message": {"text": f"/start {token_of(new.link)}", "chat": {"id": 4242}}}

    assert client.post("/telegram/webhook", json=update, headers=SECRET).status_code == 200
    assert notifiers["telegram"].sent[0][0] == "4242"
    assert notifiers["telegram"].subjects == ["Linked"]
    with migrated_db.connect() as conn:
        assert contacts.find_telegram_contact(conn, family.household_id, "4242") is not None


def test_button_acknowledges_only_for_a_contact_of_that_household(migrated_db, monkeypatch, notifiers):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret-for-tests")
    family = open_alert(migrated_db, notifiers)
    with migrated_db.begin() as conn:
        new = contacts.add_contact(conn, family.household_id, "Daughter", "telegram", NOW, SETTINGS)
        contacts.confirm(conn, token_of(new.link), NOW, chat_id="4242")
        alert_id = conn.execute(text("SELECT id FROM alerts")).scalar()

    stranger = {"callback_query": {"id": "1", "data": f"ack:{alert_id}", "message": {"chat": {"id": 999}}}}
    client.post("/telegram/webhook", json=stranger, headers=SECRET)
    with migrated_db.connect() as conn:
        assert conn.execute(text("SELECT status FROM alerts")).scalar() == "open"

    press = {"callback_query": {"id": "2", "data": f"ack:{alert_id}", "message": {"chat": {"id": 4242}}}}
    client.post("/telegram/webhook", json=press, headers=SECRET)
    with migrated_db.connect() as conn:
        assert conn.execute(text("SELECT status, acknowledged_by FROM alerts")).one() == ("acknowledged", "Daughter")


def test_bad_button_data_is_ignored(migrated_db, monkeypatch, notifiers):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret-for-tests")
    update = {"callback_query": {"id": "1", "data": "ack:not-a-uuid", "message": {"chat": {"id": 1}}}}
    assert client.post("/telegram/webhook", json=update, headers=SECRET).status_code == 200
    update = {"callback_query": {"id": "1", "data": f"ack:{uuid.uuid4()}", "message": {"chat": {"id": 1}}}}
    assert client.post("/telegram/webhook", json=update, headers=SECRET).status_code == 200


# ---------- email pages ----------


def test_email_confirmation_page(migrated_db, notifiers):
    family = make_family(migrated_db)
    with migrated_db.begin() as conn:
        new = contacts.add_contact(
            conn, family.household_id, "Aunt", "email", datetime.now(UTC), SETTINGS, email="aunt@example.com"
        )
    path = f"/contacts/confirm/{token_of(new.link)}"

    page = client.get(path)
    assert page.status_code == 200 and "<button" in page.text  # opening the link alone confirms nothing
    assert client.post(path).status_code == 200
    assert client.post(path).status_code == 404


def test_acknowledge_page(migrated_db, notifiers):
    open_alert(migrated_db, notifiers)
    [(_, message)] = notifiers["email"].sent
    path = "/a/" + token_of(message.ack_url)

    page = client.get(path)
    assert page.status_code == 200
    assert "no steps, screen use or walking since 9:05 am" in page.text
    assert client.post(path).text.count("The others have been told") == 1
    assert "Already in hand" in client.post(path).text
    assert "already checking" in client.get(path).text
    assert client.get("/a/unknown-token").status_code == 404
