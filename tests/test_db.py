from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app import db, main

client = TestClient(main.app)

EXPECTED_TABLES = {
    "devices",
    "ingested_batches",
    "step_readings",
    "minute_summary",
    "households",
    "people",
    "device_events",
}


def table_names(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


# ---------- need a database ----------


def test_migrations_create_expected_tables(migrated_db):
    assert table_names(migrated_db) >= EXPECTED_TABLES


def test_migrations_can_be_undone_and_reapplied(alembic_cfg, migrated_db):
    command.downgrade(alembic_cfg, "base")
    assert not (EXPECTED_TABLES & table_names(migrated_db))
    command.upgrade(alembic_cfg, "head")
    assert table_names(migrated_db) >= EXPECTED_TABLES


def test_health_db_reports_schema_revision(migrated_db, monkeypatch):
    monkeypatch.delenv("APP_API_KEY", raising=False)
    response = client.get("/health/db")
    assert response.status_code == 200
    assert response.json() == {"database": "ok", "schema_revision": "0002"}


# ---------- no database needed ----------


def test_health_db_requires_key_when_set(monkeypatch):
    monkeypatch.setenv("APP_API_KEY", "secret")
    assert client.get("/health/db").status_code == 401


def test_health_does_not_touch_database(monkeypatch):
    def fail():
        raise AssertionError("/health must not use the database")

    monkeypatch.setattr(db, "get_engine", fail)
    assert client.get("/health").status_code == 200
