"""The alert lifecycle against a real database (ADR 0026, stories E-1 to E-5)."""

from datetime import time, timedelta

import pytest
from alert_helpers import NOW, SETTINGS, add_activity, check, fakes, local, make_family, token_of
from sqlalchemy import text

from app import alerts, contacts, rules
from app.alerts import MAX_FAILURES_PER_CONTACT


def deliveries(engine):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text("SELECT kind, result FROM alert_deliveries ORDER BY created_at"))]


def statuses(engine):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text("SELECT rule, status, resends FROM alerts"))]


def test_inactivity_alert_goes_once_to_confirmed_contacts_only(migrated_db):
    family = make_family(migrated_db, activity=local(9, 5))
    with migrated_db.begin() as conn:  # Daughter hasn't pressed Start yet: she gets nothing
        contacts.add_contact(conn, family.household_id, "Daughter", "telegram", NOW, SETTINGS)
    notifiers = fakes()

    assert check(migrated_db, family, NOW, notifiers) == {"opened": 1, "resolved": 0, "sent": 1}
    assert notifiers["email"].subjects == ["No activity for 4 hours: Mum"]
    [(address, message)] = notifiers["email"].sent
    assert address == "son@example.com"
    assert "since 9:05 am" in message.text
    assert message.ack_url and "/a/" in message.ack_url
    assert notifiers["telegram"].sent == []

    # Five minutes later: still the same alert, nothing sent again.
    assert check(migrated_db, family, NOW + timedelta(minutes=5), notifiers) == {"opened": 0, "resolved": 0, "sent": 0}
    assert statuses(migrated_db) == [("inactivity", "open", 0)]


def test_nothing_happens_when_all_looks_normal(migrated_db):
    family = make_family(migrated_db, activity=NOW - timedelta(minutes=30))
    notifiers = fakes()
    assert check(migrated_db, family, NOW, notifiers) == {"opened": 0, "resolved": 0, "sent": 0}
    assert statuses(migrated_db) == []


def test_unacknowledged_alert_repeats_up_to_the_limit(migrated_db):
    family = make_family(migrated_db, activity=local(9, 5))
    notifiers = fakes()
    check(migrated_db, family, NOW, notifiers)
    minutes = SETTINGS.alerts.resend_after_minutes
    for i in range(1, SETTINGS.alerts.max_resends + 2):
        check(migrated_db, family, NOW + timedelta(minutes=minutes * i + 1), notifiers)
    assert len(notifiers["email"].sent) == 1 + SETTINGS.alerts.max_resends
    assert statuses(migrated_db) == [("inactivity", "open", SETTINGS.alerts.max_resends)]


def test_acknowledging_tells_everyone_and_stops_repeats(migrated_db):
    family = make_family(migrated_db, activity=local(9, 5))
    notifiers = fakes()
    check(migrated_db, family, NOW, notifiers)
    [(_, message)] = notifiers["email"].sent

    with migrated_db.begin() as conn:
        alert, person, name = alerts.alert_for_ack_token(conn, token_of(message.ack_url))
        assert (person.display_name, name) == ("Mum", "Son")
        assert alerts.acknowledge(conn, alert.id, name, NOW + timedelta(minutes=2), SETTINGS, notifiers) is True
        assert alerts.acknowledge(conn, alert.id, name, NOW + timedelta(minutes=3), SETTINGS, notifiers) is False

    assert notifiers["email"].subjects[-1] == "Son is checking on Mum"
    check(migrated_db, family, NOW + timedelta(hours=3), notifiers)
    assert notifiers["email"].subjects.count("No activity for 4 hours: Mum") == 1
    assert statuses(migrated_db) == [("inactivity", "acknowledged", 0)]


def test_alert_resolves_when_activity_resumes(migrated_db):
    family = make_family(migrated_db, activity=local(9, 5))
    notifiers = fakes()
    check(migrated_db, family, NOW, notifiers)
    with migrated_db.begin() as conn:
        add_activity(conn, family.device_id, NOW + timedelta(minutes=10))
        conn.execute(text("UPDATE devices SET last_seen_at = :t"), {"t": NOW + timedelta(minutes=10)})

    assert check(migrated_db, family, NOW + timedelta(minutes=15), notifiers)["resolved"] == 1
    assert notifiers["email"].subjects[-1] == "All clear: Mum"
    assert statuses(migrated_db) == [("inactivity", "resolved", 0)]


def test_steps_going_up_count_as_activity(migrated_db):
    family = make_family(migrated_db, activity=None)
    with migrated_db.begin() as conn:
        for minutes, steps in ((-20, 100), (-19, 130)):
            conn.execute(
                text("""INSERT INTO step_readings (device_id, session_id, recorded_at, steps_total)
                        VALUES (:d, 's', :t, :v)"""),
                {"d": family.device_id, "t": NOW + timedelta(minutes=minutes), "v": steps},
            )
    with migrated_db.connect() as conn:
        snap = alerts.snapshot(conn, family.person, alerts.get_timing(conn, family.person.id, SETTINGS), NOW)
    assert snap.state.last_activity_at == NOW - timedelta(minutes=19)
    assert snap.steps_today == 30


def test_phone_silent_alert(migrated_db):
    family = make_family(migrated_db, last_data=NOW - timedelta(hours=7), activity=NOW - timedelta(hours=7))
    notifiers = fakes()
    check(migrated_db, family, NOW, notifiers)
    assert notifiers["email"].subjects == ["Mum's phone has stopped sending"]
    assert statuses(migrated_db) == [("phone_silent", "open", 0)]


def test_quiet_hours_defer_the_alert_until_they_end(migrated_db):
    family = make_family(migrated_db, activity=local(9, 5))
    with migrated_db.begin() as conn:
        contacts.set_quiet_hours(conn, family.son.id, time(12), time(14))
    notifiers = fakes()

    check(migrated_db, family, NOW, notifiers)
    check(migrated_db, family, NOW + timedelta(minutes=5), notifiers)
    assert notifiers["email"].sent == []
    assert deliveries(migrated_db) == [("opened", "deferred")]  # recorded once, not every check

    check(migrated_db, family, local(14, 5), notifiers)
    assert notifiers["email"].subjects == ["No activity for 4 hours: Mum"]


def test_failed_sends_are_retried_then_given_up(migrated_db):
    family = make_family(migrated_db, activity=local(9, 5))
    notifiers = fakes(ok=False)
    for i in range(MAX_FAILURES_PER_CONTACT + 2):
        check(migrated_db, family, NOW + timedelta(minutes=5 * i), notifiers)
    assert len(notifiers["email"].sent) == MAX_FAILURES_PER_CONTACT


def test_check_all_checks_everyone_with_an_active_phone(migrated_db):
    make_family(migrated_db, activity=local(9, 5))
    make_family(migrated_db, activity=NOW - timedelta(minutes=10))
    totals = alerts.check_all(
        migrated_db, NOW, SETTINGS, fakes(), explainer=lambda *a: alerts.explain.Explanation(a[2], "template")
    )
    assert totals == {"people": 2, "opened": 1, "resolved": 0, "sent": 1, "failed": 0}


def test_alert_settings_default_then_saved(migrated_db):
    family = make_family(migrated_db)
    with migrated_db.begin() as conn:
        assert alerts.get_timing(conn, family.person.id, SETTINGS) == rules.AlertTiming(time(8), time(21), 4, 6)
        alerts.set_timing(conn, family.person.id, rules.AlertTiming(time(7), time(22), 2, 12))
        assert alerts.get_timing(conn, family.person.id, SETTINGS) == rules.AlertTiming(time(7), time(22), 2, 12)
        with pytest.raises(ValueError, match="1 to 12"):
            alerts.set_timing(conn, family.person.id, rules.AlertTiming(time(7), time(22), 13, 6))
        with pytest.raises(ValueError, match="start before"):
            alerts.set_timing(conn, family.person.id, rules.AlertTiming(time(22), time(7), 4, 6))


def test_settings_change_the_threshold(migrated_db):
    family = make_family(migrated_db, activity=NOW - timedelta(hours=2, minutes=5))
    with migrated_db.begin() as conn:
        alerts.set_timing(conn, family.person.id, rules.AlertTiming(time(8), time(21), 2, 6))
    notifiers = fakes()
    check(migrated_db, family, NOW, notifiers)
    assert notifiers["email"].subjects == ["No activity for 2 hours: Mum"]
