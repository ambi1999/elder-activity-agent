"""Alert contacts: adding, confirming by one-time link, quiet hours (stories C-1, D-3)."""

from datetime import time, timedelta

import pytest
from alert_helpers import NOW, SETTINGS, token_of

from app import contacts, households
from app.settings import load_settings


@pytest.fixture
def household_id(migrated_db):
    with migrated_db.begin() as conn:
        return households.create_household(conn, "Family 1").id


def test_email_contact_needs_confirming_once(migrated_db, household_id):
    with migrated_db.begin() as conn:
        new = contacts.add_contact(conn, household_id, "Son", "email", NOW, SETTINGS, email=" Son@Example.com ")
        assert new.link.startswith(SETTINGS.server.public_url + "/contacts/confirm/")
        assert contacts.list_contacts(conn, household_id, confirmed_only=True) == []

        confirmed = contacts.confirm(conn, token_of(new.link), NOW)
        assert confirmed is not None and confirmed.address == "son@example.com"
        assert contacts.confirm(conn, token_of(new.link), NOW) is None  # used
        assert [c.display_name for c in contacts.list_contacts(conn, household_id, confirmed_only=True)] == ["Son"]


def test_links_expire(migrated_db, household_id):
    with migrated_db.begin() as conn:
        new = contacts.add_contact(conn, household_id, "Son", "email", NOW, SETTINGS, email="son@example.com")
        later = NOW + timedelta(minutes=SETTINGS.alerts.link_expiry_minutes + 1)
        assert contacts.confirm(conn, token_of(new.link), later) is None


def test_invalid_email_is_refused(migrated_db, household_id):
    with migrated_db.begin() as conn, pytest.raises(ValueError, match="email address"):
        contacts.add_contact(conn, household_id, "Son", "email", NOW, SETTINGS, email="not-an-address")


def test_telegram_contact_links_the_chat_that_pressed_start(migrated_db, household_id):
    with migrated_db.begin() as conn:
        new = contacts.add_contact(conn, household_id, "Daughter", "telegram", NOW, SETTINGS)
        assert new.link.startswith("https://t.me/family_alerts_bot?start=")
        assert contacts.confirm(conn, token_of(new.link), NOW) is None  # an email confirmation can't link it
        linked = contacts.confirm(conn, token_of(new.link), NOW, chat_id="12345")
        assert linked is not None and linked.address == "12345"
        assert contacts.find_telegram_contact(conn, household_id, "12345") == linked


def test_same_chat_linked_twice_keeps_one_contact(migrated_db, household_id):
    with migrated_db.begin() as conn:
        first = contacts.add_contact(conn, household_id, "Daughter", "telegram", NOW, SETTINGS)
        second = contacts.add_contact(conn, household_id, "Daughter again", "telegram", NOW, SETTINGS)
        kept = contacts.confirm(conn, token_of(first.link), NOW, chat_id="12345")
        again = contacts.confirm(conn, token_of(second.link), NOW, chat_id="12345")
        assert again == kept
        assert len(contacts.list_contacts(conn, household_id)) == 1


def test_telegram_needs_the_bot_username(migrated_db, household_id):
    with migrated_db.begin() as conn, pytest.raises(ValueError, match="bot_username"):
        contacts.add_contact(conn, household_id, "Daughter", "telegram", NOW, load_settings(environ={}))


def test_quiet_hours_and_removal(migrated_db, household_id):
    with migrated_db.begin() as conn:
        new = contacts.add_contact(conn, household_id, "Son", "email", NOW, SETTINGS, email="son@example.com")
        assert contacts.set_quiet_hours(conn, new.contact.id, time(22), time(7)) is True
        with pytest.raises(ValueError):
            contacts.set_quiet_hours(conn, new.contact.id, time(22), None)
        assert contacts.list_contacts(conn, household_id)[0].quiet_from == time(22)
        assert contacts.remove_contact(conn, new.contact.id) is True
        assert contacts.list_contacts(conn, household_id) == []
