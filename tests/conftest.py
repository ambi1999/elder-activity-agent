"""Shared test fixtures, including a real Postgres database for database tests.

Database tests run only when TEST_DATABASE_URL is set (Docker locally, a service
container in CI). They are skipped otherwise, except in CI, where a missing
database is an error so tests can't silently stop running.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app import db, rate_limit

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def test_db_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        if os.getenv("CI"):
            pytest.fail("TEST_DATABASE_URL must be set in CI")
        pytest.skip("TEST_DATABASE_URL not set; start the test database with: docker compose up -d")
    # Tests drop and recreate tables. Never let them near the real database.
    if "neon.tech" in url:
        pytest.exit("Refusing to run tests against a Neon (production) database", returncode=1)
    return db.normalize_url(url)


@pytest.fixture(scope="session")
def alembic_cfg(test_db_url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.attributes["url"] = test_db_url
    return cfg


@pytest.fixture
def migrated_db(alembic_cfg, test_db_url, monkeypatch):
    """An empty test database with all migrations applied; the app is pointed at it."""
    command.upgrade(alembic_cfg, "head")
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    db.reset_engine()
    engine = db.get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE households, people, devices, ingested_batches, step_readings, minute_summary, device_events, "
                "alert_contacts, alert_settings, alerts, alert_deliveries, users, members, signin_links, sessions"
            )
        )
    yield engine
    db.reset_engine()


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Each test starts with no uploads or sign-in requests counted."""
    for limiter in (rate_limit.uploads, rate_limit.signin_by_email, rate_limit.signin_by_ip):
        limiter.reset()
    yield
    for limiter in (rate_limit.uploads, rate_limit.signin_by_email, rate_limit.signin_by_ip):
        limiter.reset()
