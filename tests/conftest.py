"""
Phase 2 conftest for checkin-service.

Replaces the mock-only conftest with a REAL SQLAlchemy + FastAPI TestClient
fixture stack:

  * `engine` / `db_session` — SQLite in-memory backed by StaticPool so the
    test client and the request handler share the same connection.
  * `client` — FastAPI TestClient with `get_db` and the auth dependencies
    overridden to return controllable actor dicts (admin / fan / service).
  * Three actor fixtures: `admin_actor`, `fan_actor`, `service_actor`.

The point: every test in the suite gets a clean DB, no docker MySQL
required, no auth-service round-trip required.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Iterator

# Point database.py at SQLite in-memory BEFORE any of our modules import it.
os.environ.setdefault("CHECKIN_TEST_DB_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Now we can safely import the app modules.
from src import main as main_module
from src.auth import require_bearer_actor
from src.database import Base, SessionLocal, engine, get_db


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> Iterator[None]:
    """Build the schema once per pytest session against the in-memory DB."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session() -> Iterator[Session]:
    """Per-test session with HARD isolation.

    The previous version of this fixture only called rollback() at teardown,
    which is a no-op against rows that the request handler has already
    committed. Tests that committed rows leaked into later tests, hiding
    ordering-dependent bugs. We now wipe every table BEFORE each test by
    issuing DELETE FROM in reverse FK order. SQLite in-memory makes this
    a sub-millisecond operation for the 4 tables in this service.
    """
    session = SessionLocal()
    try:
        # Wipe all rows from every ORM-declared table before the test runs.
        # `sorted_tables` returns tables in dependency order; reverse for delete.
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def admin_actor() -> Dict[str, Any]:
    return {
        "user_id": "admin-uid-1",
        "role": "school_admin",
        "canonical_role": "school_admin",
        "school_id": "school-uuid-A",
        "email": "admin@dev.nilbx.com",
        "permissions": [],
        "auth_mode": "bearer",
    }


@pytest.fixture()
def admin_actor_other_school() -> Dict[str, Any]:
    """Different school admin used for cross-tenant 404 tests."""
    return {
        "user_id": "admin-uid-2",
        "role": "school_admin",
        "canonical_role": "school_admin",
        "school_id": "school-uuid-B",
        "email": "admin2@dev.nilbx.com",
        "permissions": [],
        "auth_mode": "bearer",
    }


@pytest.fixture()
def fan_actor() -> Dict[str, Any]:
    return {
        "user_id": "fan-uid-100",
        "role": "fan",
        "canonical_role": "fan",
        "school_id": None,
        "email": "fan@dev.nilbx.com",
        "permissions": [],
        "auth_mode": "bearer",
    }


@pytest.fixture()
def fan_actor_other() -> Dict[str, Any]:
    return {
        "user_id": "fan-uid-200",
        "role": "fan",
        "canonical_role": "fan",
        "school_id": None,
        "email": "fan2@dev.nilbx.com",
        "permissions": [],
        "auth_mode": "bearer",
    }


# ── Phase 10 fixtures ───────────────────────────────────────────────
#
# These are the new "non-fan event organizer" personas added when the
# events POST gate flipped from require_admin to require_event_creator.
# Each actor models a different ownership flow:
#
#   creator_actor    — creator role, NO school binding. Personal events
#                       go under the f"user:{user_id}" tenant namespace.
#   brand_actor      — brand role, NO school binding. Same personal
#                       namespace.
#   coach_actor      — college_coach role WITH a school binding.
#                       Eligible for school_only events.
#   fan_in_school    — fan role WITH a school binding (some fans on dev
#                       have school_id set). Used to test the
#                       school_only register gate.
#   admin_actor (existing) — school_admin in school A; eligible for
#                       school_only events scoped to school A.

@pytest.fixture()
def creator_actor() -> Dict[str, Any]:
    return {
        "user_id": "creator-uid-300",
        "role": "creator",
        "canonical_role": "creator",
        "school_id": None,
        "email": "creator@dev.nilbx.com",
        "permissions": [],
        "auth_mode": "bearer",
    }


@pytest.fixture()
def brand_actor() -> Dict[str, Any]:
    return {
        "user_id": "brand-uid-400",
        "role": "brand",
        "canonical_role": "brand",
        "school_id": None,
        "email": "brand@dev.nilbx.com",
        "permissions": [],
        "auth_mode": "bearer",
    }


@pytest.fixture()
def coach_actor() -> Dict[str, Any]:
    return {
        "user_id": "coach-uid-500",
        "role": "college_coach",
        "canonical_role": "college_coach",
        "school_id": "school-uuid-A",
        "email": "coach@dev.nilbx.com",
        "permissions": [],
        "auth_mode": "bearer",
    }


@pytest.fixture()
def fan_in_school() -> Dict[str, Any]:
    """Fan persona with a school binding — used for school_only register
    gate tests where the fan is supposed to be allowed."""
    return {
        "user_id": "fan-school-uid-600",
        "role": "fan",
        "canonical_role": "fan",
        "school_id": "school-uuid-A",
        "email": "fanA@dev.nilbx.com",
        "permissions": [],
        "auth_mode": "bearer",
    }


@pytest.fixture()
def fan_in_school_b() -> Dict[str, Any]:
    """Fan in a different school — used to verify school_only events
    are NOT visible cross-school."""
    return {
        "user_id": "fan-school-uid-700",
        "role": "fan",
        "canonical_role": "fan",
        "school_id": "school-uuid-B",
        "email": "fanB@dev.nilbx.com",
        "permissions": [],
        "auth_mode": "bearer",
    }


@pytest.fixture()
def client_factory(db_session: Session):
    """Factory that returns a TestClient bound to a specific actor.

    Usage:
        admin_client = client_factory(admin_actor)
        admin_client.post("/api/checkin/events/", json=...)
    """

    def _make(actor: Dict[str, Any]) -> TestClient:
        app = main_module.app

        def _override_get_db() -> Iterator[Session]:
            yield db_session

        def _override_actor() -> Dict[str, Any]:
            return actor

        # Only override the bearer-resolver. require_admin still runs its
        # real role check against the overridden actor — so a fan_actor
        # will hit the actual 403 path, not bypass it.
        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[require_bearer_actor] = _override_actor
        return TestClient(app)

    yield _make
    main_module.app.dependency_overrides.clear()


@pytest.fixture()
def unauthed_client():
    """TestClient with NO dependency overrides — exercises the real auth gate.
    Used for the unauthenticated 401 assertions."""
    app = main_module.app
    yield TestClient(app)
    app.dependency_overrides.clear()
