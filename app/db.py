"""Database connection.

The engine is created on first use, so importing the app (for example in
tests that don't need a database) never opens a connection.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

_engine: Engine | None = None


def normalize_url(url: str) -> str:
    """Make a standard Postgres URL use the psycopg (v3) driver in SQLAlchemy.

    Neon and most providers give URLs starting with postgresql:// or postgres://.
    SQLAlchemy would pick the older psycopg2 driver for those, which isn't installed.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def database_url() -> str:
    return normalize_url(os.environ["DATABASE_URL"])


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            database_url(),
            pool_pre_ping=True,  # Neon closes idle connections when it sleeps; check before use
            pool_recycle=300,    # replace connections older than 5 minutes
            pool_size=3,
            max_overflow=2,
        )
    return _engine


def reset_engine() -> None:
    """Close all connections and forget the engine (used by tests)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
