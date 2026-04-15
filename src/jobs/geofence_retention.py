"""Geofence hash retention housekeeping.

P1 fix (A09 / privacy) — even though `event_checkins.lat_hash` and
`.lon_hash` are hashed at ~100m precision and never stored as raw
coordinates, they are still a privacy-sensitive signal (they tell you
approximately where a user was at a given time). We cap the retention
window so the hashes get nulled out after a configurable number of
days. The check-in row itself (attendance record, timestamps, method)
is retained for audit and attendance reporting — only the location
hashes are scrubbed.

Usage:
    from sqlalchemy.orm import Session
    from src.jobs.geofence_retention import purge_old_geofence_hashes

    def run():
        db = SessionLocal()
        try:
            stats = purge_old_geofence_hashes(db)
            logger.info("geofence_retention stats=%s", stats)
        finally:
            db.close()

Environment:
    GEOFENCE_RETENTION_DAYS — default 90. Set to 0 to disable (job is a
    no-op; useful for paused environments).

TODO: wire this into the deployment-time scheduler. Options:
      - ECS scheduled task invoking `python -m src.jobs.geofence_retention`
      - celery-beat entry in the platform-wide workers
      - AWS EventBridge → Lambda → RDS (service-external)
    The function is deliberately scheduler-agnostic; pick one per env.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session

from ..models import EventCheckin

logger = logging.getLogger(__name__)


def _retention_days() -> int:
    raw = os.getenv("GEOFENCE_RETENTION_DAYS", "90").strip()
    try:
        value = int(raw)
    except ValueError:
        return 90
    return max(value, 0)


def purge_old_geofence_hashes(
    db: Session,
    max_age_days: int | None = None,
) -> Dict[str, Any]:
    """Null out `lat_hash` / `lon_hash` on check-ins older than
    `max_age_days` (default from GEOFENCE_RETENTION_DAYS env).

    Returns a small dict with {rows_scrubbed, cutoff, dry_run} for
    caller logging. Does NOT delete the check-in rows themselves —
    attendance history is retained for audit.
    """
    effective_days = max_age_days if max_age_days is not None else _retention_days()
    if effective_days <= 0:
        return {"rows_scrubbed": 0, "cutoff": None, "dry_run": False, "disabled": True}

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=effective_days)

    # Only touch rows that still have a hash — idempotent and cheap to
    # rerun. Bulk UPDATE avoids the per-row ORM overhead.
    q = (
        db.query(EventCheckin)
        .filter(
            EventCheckin.checkin_at < cutoff,
            (EventCheckin.lat_hash.isnot(None)) | (EventCheckin.lon_hash.isnot(None)),
        )
    )
    rows = q.update(
        {EventCheckin.lat_hash: None, EventCheckin.lon_hash: None},
        synchronize_session=False,
    )
    db.commit()
    return {
        "rows_scrubbed": int(rows or 0),
        "cutoff": cutoff.isoformat(),
        "dry_run": False,
        "disabled": False,
    }


if __name__ == "__main__":
    # Allow `python -m src.jobs.geofence_retention` for ad-hoc ops
    # invocation. In a scheduled task the caller should import the
    # function directly.
    from ..database import SessionLocal

    logging.basicConfig(level=logging.INFO)
    session = SessionLocal()
    try:
        result = purge_old_geofence_hashes(session)
        logger.info("geofence_retention_result %s", result)
    finally:
        session.close()
