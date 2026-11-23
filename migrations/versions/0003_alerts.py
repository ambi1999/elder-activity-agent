"""Alerts: contacts, per-person settings, alerts and their deliveries (ADR 0026).

- alert_contacts: who is told, by email or Telegram. A contact is usable once
  confirmed: an email address by opening a link, a Telegram chat by pressing
  Start on a one-time link (which also records the chat id).
- alert_settings: when to alert, per person (waking hours, thresholds).
- alerts: one row per alert, open -> acknowledged -> resolved. At most one
  unresolved alert per person and rule, so an alert is never raised twice.
- alert_deliveries: every message sent (or deferred, or failed) for an alert,
  with a one-time acknowledge token for email links.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-23
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the alert tables."""
    op.execute("""
        CREATE TABLE alert_contacts (
            id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            household_id      uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
            display_name      text NOT NULL,
            channel           text NOT NULL CHECK (channel IN ('email', 'telegram')),
            -- An email address, or a Telegram chat id once the contact has pressed Start.
            address           text,
            confirmed_at      timestamptz,
            -- One-time link to confirm the email address or link the Telegram chat (hash only).
            link_token_hash   text UNIQUE,
            link_expires_at   timestamptz,
            -- No messages between these local times (in the person's timezone); both or neither.
            quiet_from        time,
            quiet_to          time,
            created_at        timestamptz NOT NULL DEFAULT now(),
            CHECK ((quiet_from IS NULL) = (quiet_to IS NULL)),
            CHECK (confirmed_at IS NULL OR address IS NOT NULL)
        )
    """)
    op.execute("CREATE INDEX ix_alert_contacts_household ON alert_contacts (household_id)")
    op.execute("""
        CREATE UNIQUE INDEX ux_alert_contacts_address ON alert_contacts (household_id, channel, address)
        WHERE address IS NOT NULL
    """)

    # Defaults match config/settings.toml's [alerts] defaults for new people.
    op.execute("""
        CREATE TABLE alert_settings (
            person_id       uuid PRIMARY KEY REFERENCES people(id) ON DELETE CASCADE,
            waking_from     time NOT NULL DEFAULT '08:00',
            waking_to       time NOT NULL DEFAULT '21:00',
            inactive_hours  smallint NOT NULL DEFAULT 4 CHECK (inactive_hours BETWEEN 1 AND 12),
            silent_hours    smallint NOT NULL DEFAULT 6 CHECK (silent_hours BETWEEN 1 AND 48),
            updated_at      timestamptz NOT NULL DEFAULT now(),
            CHECK (waking_from < waking_to)
        )
    """)

    op.execute("""
        CREATE TABLE alerts (
            id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            person_id         uuid NOT NULL REFERENCES people(id) ON DELETE CASCADE,
            rule              text NOT NULL CHECK (rule IN ('inactivity', 'phone_silent')),
            status            text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'acknowledged', 'resolved')),
            -- What the rule saw: last activity (inactivity) or last data from the phone (phone_silent).
            since             timestamptz NOT NULL,
            explanation       text NOT NULL,
            explained_by      text NOT NULL CHECK (explained_by IN ('llm', 'template')),
            opened_at         timestamptz NOT NULL DEFAULT now(),
            acknowledged_at   timestamptz,
            acknowledged_by   text,
            resolved_at       timestamptz,
            resends           smallint NOT NULL DEFAULT 0
        )
    """)
    # At most one unresolved alert per person and rule.
    op.execute("CREATE UNIQUE INDEX ux_alerts_unresolved ON alerts (person_id, rule) WHERE status <> 'resolved'")

    op.execute("""
        CREATE TABLE alert_deliveries (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            alert_id        uuid NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
            contact_id      uuid NOT NULL REFERENCES alert_contacts(id) ON DELETE CASCADE,
            kind            text NOT NULL CHECK (kind IN ('opened', 'resend', 'acknowledged', 'resolved')),
            result          text NOT NULL CHECK (result IN ('sent', 'deferred', 'failed')),
            -- Hash of the one-time "I'm checking" link in emails.
            ack_token_hash  text UNIQUE,
            created_at      timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_alert_deliveries_alert ON alert_deliveries (alert_id)")


def downgrade() -> None:
    """Remove the alert tables."""
    op.execute("DROP TABLE alert_deliveries")
    op.execute("DROP TABLE alerts")
    op.execute("DROP TABLE alert_settings")
    op.execute("DROP TABLE alert_contacts")
