"""Initial schema: devices, ingested batches, step readings, minute summaries.

See docs/adr/0013 (storage model) and 0011 (device authentication).

Revision ID: 0001
Revises:
Create Date: 2026-11-16
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per phone. token_hash holds a SHA-256 hash of the phone's token (Stage B);
    # the token itself is never stored.
    op.execute("""
        CREATE TABLE devices (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name          text NOT NULL,
            timezone      text NOT NULL DEFAULT 'UTC',
            token_hash    text UNIQUE,
            created_at    timestamptz NOT NULL DEFAULT now(),
            last_seen_at  timestamptz,
            revoked_at    timestamptz
        )
    """)

    # Batches already processed, so a batch the phone sends twice is skipped (idempotency).
    op.execute("""
        CREATE TABLE ingested_batches (
            device_id      uuid NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            session_id     text NOT NULL,
            batch_seq      bigint NOT NULL,
            reading_count  integer NOT NULL,
            received_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (device_id, session_id, batch_seq)
        )
    """)

    # Raw step running totals. They reset to 0 at the start of each session
    # (or on reboot for Android's step counter); steps per minute are calculated in queries.
    op.execute("""
        CREATE TABLE step_readings (
            device_id    uuid NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            session_id   text NOT NULL,
            recorded_at  timestamptz NOT NULL,
            steps_total  integer NOT NULL CHECK (steps_total >= 0),
            PRIMARY KEY (device_id, session_id, recorded_at)
        )
    """)
    op.execute("CREATE INDEX ix_step_readings_device_time ON step_readings (device_id, recorded_at)")

    # One row per phone per minute (UTC). Light is stored as sum + count so the average
    # stays correct when late batches add to a minute. battery_at keeps the latest battery
    # reading even if batches arrive out of order.
    op.execute("""
        CREATE TABLE minute_summary (
            device_id         uuid NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            minute            timestamptz NOT NULL,
            light_sum         double precision NOT NULL DEFAULT 0,
            light_samples     integer NOT NULL DEFAULT 0 CHECK (light_samples >= 0),
            light_max         double precision,
            battery_level     real CHECK (battery_level BETWEEN 0 AND 1),
            battery_charging  boolean,
            battery_at        timestamptz,
            readings          integer NOT NULL DEFAULT 0,
            updated_at        timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (device_id, minute)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE minute_summary")
    op.execute("DROP TABLE step_readings")
    op.execute("DROP TABLE ingested_batches")
    op.execute("DROP TABLE devices")
