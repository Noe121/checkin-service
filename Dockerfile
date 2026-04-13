# ---------- builder stage ----------
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY checkin-service/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- runtime stage ----------
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    curl \
 && rm -rf /var/lib/apt/lists/*

# Download Amazon RDS CA bundle for full SSL certificate verification
RUN curl -sS -o /etc/ssl/certs/global-bundle.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem

COPY --from=builder /install /usr/local

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser
WORKDIR /app

# Phase 4.1 fix (2026-04-11) — preserve the `src/` package directory so
# relative imports inside src/main.py work. The previous flat layout
# (`COPY checkin-service/src/ .`) put main.py at /app/main.py and broke
# `from .database import ...` with "attempted relative import with no
# known parent package". Mirroring crm-service's pattern.
COPY --chown=appuser:appuser checkin-service/src/ ./src/

USER appuser

ENV DB_SSL_CA_PATH=/etc/ssl/certs/global-bundle.pem \
    PYTHONPATH=/app

EXPOSE 8006

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8006/health || exit 1

# Run main.py as a package member (`src.main`) so the relative imports
# in src/main.py + src/routers/*.py + src/models/*.py resolve correctly.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8006"]
