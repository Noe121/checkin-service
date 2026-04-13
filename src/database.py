"""
SQLAlchemy database connection + session management for checkin-service.

Mirrors crm-service/src/database.py. checkin-service connects to nilbx_db
(NOT a separate checkin_db — there is no such database). The generic
events / event_registrations / event_checkins / qr_tokens tables added
by V116 live alongside the Greek-specific tables added by V108 + V115.

The session is exposed via `get_db()` (FastAPI dependency) and the
declarative `Base` is shared by every ORM model in src/models/.
"""
from __future__ import annotations

import os
import ssl as _ssl
from typing import Any, Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool


def _build_database_url() -> str:
    """Construct the SQLAlchemy URL.

    Tests can override the entire URL via CHECKIN_TEST_DB_URL — used by
    the pytest fixture in tests/conftest.py to point at SQLite in-memory.
    """
    test_url = os.getenv("CHECKIN_TEST_DB_URL", "").strip()
    if test_url:
        return test_url

    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER") or os.getenv("DB_USERNAME") or "root"
    password = os.getenv("DB_PASSWORD", "")
    # checkin-service connects to nilbx_db (V116 added the generic tables
    # alongside the Greek tables from V108 + V115). There is no separate
    # checkin_db. Container-side override via DB_NAME is still respected.
    name = os.getenv("DB_NAME", "nilbx_db")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"


def _mysql_connect_args() -> dict[str, Any]:
    """SSL config for prod RDS, no-op for local docker / SQLite."""
    if "sqlite" in DATABASE_URL:
        return {}

    db_host = os.getenv("DB_HOST", "").strip().lower()
    env_name = os.getenv("ENVIRONMENT", "development").strip().lower()
    db_ssl_enabled_raw = os.getenv("DB_SSL_ENABLED")
    db_ssl_ca_path = os.getenv("DB_SSL_CA_PATH", "/etc/ssl/certs/global-bundle.pem").strip()

    if db_ssl_enabled_raw is not None:
        ssl_enabled = db_ssl_enabled_raw.strip().lower() in {"1", "true", "yes", "on"}
    else:
        is_local_host = db_host in {"", "localhost", "127.0.0.1", "mysql", "nilbx-mysql"}
        is_local_env = env_name in {"development", "local", "test"}
        ssl_enabled = not (is_local_host and is_local_env)

    if not ssl_enabled:
        return {}

    ssl_ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_CLIENT)
    if db_ssl_ca_path and os.path.isfile(db_ssl_ca_path):
        ssl_ctx.load_verify_locations(cafile=db_ssl_ca_path)
        ssl_ctx.check_hostname = True
        ssl_ctx.verify_mode = _ssl.CERT_REQUIRED
    else:
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = _ssl.CERT_NONE
    return {"ssl": ssl_ctx}


DATABASE_URL = _build_database_url()


def _build_engine_kwargs() -> dict[str, Any]:
    """Pool config: real pool for MySQL, no pool for SQLite (in-memory)."""
    if "sqlite" in DATABASE_URL:
        # SQLite in-memory needs a single shared connection so the test
        # client and the request handler see the same data.
        from sqlalchemy.pool import StaticPool
        return {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    return {
        "connect_args": _mysql_connect_args(),
        "poolclass": QueuePool,
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 3600,
    }


engine = create_engine(DATABASE_URL, **_build_engine_kwargs())
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Iterator[Session]:
    """FastAPI dependency for getting a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """Create all ORM-declared tables. Used in local dev / pytest only.

    In dev/staging/prod the tables are owned by the V001 Flyway migration;
    this is gated behind the CHECKIN_CREATE_ALL env var so it's a no-op
    when migrations are the source of truth.
    """
    Base.metadata.create_all(bind=engine)
