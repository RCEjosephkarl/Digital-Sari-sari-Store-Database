"""PostgreSQL connectivity.

Two backends, chosen automatically:

* **DATABASE_URL set**  → connect to that PostgreSQL (Docker, local install,
  or a cloud DB). This is what dashboards and ML notebooks should also use.
* **DATABASE_URL empty** → spin up / reuse a zero-setup local PostgreSQL via
  ``pgserver`` under ``PGDATA_DIR``. Ideal on WSL with no Docker installed.

The same connection info is exposed both as a libpq URL (for psycopg / fast
COPY) and as a SQLAlchemy URL (for pandas ``read_sql`` in analytics & ML).
"""
from __future__ import annotations

import psycopg
from sqlalchemy import Engine, create_engine

from .config import Settings, settings as default_settings

_pg_server = None  # cached local pgserver instance


def _libpq_url(settings: Settings) -> str:
    """Return a libpq-style connection URL (postgresql://...)."""
    url = settings.database_url
    if url:
        return (
            url.replace("postgresql+psycopg://", "postgresql://")
            .replace("postgresql+psycopg2://", "postgresql://")
        )

    # Fallback: local, self-contained PostgreSQL via pgserver.
    global _pg_server
    if _pg_server is None:
        import pgserver  # imported lazily so it's an optional dependency

        settings.pgdata_dir.mkdir(parents=True, exist_ok=True)
        _pg_server = pgserver.get_server(str(settings.pgdata_dir))
    return _pg_server.get_uri()


def sqlalchemy_url(settings: Settings = default_settings) -> str:
    """Return a SQLAlchemy URL using the psycopg (v3) driver."""
    url = settings.database_url
    if url and "+psycopg" in url:
        return url
    return _libpq_url(settings).replace("postgresql://", "postgresql+psycopg://", 1)


def get_connection(settings: Settings = default_settings) -> psycopg.Connection:
    """Raw psycopg connection (used for fast COPY and DDL)."""
    return psycopg.connect(_libpq_url(settings))


def get_engine(settings: Settings = default_settings) -> Engine:
    """SQLAlchemy engine — convenient for ``pandas.read_sql`` in analytics/ML."""
    return create_engine(sqlalchemy_url(settings))


def run_script(conn: psycopg.Connection, sql: str) -> None:
    """Execute a multi-statement SQL script via libpq's simple-query protocol.

    psycopg's normal ``execute`` is single-statement; ``PQexec`` (exposed as
    ``pgconn.exec_``) runs a whole script (functions with ``$$`` bodies, etc.).
    """
    result = conn.pgconn.exec_(sql.encode("utf-8"))
    status = result.status
    # ExecStatusType: 1=EMPTY-ish, 2=COMMAND_OK, 3=TUPLES_OK
    if status not in (psycopg.pq.ExecStatus.COMMAND_OK, psycopg.pq.ExecStatus.TUPLES_OK):
        msg = result.error_message.decode("utf-8", "replace")
        raise RuntimeError(f"SQL script failed: {msg}")
