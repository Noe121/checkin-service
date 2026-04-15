"""Multi-signal GPS / location verification for check-in submissions.

This module provides sanity-check helpers on top of the straight haversine
geofence check. The goal is to catch the most obvious GPS-spoofing cases
without requiring a mobile-side round-trip:

  A. velocity_check(): if the caller successfully checked in at a different
     event venue in the last 2 hours, the implied velocity between the two
     event venues must be physically plausible (< 500 mph). A jet from LAX
     to JFK tops out around 575 mph ground speed — 500 mph is a conservative
     sanity cap. We use event venues, not per-checkin coordinates, because
     the stored lat/lon are hashed (one-way) and not reversible; the venue
     locations are authoritative and good enough for a sanity guard.

  B. ip_country_check(): cross-check the CloudFront/ALB viewer-country
     header against an event.country field if present. If the header is
     absent, or the event row has no country metadata, the check no-ops
     (fail-open on missing signal). When both are present and disagree,
     the request is rejected.

  C. verify_device_attestation(): stub for DeviceCheck (iOS) /
     Play Integrity (Android). Real verification requires backend-side
     calls to Apple and Google; for now this returns a deterministic
     "not implemented" status. When REQUIRE_DEVICE_ATTESTATION=true in
     the service env AND we are not in dev, callers that don't supply
     a token are rejected upstream in the router.

Every reject path uses a distinct opaque code so the client / ops
dashboard can tell them apart:
  - velocity_implausible
  - ip_country_mismatch
  - attestation_not_implemented
  - attestation_invalid

Environment knobs:
  VELOCITY_MAX_MPH              — default 500
  VELOCITY_WINDOW_SECONDS       — default 7200 (2 hours)
  VELOCITY_CHECK_ENABLED        — default "true"
  IP_COUNTRY_CHECK_ENABLED      — default "true"
  REQUIRE_DEVICE_ATTESTATION    — default "false"
  SKIP_DEVICE_ATTESTATION       — default "false" (dev shortcut)
  ENVIRONMENT                   — "development" | "dev" skip the attestation hard-fail
"""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from ..models import Event, EventCheckin
from .geofence_service import haversine_distance_m

logger = logging.getLogger(__name__)


# ── knobs ────────────────────────────────────────────────────────────

def _env_bool(key: str, default: str = "false") -> bool:
    return os.getenv(key, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _is_dev() -> bool:
    env = os.getenv("ENVIRONMENT", "development").strip().lower()
    return env in {"development", "dev", "local", "test"}


# ── A. velocity check ────────────────────────────────────────────────

def velocity_check(
    db: Session,
    *,
    attendee_user_id: str,
    event: Event,
    now: Optional[datetime] = None,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Reject check-ins that imply a physically impossible travel speed.

    Looks up the most recent check-in for this attendee within the last
    VELOCITY_WINDOW_SECONDS. If that previous check-in was at a different
    event venue, compute the straight-line distance + elapsed seconds +
    implied speed. If > VELOCITY_MAX_MPH, reject.

    Returns (ok, reject_detail). `ok=False` means the caller must reject
    with reject_detail.
    """
    if not _env_bool("VELOCITY_CHECK_ENABLED", "true"):
        return True, None

    window_s = _env_int("VELOCITY_WINDOW_SECONDS", 7200)
    max_mph = _env_float("VELOCITY_MAX_MPH", 500.0)

    if event.latitude is None or event.longitude is None:
        # No venue coords on the current event → cannot compute velocity.
        return True, None

    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    since = now - timedelta(seconds=window_s)

    prior = (
        db.query(EventCheckin)
        .filter(
            EventCheckin.attendee_user_id == attendee_user_id,
            EventCheckin.event_id != event.id,
            EventCheckin.checkin_at >= since,
        )
        .order_by(EventCheckin.checkin_at.desc())
        .first()
    )
    if prior is None:
        return True, None

    prior_event = db.query(Event).filter(Event.id == prior.event_id).first()
    if prior_event is None or prior_event.latitude is None or prior_event.longitude is None:
        return True, None

    distance_m = haversine_distance_m(
        float(prior_event.latitude),
        float(prior_event.longitude),
        float(event.latitude),
        float(event.longitude),
    )

    elapsed = (now - prior.checkin_at).total_seconds()
    if elapsed <= 0:
        return True, None

    # Convert m/s → mph: 1 m/s = 2.2369362921 mph
    speed_mph = (distance_m / elapsed) * 2.2369362921

    if speed_mph > max_mph:
        return False, {
            "code": "velocity_implausible",
            "implied_mph": round(speed_mph, 1),
            "max_mph": max_mph,
        }
    return True, None


# ── B. IP → coarse-geo cross-check ───────────────────────────────────

def _extract_viewer_country(headers: Dict[str, str]) -> Optional[str]:
    """Read the CloudFront / App Engine viewer-country header.

    We prefer CloudFront-Viewer-Country (ISO 3166-1 alpha-2) since the
    ALB in front of checkin-service is CloudFront-backed in dev + prod.
    """
    for key in (
        "CloudFront-Viewer-Country",
        "cloudfront-viewer-country",
        "X-Appengine-Country",
        "x-appengine-country",
    ):
        value = headers.get(key)
        if value:
            return str(value).strip().upper()[:2] or None
    return None


def ip_country_check(
    *,
    event: Event,
    headers: Dict[str, str],
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Compare request IP country (from CDN header) to the event's country.

    Returns ok=True (no-op) if:
      - the feature flag is off
      - no CDN country header is present (we never have a GeoIP DB
        bundled in this service)
      - the Event model has no country column / attribute

    TODO: the Event model does NOT currently have a country column. The
    V116 migration for `events` only stores latitude/longitude; there is
    no ISO country code. Wiring this fully requires a new migration. For
    now we look for `event.country` and skip silently if absent. Add this
    column in a follow-up Alembic migration to activate the check.
    """
    if not _env_bool("IP_COUNTRY_CHECK_ENABLED", "true"):
        return True, None

    event_country = getattr(event, "country", None)
    if not event_country:
        return True, None

    viewer_country = _extract_viewer_country(headers)
    if not viewer_country:
        # No CDN header → cannot decide. Fail-open.
        return True, None

    if str(event_country).strip().upper()[:2] != viewer_country:
        return False, {
            "code": "ip_country_mismatch",
            "expected": str(event_country).strip().upper()[:2],
            "seen": viewer_country,
        }
    return True, None


# ── C. Device attestation stub ───────────────────────────────────────

def verify_device_attestation(
    platform: Optional[str],
    token: Optional[str],
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Verify a DeviceCheck (iOS) / Play Integrity (Android) attestation.

    Current state: STUB. Real verification requires:
      * iOS: POST to api.development.devicecheck.apple.com with a signed
        JWT (team_id + key_id + p8 private key) to validate the device
        token, then compare bits 0/1.
      * Android: a Google-signed JWS from the Play Integrity API, decoded
        and verified against Google's public keys, then matched against
        the expected package_name and cert_digest_sha256.

    Neither callout is implemented here. Until it is, this function
    fails closed with `attestation_not_implemented` — unless the service
    env has SKIP_DEVICE_ATTESTATION=true AND we are in dev, in which case
    it returns ok to let dev smoke tests proceed.

    TODO: implement real verification callouts. Until then, don't set
    REQUIRE_DEVICE_ATTESTATION=true in prod — you will break all check-ins.
    """
    if _is_dev() and _env_bool("SKIP_DEVICE_ATTESTATION", "false"):
        return True, None

    if not platform or not token:
        return False, {"code": "attestation_missing"}

    if platform not in ("ios", "android"):
        return False, {"code": "attestation_invalid_platform"}

    # Placeholder — real implementation lands later.
    return False, {"code": "attestation_not_implemented"}


def attestation_required() -> bool:
    """True if the router must require a device_attestation payload."""
    if not _env_bool("REQUIRE_DEVICE_ATTESTATION", "false"):
        return False
    if _is_dev() and _env_bool("SKIP_DEVICE_ATTESTATION", "false"):
        return False
    return True
