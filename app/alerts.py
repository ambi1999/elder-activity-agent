"""The alert lifecycle: check, open, deliver, repeat, acknowledge, resolve (ADR 0026, stories E-1 to E-5).

``check_all`` runs every few minutes (POST /jobs/check-alerts). For each person
with an active phone it:

1. gathers their state (last data, last activity) and settings,
2. asks ``app.rules`` which rules fire,
3. opens an alert for a new finding (explained by the LLM, or the template),
4. delivers it to every confirmed contact, respecting quiet hours,
5. repeats it after ``alerts.resend_after_minutes`` while nobody has acknowledged it,
6. resolves it, and says so, once the cause has gone away.

Acknowledging (from an email link or a Telegram button) tells every contact who
is checking and stops the repeats. Each person is processed in their own
transaction, so a problem with one never stops alerts for the others.
"""

import logging
import secrets
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app import contacts, explain, messages, rules
from app.contacts import Contact
from app.devices import hash_token
from app.notifiers import Notifier
from app.settings import Settings

log = logging.getLogger(__name__)

MAX_FAILURES_PER_CONTACT = 6  # failed sends of one alert to one contact before giving up
LOOKBACK = timedelta(days=2)  # how far back to look for the last activity

Explainer = Callable[[rules.Finding, explain.Facts, str, int], explain.Explanation]


@dataclass(frozen=True)
class Person:
    """Someone with at least one active phone."""

    id: uuid.UUID
    household_id: uuid.UUID
    display_name: str
    timezone: str


@dataclass(frozen=True)
class Alert:
    """One alert about one person."""

    id: uuid.UUID
    person_id: uuid.UUID
    rule: str
    status: str
    since: datetime
    explanation: str
    explained_by: str
    resends: int


@dataclass(frozen=True)
class Snapshot:
    """A person's state for the rules, plus facts for messages."""

    state: rules.PersonState
    battery: float | None
    steps_today: int | None


# ---------------------------------------------------------------------------
# Settings per person
# ---------------------------------------------------------------------------


def get_timing(conn: Connection, person_id: uuid.UUID, settings: Settings) -> rules.AlertTiming:
    """A person's alert settings, or the defaults from config/settings.toml if never set."""
    row = conn.execute(
        text("SELECT waking_from, waking_to, inactive_hours, silent_hours FROM alert_settings WHERE person_id = :id"),
        {"id": person_id},
    ).first()
    if row is not None:
        return rules.AlertTiming(*row)
    defaults = settings.alerts
    return rules.AlertTiming(
        defaults.default_waking_from,
        defaults.default_waking_to,
        defaults.default_inactive_hours,
        defaults.default_silent_hours,
    )


def set_timing(conn: Connection, person_id: uuid.UUID, timing: rules.AlertTiming) -> None:
    """Save a person's alert settings (story E-5).

    Raises:
        ValueError: If a value is outside its allowed range.
    """
    if not timing.waking_from < timing.waking_to:
        raise ValueError("Waking hours must start before they end (they can't cross midnight).")
    if not 1 <= timing.inactive_hours <= 12:
        raise ValueError("No-activity hours must be 1 to 12.")
    if not 1 <= timing.silent_hours <= 48:
        raise ValueError("Phone-silent hours must be 1 to 48.")
    conn.execute(
        text("""
            INSERT INTO alert_settings (person_id, waking_from, waking_to, inactive_hours, silent_hours)
            VALUES (:id, :wf, :wt, :ih, :sh)
            ON CONFLICT (person_id) DO UPDATE SET
                waking_from = EXCLUDED.waking_from, waking_to = EXCLUDED.waking_to,
                inactive_hours = EXCLUDED.inactive_hours, silent_hours = EXCLUDED.silent_hours,
                updated_at = now()
        """),
        {
            "id": person_id,
            "wf": timing.waking_from,
            "wt": timing.waking_to,
            "ih": timing.inactive_hours,
            "sh": timing.silent_hours,
        },
    )


# ---------------------------------------------------------------------------
# Reading the data
# ---------------------------------------------------------------------------


def people_to_check(conn: Connection) -> list[Person]:
    """Everyone with at least one active phone."""
    rows = conn.execute(
        text("""
            SELECT DISTINCT p.id, p.household_id, p.display_name, p.timezone
            FROM people p JOIN devices d ON d.person_id = p.id
            WHERE d.status = 'active'
            ORDER BY p.id
        """)
    ).all()
    return [Person(*row) for row in rows]


def snapshot(conn: Connection, person: Person, timing: rules.AlertTiming, now: datetime) -> Snapshot:
    """Gather what the rules need about one person, from all their active phones."""
    params: dict[str, Any] = {"person": person.id, "after": now - LOOKBACK}
    row = (
        conn.execute(
            text("""
                WITH phones AS (
                    SELECT id, last_seen_at FROM devices WHERE person_id = :person AND status = 'active'
                ),
                steps AS (
                    SELECT recorded_at,
                           steps_total - lag(steps_total) OVER (
                               PARTITION BY device_id, session_id ORDER BY recorded_at) AS delta
                    FROM step_readings
                    WHERE device_id IN (SELECT id FROM phones) AND recorded_at > :after
                )
                SELECT
                    (SELECT max(last_seen_at) FROM phones) AS last_data_at,
                    GREATEST(
                        (SELECT max(recorded_at) FROM steps WHERE delta > 0),
                        (SELECT max(recorded_at) FROM device_events
                          WHERE device_id IN (SELECT id FROM phones) AND recorded_at > :after
                            AND (sensor = 'screen' OR (sensor = 'activity' AND value = ANY(:active_types))))
                    ) AS last_activity_at,
                    (SELECT battery_level FROM minute_summary
                      WHERE device_id IN (SELECT id FROM phones) AND battery_at IS NOT NULL
                      ORDER BY battery_at DESC LIMIT 1) AS battery,
                    (SELECT sum(delta) FROM steps WHERE delta > 0 AND recorded_at >= :midnight) AS steps_today
            """),
            {
                **params,
                "active_types": list(rules.ACTIVE_TYPES),
                "midnight": datetime.combine(
                    now.astimezone(ZoneInfo(person.timezone)).date(), time(), ZoneInfo(person.timezone)
                ),
            },
        )
        .mappings()
        .one()
    )
    state = rules.PersonState(person.timezone, timing, row["last_data_at"], row["last_activity_at"])
    steps = row["steps_today"]
    return Snapshot(state, row["battery"], int(steps) if steps is not None else None)


def unresolved_alerts(conn: Connection, person_id: uuid.UUID) -> dict[str, Alert]:
    """The person's open or acknowledged alerts, by rule."""
    rows = conn.execute(
        text("""
            SELECT id, person_id, rule, status, since, explanation, explained_by, resends
            FROM alerts WHERE person_id = :id AND status <> 'resolved'
        """),
        {"id": person_id},
    ).all()
    return {row.rule: Alert(*row) for row in rows}


def find_alert(conn: Connection, alert_id: uuid.UUID) -> tuple[Alert, Person] | None:
    """An alert and its person, or None."""
    row = conn.execute(
        text("""
            SELECT a.id, a.person_id, a.rule, a.status, a.since, a.explanation, a.explained_by, a.resends,
                   p.household_id, p.display_name, p.timezone
            FROM alerts a JOIN people p ON p.id = a.person_id WHERE a.id = :id
        """),
        {"id": alert_id},
    ).first()
    if row is None:
        return None
    return Alert(*row[:8]), Person(row[1], row[8], row[9], row[10])


# ---------------------------------------------------------------------------
# Delivering
# ---------------------------------------------------------------------------


def _hours(rule: str, timing: rules.AlertTiming) -> int:
    return timing.inactive_hours if rule == rules.INACTIVITY else timing.silent_hours


def _record(
    conn: Connection, alert: Alert, contact: Contact, kind: str, result: str, ack_hash: str | None, now: datetime
) -> None:
    # The check's own clock, not the database's, so repeats are timed from it (and tests control it).
    conn.execute(
        text("""
            INSERT INTO alert_deliveries (alert_id, contact_id, kind, result, ack_token_hash, created_at)
            VALUES (:alert, :contact, :kind, :result, :ack, :now)
        """),
        {"alert": alert.id, "contact": contact.id, "kind": kind, "result": result, "ack": ack_hash, "now": now},
    )


def _deliver_alert(
    conn: Connection,
    alert: Alert,
    person: Person,
    contact: Contact,
    kind: str,
    hours: int,
    now: datetime,
    settings: Settings,
    notifiers: Mapping[str, Notifier],
    record_deferral: bool = True,
) -> bool:
    """Send an open alert to one contact, or defer it in their quiet hours. Returns True if sent.

    A deferral is recorded once (``record_deferral``), not at every check during
    the quiet hours; the next check after they end sends the alert.
    """
    if contact.address is None:
        return False
    if contacts.in_quiet_hours(contact, now, person.timezone):
        if record_deferral:
            _record(conn, alert, contact, kind, "deferred", None, now)
        return False
    ack_url, ack_hash = None, None
    if contact.channel == "email":
        token = secrets.token_urlsafe(24)
        ack_url, ack_hash = f"{settings.server.public_url}/a/{token}", hash_token(token)
    message = messages.opened(
        alert.rule, person.display_name, hours, alert.explanation, alert.explained_by == "llm", ack_url, str(alert.id)
    )
    sent = notifiers[contact.channel].send(contact.address, message)
    _record(conn, alert, contact, kind, "sent" if sent else "failed", ack_hash if sent else None, now)
    return sent


def _notify(
    conn: Connection,
    alert: Alert,
    targets: list[Contact],
    kind: str,
    message: messages.Message,
    notifiers: Mapping[str, Notifier],
    now: datetime,
) -> None:
    """Send an update (acknowledged, resolved) to contacts; not repeated if it fails."""
    for contact in targets:
        if contact.address is not None:
            sent = notifiers[contact.channel].send(contact.address, message)
            _record(conn, alert, contact, kind, "sent" if sent else "failed", None, now)


def _delivery_counts(conn: Connection, alert_id: uuid.UUID) -> dict[uuid.UUID, tuple[int, int, int]]:
    """Per contact: messages about the open alert (sent, failed, deferred)."""
    rows = conn.execute(
        text("""
            SELECT contact_id,
                   count(*) FILTER (WHERE result = 'sent') AS sent,
                   count(*) FILTER (WHERE result = 'failed') AS failed,
                   count(*) FILTER (WHERE result = 'deferred') AS deferred
            FROM alert_deliveries WHERE alert_id = :id AND kind IN ('opened', 'resend')
            GROUP BY contact_id
        """),
        {"id": alert_id},
    ).all()
    return {row.contact_id: (row.sent, row.failed, row.deferred) for row in rows}


def _last_sent(conn: Connection, alert_id: uuid.UUID) -> datetime | None:
    value: datetime | None = conn.execute(
        text("""
            SELECT max(created_at) FROM alert_deliveries
            WHERE alert_id = :id AND kind IN ('opened', 'resend') AND result = 'sent'
        """),
        {"id": alert_id},
    ).scalar()
    return value


def _reached(conn: Connection, alert_id: uuid.UUID, household: list[Contact]) -> list[Contact]:
    """Contacts who were sent anything about this alert."""
    ids = {
        row[0]
        for row in conn.execute(
            text("SELECT DISTINCT contact_id FROM alert_deliveries WHERE alert_id = :id AND result = 'sent'"),
            {"id": alert_id},
        )
    }
    return [c for c in household if c.id in ids]


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------


def _open_alert(
    conn: Connection,
    person: Person,
    finding: rules.Finding,
    snap: Snapshot,
    now: datetime,
    settings: Settings,
    explainer: Explainer,
) -> Alert:
    hours = _hours(finding.rule, snap.state.timing)
    template = messages.template_explanation(
        finding.rule, person.display_name, finding.since, person.timezone, finding.since_is_wake_start, snap.battery
    )
    last = snap.state.last_data_at or now
    facts = explain.Facts(
        since_local=messages.clock(finding.since, person.timezone),
        hours=hours,
        steps_today=snap.steps_today,
        battery=snap.battery,
        minutes_since_data=int((now - last).total_seconds() // 60),
    )
    explanation = explainer(finding, facts, template, settings.alerts.llm_timeout_seconds)
    row = conn.execute(
        text("""
            INSERT INTO alerts (person_id, rule, since, explanation, explained_by, opened_at)
            VALUES (:person, :rule, :since, :explanation, :by, :now)
            RETURNING id, person_id, rule, status, since, explanation, explained_by, resends
        """),
        {
            "person": person.id,
            "rule": finding.rule,
            "since": finding.since,
            "explanation": explanation.text,
            "by": explanation.source,
            "now": now,
        },
    ).one()
    log.info("alert opened person=%s rule=%s explained_by=%s", str(person.id)[:8], finding.rule, explanation.source)
    return Alert(*row)


def check_person(
    conn: Connection,
    person: Person,
    now: datetime,
    settings: Settings,
    notifiers: Mapping[str, Notifier],
    explainer: Explainer = explain.explain,
) -> dict[str, int]:
    """Run the rules for one person and act on them. Returns counts for the job's response."""
    counts = {"opened": 0, "resolved": 0, "sent": 0}
    timing = get_timing(conn, person.id, settings)
    snap = snapshot(conn, person, timing, now)
    findings = {f.rule: f for f in rules.evaluate(snap.state, now)}
    current = unresolved_alerts(conn, person.id)
    household = contacts.list_contacts(conn, person.household_id, confirmed_only=True)

    for rule in rules.RULES:
        alert = current.get(rule)
        if alert is not None and rules.is_cleared(rule, alert.since, snap.state):
            conn.execute(
                text("UPDATE alerts SET status = 'resolved', resolved_at = :now WHERE id = :id"),
                {"now": now, "id": alert.id},
            )
            at = snap.state.last_activity_at if rule == rules.INACTIVITY else snap.state.last_data_at
            message = messages.resolved(rule, person.display_name, at or now, person.timezone)
            _notify(conn, alert, _reached(conn, alert.id, household), "resolved", message, notifiers, now)
            counts["resolved"] += 1
            continue
        if alert is None and rule in findings:
            alert = _open_alert(conn, person, findings[rule], snap, now, settings, explainer)
            counts["opened"] += 1
        if alert is None or alert.status != "open":
            continue

        hours = _hours(rule, timing)
        delivered = _delivery_counts(conn, alert.id)
        # First delivery, or a retry for contacts deferred (quiet hours) or failed earlier.
        for contact in household:
            sent, failed, deferred = delivered.get(contact.id, (0, 0, 0))
            if sent == 0 and failed < MAX_FAILURES_PER_CONTACT:
                counts["sent"] += _deliver_alert(
                    conn,
                    alert,
                    person,
                    contact,
                    "opened",
                    hours,
                    now,
                    settings,
                    notifiers,
                    record_deferral=deferred == 0,
                )

        # Repeat to everyone while nobody has acknowledged it.
        last = _last_sent(conn, alert.id)
        due = last is not None and now - last >= timedelta(minutes=settings.alerts.resend_after_minutes)
        if due and alert.resends < settings.alerts.max_resends:
            conn.execute(text("UPDATE alerts SET resends = resends + 1 WHERE id = :id"), {"id": alert.id})
            for contact in household:
                counts["sent"] += _deliver_alert(
                    conn, alert, person, contact, "resend", hours, now, settings, notifiers
                )
    return counts


def check_all(
    engine: Engine,
    now: datetime,
    settings: Settings,
    notifiers: Mapping[str, Notifier],
    explainer: Explainer = explain.explain,
) -> dict[str, int]:
    """Check everyone with an active phone, each in their own transaction.

    Returns:
        Totals: people checked, alerts opened and resolved, messages sent, and
        people whose check failed (logged, retried at the next run).
    """
    totals = {"people": 0, "opened": 0, "resolved": 0, "sent": 0, "failed": 0}
    with engine.connect() as conn:
        people = people_to_check(conn)
    for person in people:
        totals["people"] += 1
        try:
            with engine.begin() as conn:
                for key, value in check_person(conn, person, now, settings, notifiers, explainer).items():
                    totals[key] += value
        except Exception:
            log.exception("Alert check failed for person %s", str(person.id)[:8])
            totals["failed"] += 1
    return totals


# ---------------------------------------------------------------------------
# Acknowledging
# ---------------------------------------------------------------------------


def acknowledge(
    conn: Connection, alert_id: uuid.UUID, by: str, now: datetime, settings: Settings, notifiers: Mapping[str, Notifier]
) -> bool:
    """Mark an open alert as being checked by someone, and tell every contact (story E-3).

    Returns:
        True if it was open and is now acknowledged; False if it was already
        acknowledged or resolved (nothing is sent again).
    """
    found = find_alert(conn, alert_id)
    if found is None:
        return False
    alert, person = found
    updated = conn.execute(
        text("""
            UPDATE alerts SET status = 'acknowledged', acknowledged_at = :now, acknowledged_by = :by
            WHERE id = :id AND status = 'open'
        """),
        {"now": now, "by": by, "id": alert_id},
    ).rowcount
    if updated != 1:
        return False
    timing = get_timing(conn, person.id, settings)
    message = messages.acknowledged(
        alert.rule, person.display_name, _hours(alert.rule, timing), by, now, person.timezone
    )
    household = contacts.list_contacts(conn, person.household_id, confirmed_only=True)
    _notify(conn, alert, household, "acknowledged", message, notifiers, now)
    log.info("alert acknowledged alert=%s", str(alert_id)[:8])
    return True


def alert_for_ack_token(conn: Connection, token: str) -> tuple[Alert, Person, str] | None:
    """The alert, person and contact name behind an email's "I'm checking" link, or None."""
    row = conn.execute(
        text("""
            SELECT d.alert_id, c.display_name FROM alert_deliveries d
            JOIN alert_contacts c ON c.id = d.contact_id
            WHERE d.ack_token_hash = :hash
        """),
        {"hash": hash_token(token)},
    ).first()
    if row is None:
        return None
    found = find_alert(conn, row.alert_id)
    return (*found, row.display_name) if found else None
