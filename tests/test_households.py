"""Households, people and adding phones (ADR 0024, story A-2), against a real database.

Verifies: EA-FR-HH-001, EA-FR-HH-002, EA-FR-HH-003, EA-FR-HH-004, EA-FR-HH-005, EA-FR-HH-006
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import devices, households
from app.settings import load_settings

NOW = datetime.now(UTC)


def setup_household(engine, timezone="Australia/Brisbane"):
    with engine.begin() as conn:
        household = households.create_household(conn, "Family 1")
        person = households.add_person(conn, household.id, "Mum", timezone)
    return household, person


def test_add_phone_creates_a_pending_device_with_setup_qr_contents(migrated_db):
    settings = load_settings(environ={})
    _, person = setup_household(migrated_db)
    with migrated_db.begin() as conn:
        phone = households.add_phone(conn, person, "Mum's phone", NOW, settings)

    assert phone.device.status == "pending"
    assert phone.device.timezone == "Australia/Brisbane"
    assert phone.expires_at == NOW + timedelta(minutes=30)
    assert phone.provisioning["endpoint"] == settings.server.readings_endpoint
    assert phone.provisioning["profile"] == "activity"
    with migrated_db.connect() as conn:
        assert devices.find_device(conn, phone.provisioning["token"], NOW) is not None


def test_expiry_comes_from_the_setting(migrated_db):
    settings = load_settings(environ={"PAIRING__PENDING_TOKEN_EXPIRY_MINUTES": "60"})
    _, person = setup_household(migrated_db)
    with migrated_db.begin() as conn:
        phone = households.add_phone(conn, person, "Mum's phone", NOW, settings)
    assert phone.expires_at == NOW + timedelta(minutes=60)
    with migrated_db.connect() as conn:
        token = phone.provisioning["token"]
        assert devices.find_device(conn, token, NOW + timedelta(minutes=59)) is not None
        assert devices.find_device(conn, token, NOW + timedelta(minutes=61)) is None


def test_token_is_not_stored(migrated_db):
    _, person = setup_household(migrated_db)
    with migrated_db.begin() as conn:
        phone = households.add_phone(conn, person, "Mum's phone", NOW, load_settings(environ={}))
    with migrated_db.connect() as conn:
        listed = households.list_households(conn)
    assert phone.provisioning["token"] not in str(listed)


def test_list_shows_households_people_and_phones(migrated_db):
    household, person = setup_household(migrated_db)
    with migrated_db.begin() as conn:
        households.add_phone(conn, person, "Mum's phone", NOW, load_settings(environ={}))
        listed = households.list_households(conn)
    assert [(r["household"], r["person"], r["device"], r["status"]) for r in listed] == [
        ("Family 1", "Mum", "Mum's phone", "pending")
    ]
    assert listed[0]["household_id"] == household.id


def test_unknown_timezone_is_refused(migrated_db):
    with migrated_db.begin() as conn:
        household = households.create_household(conn, "Family 1")
        with pytest.raises(ValueError, match="timezone"):
            households.add_person(conn, household.id, "Mum", "Mars/Olympus")


def test_overlong_phone_name_is_refused(migrated_db):
    _, person = setup_household(migrated_db)
    with migrated_db.begin() as conn, pytest.raises(ValueError, match="100"):
        households.add_phone(conn, person, "x" * 101, NOW, load_settings(environ={}))


def test_find_person(migrated_db):
    _, person = setup_household(migrated_db)
    with migrated_db.connect() as conn:
        assert households.find_person(conn, person.id) == person
        assert households.find_person(conn, uuid.uuid4()) is None


def test_delete_household_removes_people_phones_and_data(migrated_db):
    household, person = setup_household(migrated_db)
    with migrated_db.begin() as conn:
        phone = households.add_phone(conn, person, "Mum's phone", NOW, load_settings(environ={}))
        conn.execute(
            text(
                "INSERT INTO step_readings (device_id, session_id, recorded_at, steps_total) VALUES (:d, 's', now(), 5)"
            ),
            {"d": phone.device.id},
        )
        assert households.count_household_data(conn, household.id) == {"people": 1, "phones": 1, "data_rows": 1}

        assert households.delete_household(conn, household.id) is True

    with migrated_db.connect() as conn:
        assert households.find_household(conn, household.id) is None
        assert households.find_person(conn, person.id) is None
        assert devices.find_device(conn, phone.provisioning["token"], NOW) is None
        assert conn.execute(text("SELECT count(*) FROM step_readings")).scalar() == 0


def test_deleting_one_household_leaves_others(migrated_db):
    first, _ = setup_household(migrated_db)
    second, _ = setup_household(migrated_db)
    with migrated_db.begin() as conn:
        households.delete_household(conn, first.id)
    with migrated_db.connect() as conn:
        assert households.find_household(conn, second.id) == second


def test_deleting_an_unknown_household_reports_it(migrated_db):
    with migrated_db.begin() as conn:
        assert households.delete_household(conn, uuid.uuid4()) is False
