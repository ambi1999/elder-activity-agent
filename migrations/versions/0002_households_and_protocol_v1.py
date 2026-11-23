"""Households, people and pending devices; storage for protocol v1 sensors.

See docs/adr/0024 (households and pairing) and 0023 (protocol v1).

- households and people: who a phone belongs to. Every household's data is
  reached through its people and their devices.
- devices: person_id, and a status of pending, active or revoked. A pending
  device's token stops working at pending_expires_at unless its first batch
  arrives before then.
- device_events: screen on/off and activity changes.
- minute_summary: motion columns, like the light ones.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add households, people, device status and protocol v1 storage."""
    op.execute("""
        CREATE TABLE households (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name        text NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
    """)

    # The person being looked after. A nickname, not a full name (ADR 0022).
    op.execute("""
        CREATE TABLE people (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            household_id  uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
            display_name  text NOT NULL,
            timezone      text NOT NULL DEFAULT 'UTC',
            created_at    timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_people_household ON people (household_id)")

    # Existing devices (registered with register_device.py) have no person and
    # stay active; devices revoked before now become 'revoked'.
    op.execute("""
        ALTER TABLE devices
            ADD COLUMN person_id uuid REFERENCES people(id) ON DELETE CASCADE,
            ADD COLUMN status text NOT NULL DEFAULT 'active',
            ADD COLUMN pending_expires_at timestamptz
    """)
    op.execute("UPDATE devices SET status = 'revoked' WHERE revoked_at IS NOT NULL")
    op.execute("""
        ALTER TABLE devices
            ADD CONSTRAINT ck_devices_status CHECK (status IN ('pending', 'active', 'revoked')),
            -- A pending device always has an expiry; other devices never do.
            ADD CONSTRAINT ck_devices_pending_expiry CHECK ((status = 'pending') = (pending_expires_at IS NOT NULL))
    """)
    op.execute("CREATE INDEX ix_devices_person ON devices (person_id)")

    # Screen and activity changes, one row per change.
    op.execute("""
        CREATE TABLE device_events (
            device_id    uuid NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            sensor       text NOT NULL CHECK (sensor IN ('screen', 'activity')),
            recorded_at  timestamptz NOT NULL,
            value        text NOT NULL,
            confidence   smallint CHECK (confidence BETWEEN 0 AND 100),
            PRIMARY KEY (device_id, sensor, recorded_at)
        )
    """)
    op.execute("CREATE INDEX ix_device_events_device_time ON device_events (device_id, recorded_at)")

    op.execute("""
        ALTER TABLE minute_summary
            ADD COLUMN motion_sum double precision NOT NULL DEFAULT 0,
            ADD COLUMN motion_samples integer NOT NULL DEFAULT 0 CHECK (motion_samples >= 0),
            ADD COLUMN motion_max double precision
    """)


def downgrade() -> None:
    """Remove everything added by upgrade()."""
    op.execute("ALTER TABLE minute_summary DROP COLUMN motion_max, DROP COLUMN motion_samples, DROP COLUMN motion_sum")
    op.execute("DROP TABLE device_events")
    op.execute("DROP INDEX ix_devices_person")
    op.execute("""
        ALTER TABLE devices
            DROP CONSTRAINT ck_devices_pending_expiry,
            DROP CONSTRAINT ck_devices_status,
            DROP COLUMN pending_expires_at,
            DROP COLUMN status,
            DROP COLUMN person_id
    """)
    op.execute("DROP TABLE people")
    op.execute("DROP TABLE households")
