"""
Check-in Service - Main FastAPI Application
Handles event check-ins and attendance tracking
"""
import os
from datetime import datetime
import requests
import logging
import sys
import mysql.connector

from fastapi import FastAPI, HTTPException, Header, Query, Depends, Body
from fastapi.responses import JSONResponse

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

# NIL Platform Middleware
try:
    from shared.middleware import CorrelationMiddleware, IdempotencyMiddleware, InMemoryIdempotencyBackend
except ImportError:
    from pathlib import Path
    _repo_root = str(Path(__file__).resolve().parents[2])
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)
    from shared.middleware import CorrelationMiddleware, IdempotencyMiddleware, InMemoryIdempotencyBackend

# Database configuration - Load from Secrets Manager
SECRET_NAME = os.getenv("DB_SECRET_NAME", "dev-checkin-db-credentials")

def _get_db_config():
    """Load database config from Secrets Manager."""
    try:
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
        from shared.secrets_manager import get_db_credentials
        creds = get_db_credentials(SECRET_NAME)
        logger.info("✓ Loaded checkin database credentials from AWS Secrets Manager")
        return {
            "host": creds['host'],
            "port": creds['port'],
            "user": creds['username'],
            "password": creds['password'],
            "database": creds['dbname']
        }
    except Exception as e:
        logger.warning(f"Could not load from Secrets Manager: {e}. Using environment variables.")
        return {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 3306)),
            "user": os.getenv("DB_USER", "root"),
            "password": os.getenv("DB_PASSWORD", "rootpassword"),
            "database": os.getenv("DB_NAME", "nilbx_db")
        }

DB_CONFIG = _get_db_config()

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

# NIL Platform Middleware
app.add_middleware(CorrelationMiddleware)
if os.getenv("IDEMPOTENCY_MIDDLEWARE_ENABLED", "false").lower() == "true":
    app.add_middleware(IdempotencyMiddleware, backend=InMemoryIdempotencyBackend())


def get_db():
    """Get database connection with proper cleanup"""
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        logger.info("Database connection established")
        yield conn
    except mysql.connector.Error as err:
        logger.error(f"Database connection failed: {err}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {err}")
    finally:
        if conn and conn.is_connected():
            conn.close()
            logger.info("Database connection closed")


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
def database_health_check(db=Depends(get_db)):
    """Database health check endpoint with connection test"""
    try:
        cursor = db.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        return {
            "status": "healthy",
            "service": "checkin-service",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Database unhealthy: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
