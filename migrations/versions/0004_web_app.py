"""Web app sign-in and access: users, members, sign-in links and sessions (ADR 0025, ADR 0028).

- users: people who sign in to the web app (family members, nurses), by email
  address only. Not the person being looked after, who never signs in.
- members: which households a user belongs to, and their role. A user may be a
  member of many households (a nurse), so what they can see is the set of
  people in all of them (ADR 0028).
- signin_links: one-time sign-in links sent by email. Only a hash of the token
  is stored, so a database leak can't be used to sign in.
- sessions: who is signed in, one row per browser. Only a hash of the session
  id (the cookie's value) is stored; deleting the row signs that browser out.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-24
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the web app's tables."""
    # Email addresses are stored lower-case (the app normalises them), so the
    # unique index treats Daughter@Example.com and daughter@example.com as one.
    op.execute("""
        CREATE TABLE users (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email           text NOT NULL UNIQUE CHECK (email = lower(email) AND position('@' in email) > 1),
            display_name    text NOT NULL,
            created_at      timestamptz NOT NULL DEFAULT now(),
            last_signin_at  timestamptz
        )
    """)

    # owner: can change settings, phones, contacts and members (step D2).
    # viewer: can see everything and acknowledge alerts, but not change settings.
    op.execute("""
        CREATE TABLE members (
            user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            household_id  uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
            role          text NOT NULL CHECK (role IN ('owner', 'viewer')),
            created_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, household_id)
        )
    """)
    op.execute("CREATE INDEX ix_members_household ON members (household_id)")

    op.execute("""
        CREATE TABLE signin_links (
            token_hash  text PRIMARY KEY,
            user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at  timestamptz NOT NULL,
            used_at     timestamptz,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_signin_links_user ON signin_links (user_id)")

    op.execute("""
        CREATE TABLE sessions (
            id_hash       text PRIMARY KEY,
            user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            -- Sent back in every form, so another site can't submit forms as this user.
            csrf_token    text NOT NULL,
            created_at    timestamptz NOT NULL DEFAULT now(),
            expires_at    timestamptz NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_sessions_user ON sessions (user_id)")


def downgrade() -> None:
    """Remove the web app's tables."""
    op.execute("DROP TABLE sessions")
    op.execute("DROP TABLE signin_links")
    op.execute("DROP TABLE members")
    op.execute("DROP TABLE users")
