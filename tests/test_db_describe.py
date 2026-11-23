"""Scripts describe the database without printing its host name."""

from sqlalchemy import create_engine

from app.db import describe


def test_neon_host_is_not_shown():
    engine = create_engine("postgresql+psycopg://u:XXX@ep-example-123.c-5.us-west-2.aws.neon.tech/neondb")
    assert describe(engine) == "Neon (neondb)"


def test_local_and_other_databases():
    assert describe(create_engine("postgresql+psycopg://u:XXX@localhost:5433/elder")) == "local (elder)"
    assert describe(create_engine("postgresql+psycopg://u:XXX@db.example.com/app")) == "remote (app)"
