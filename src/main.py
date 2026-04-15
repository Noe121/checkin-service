"""
Check-in Service - Main FastAPI Application
Handles event check-ins and attendance tracking.

Connects to nilbx_db (NOT a separate checkin_db). The generic events /
event_registrations / event_checkins / qr_tokens tables added by V116
live alongside the Greek-specific tables added by V108 + V115.
"""
import os
from datetime import datetime
import logging
import sys

from fastapi import FastAPI

from .database import get_db, engine  # noqa: F401 — engine import warms the connection
from .routers import checkins as checkins_router
from .routers import eligible_groups as eligible_groups_router
from .routers import events as events_router
from .routers import event_invitations as event_invitations_router
from .routers import qr_tokens as qr_tokens_router
from .routers import registrations as registrations_router

# Configure stdout logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format=LOG_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("checkin-service")
logger.info("Check-in service starting up")

# NIL Platform Middleware (optional — not available in Docker containers)
_HAS_SHARED_MIDDLEWARE = False
try:
    from shared.middleware import CorrelationMiddleware, IdempotencyMiddleware, InMemoryIdempotencyBackend
    _HAS_SHARED_MIDDLEWARE = True
except ImportError:
    try:
        from pathlib import Path
        _file_path = Path(__file__).resolve()
        _repo_root = str(_file_path.parents[min(2, len(_file_path.parents) - 1)])
        if _repo_root not in sys.path:
            sys.path.insert(0, _repo_root)
        from shared.middleware import CorrelationMiddleware, IdempotencyMiddleware, InMemoryIdempotencyBackend
        _HAS_SHARED_MIDDLEWARE = True
    except (ImportError, IndexError):
        CorrelationMiddleware = None
        IdempotencyMiddleware = None
        InMemoryIdempotencyBackend = None

# Database connection lives in src/database.py (SQLAlchemy engine + session).
# checkin-service connects to nilbx_db via the standard `dev-nilbx-db-credentials`
# secret — there is no separate checkin_db. The previous mysql.connector
# bootstrap was removed when the routers landed in Phase 2.

# ===== FastAPI Setup =====

# ---------------------------------------------------------------------------
# CSRF protection for cookie-authenticated mutating requests
# ---------------------------------------------------------------------------
import hmac as _hmac
import os as _csrf_os
from starlette.middleware.base import BaseHTTPMiddleware as _BaseHTTPMiddleware
from fastapi.responses import JSONResponse as _JSONResponse

_SESSION_COOKIE_NAME = _csrf_os.getenv("SESSION_COOKIE_NAME", "nilbx_session")
_CSRF_COOKIE_NAME = _csrf_os.getenv("CSRF_COOKIE_NAME", "nilbx_csrf")
_COOKIE_AUTH_ENABLED = _csrf_os.getenv("COOKIE_AUTH_ENABLED", "true").lower() == "true"
_CSRF_PROTECTION_ENABLED = _csrf_os.getenv("CSRF_PROTECTION_ENABLED", "true").lower() == "true"
_CSRF_EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class CSRFMiddleware(_BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not (_CSRF_PROTECTION_ENABLED and _COOKIE_AUTH_ENABLED):
            return await call_next(request)
        if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
            return await call_next(request)
        if request.url.path in _CSRF_EXEMPT_PATHS:
            return await call_next(request)
        if not request.cookies.get(_SESSION_COOKIE_NAME):
            return await call_next(request)
        csrf_cookie = request.cookies.get(_CSRF_COOKIE_NAME)
        csrf_header = request.headers.get("X-CSRF-Token")
        if not csrf_cookie or not csrf_header or not _hmac.compare_digest(csrf_cookie, csrf_header):
            return _JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})
        return await call_next(request)


app = FastAPI(
    title="Check-in Service",
    description="Handles event check-ins and attendance tracking",
    version="1.0.0"
)
app.add_middleware(CSRFMiddleware)  # CSRF: cookie-authenticated mutating requests

# NIL Platform Middleware (skip if shared module unavailable in Docker)
if _HAS_SHARED_MIDDLEWARE and CorrelationMiddleware is not None:
    app.add_middleware(CorrelationMiddleware)
    if (os.getenv("IDEMPOTENCY_MIDDLEWARE_ENABLED", "false").lower() == "true"
            and IdempotencyMiddleware is not None
            and InMemoryIdempotencyBackend is not None):
        app.add_middleware(IdempotencyMiddleware, backend=InMemoryIdempotencyBackend())

# Register routers
app.include_router(events_router.router)
app.include_router(registrations_router.router)
app.include_router(checkins_router.router)
app.include_router(qr_tokens_router.router)
# Phase 10 — event invitations + /me/invitations
app.include_router(event_invitations_router.event_invitations_router)
app.include_router(event_invitations_router.me_invitations_router)
# Phase 11 — eligible groups picker for the create-event UI
app.include_router(eligible_groups_router.router)


# ===== Health Check =====

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "checkin-service",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/db-health")
def database_health_check():
    """Database health check endpoint with connection test"""
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "service": "checkin-service",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception:
        # P1 fix (A09) — never echo the underlying DB error to the wire.
        # Full stack trace stays in service logs; client sees only an
        # opaque machine-readable code.
        logger.exception("db_health_check_failed")
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail={"code": "db_unhealthy"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
