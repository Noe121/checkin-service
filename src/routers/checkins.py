"""Check-in submission router.

Dedup contract: there is no Idempotency-Key support on this endpoint.
A second POST for the same (event_id, attendee_user_id) returns
`status: duplicate` via the `uk_ec_event_attendee` UNIQUE constraint
on V116 event_checkins. The earlier draft of this router accepted an
Idempotency-Key header but never persisted or replayed it — that was
removed in the Phase 2.1 review fix. The unique-constraint dedup is
the canonical replay-safe pattern.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import assert_self_or_admin, require_bearer_actor
from ..database import get_db
from ..models import Event, EventCheckin, EventRegistration
from ..schemas.checkin import CheckinRequest, CheckinResponse
from ..services.geo_verification import (
    attestation_required,
    ip_country_check,
    velocity_check,
    verify_device_attestation,
)
from ..services.geofence_service import hash_coordinate, verify_distance
from ..services.hashing import sanitize_text, sha256_full
from ..services.qr_token_service import (
    QrTokenVerifyResult,
    consume_token,
    peek_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/checkin/events", tags=["checkins"])


# ── P1 fix (A04) — sliding-window rate limiter ──────────────────────
#
# Two independent windows guard the check-in endpoint:
#
#   (1) Per-(attendee, event) — 5 scans per 60s. Blocks a compromised or
#       shared session from rapidly hammering the check-in flow for a
#       single event (e.g. someone handing a phone around trying to
#       probe QR tokens).
#
#   (2) Per client IP — 60 scans per 60s. Door staff may scan many
#       attendees per minute; 60/min gives a legitimate operator
#       headroom while still choking botnets that proxy through a
#       single IP.
#
# The limiter is an in-memory deque per key. That is sufficient for a
# single-task-per-event check-in service (the common case) and fails
# open across task restarts — the tradeoff we pick over pulling in a
# redis dependency. A cluster-wide limiter belongs in a shared cache
# service and is out of scope here.
_RL_LOCK = threading.Lock()
_RL_ATTENDEE_EVENT: Dict[Tuple[str, int], Deque[float]] = {}
_RL_IP: Dict[str, Deque[float]] = {}

_RL_ATTENDEE_EVENT_WINDOW_S = 60.0
_RL_ATTENDEE_EVENT_MAX = 5

_RL_IP_WINDOW_S = 60.0
_RL_IP_MAX = 60


def _prune(dq: Deque[float], now: float, window: float) -> None:
    cutoff = now - window
    while dq and dq[0] < cutoff:
        dq.popleft()


def _rate_limit(
    *,
    attendee_user_id: str,
    event_id: int,
    client_ip: Optional[str],
) -> Optional[Tuple[str, int]]:
    """Returns (code, retry_after_seconds) when the caller is throttled,
    otherwise None. Caller should raise 429 with Retry-After when set."""
    now = time.monotonic()
    with _RL_LOCK:
        # (1) per-(attendee, event)
        key_ae = (str(attendee_user_id), int(event_id))
        dq_ae = _RL_ATTENDEE_EVENT.setdefault(key_ae, deque())
        _prune(dq_ae, now, _RL_ATTENDEE_EVENT_WINDOW_S)
        if len(dq_ae) >= _RL_ATTENDEE_EVENT_MAX:
            retry = int(_RL_ATTENDEE_EVENT_WINDOW_S - (now - dq_ae[0])) + 1
            return "rate_limited_attendee", max(retry, 1)

        # (2) per client IP
        if client_ip:
            dq_ip = _RL_IP.setdefault(client_ip, deque())
            _prune(dq_ip, now, _RL_IP_WINDOW_S)
            if len(dq_ip) >= _RL_IP_MAX:
                retry = int(_RL_IP_WINDOW_S - (now - dq_ip[0])) + 1
                return "rate_limited_ip", max(retry, 1)
            dq_ip.append(now)

        dq_ae.append(now)
    return None


def _reset_rate_limiter_state() -> None:
    """Test-only helper: wipe the module-level sliding-window state.

    The limiter stores per-key deques in process memory, so state
    persists across requests — which is the point in production but
    noisy in test suites that run many checkin POSTs against the
    same fixture actors. The pytest conftest calls this between
    tests to keep the fixture shape stable.
    """
    with _RL_LOCK:
        _RL_ATTENDEE_EVENT.clear()
        _RL_IP.clear()


def _client_ip(request: Request) -> Optional[str]:
    """Best-effort client IP extraction. Prefers the X-Forwarded-For
    leftmost entry (set by ALB / CloudFront) and falls back to the
    socket peer address."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    client = request.client
    return client.host if client else None


@router.post(
    "/{event_id}/checkin",
    response_model=CheckinResponse,
    status_code=status.HTTP_200_OK,
)
def submit_checkin(
    event_id: int,
    payload: CheckinRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_bearer_actor),
) -> CheckinResponse:
    """Submit a check-in.

    Flow:
      1. Resolve target attendee (default: bearer actor; admin can supply any)
      2. Look up the event (must exist + be active)
      3. Verify QR token (if event.checkin_method requires it)
      4. Verify geofence (if event.checkin_method requires it)
      5. Look up the attendee's registration row (must exist or auto-create
         for admin/walk-in scenarios — see registration_required note below)
      6. Insert event_checkins row with HASHED coordinates only
      7. Mark the registration as 'attended'
      8. Return CheckinResponse with the outcome
    """
    target_user_id = payload.attendee_user_id or (actor.get("user_id") and str(actor["user_id"]))
    if not target_user_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "attendee_user_id_required"},
        )
    assert_self_or_admin(actor, target_user_id)

    # P1 fix (A04) — rate limit the check-in endpoint. Two sliding
    # windows: per-(attendee, event) at 5/60s and per-IP at 60/60s.
    # Throttled responses return 429 + Retry-After.
    client_ip = _client_ip(request)
    throttle = _rate_limit(
        attendee_user_id=target_user_id,
        event_id=event_id,
        client_ip=client_ip,
    )
    if throttle is not None:
        code, retry_after = throttle
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": code},
            headers={"Retry-After": str(retry_after)},
        )

    # P1 fix (A02/A04) — device attestation gate. When
    # REQUIRE_DEVICE_ATTESTATION=true in the service env (and we are
    # NOT in a dev SKIP shortcut), a device_attestation payload must
    # be supplied and verify successfully.
    if attestation_required():
        att = payload.device_attestation
        if att is None:
            return CheckinResponse(status="attestation_missing")
        ok, reject = verify_device_attestation(att.platform, att.token)
        if not ok:
            code = (reject or {}).get("code", "attestation_invalid")
            if code == "attestation_not_implemented":
                return CheckinResponse(status="attestation_not_implemented")
            if code == "attestation_missing":
                return CheckinResponse(status="attestation_missing")
            return CheckinResponse(status="attestation_invalid")

    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if event.status not in {"published", "active"}:
        return CheckinResponse(status="event_not_active")

    # P1 fix (A02/A04) — IP → coarse-geo cross-check. No-ops if the
    # event row has no country column / the CDN did not set a viewer
    # country header.
    ip_ok, ip_reject = ip_country_check(
        event=event,
        headers={k: v for k, v in request.headers.items()},
    )
    if not ip_ok:
        logger.info(
            "checkin_ip_country_mismatch event=%s detail=%s",
            event_id,
            ip_reject,
        )
        return CheckinResponse(status="ip_country_mismatch")

    # P1 fix (A02/A04) — velocity sanity check. If the attendee
    # checked in at a different event venue within the last 2 hours
    # and the implied travel speed exceeds 500 mph, reject.
    vel_ok, vel_reject = velocity_check(
        db,
        attendee_user_id=target_user_id,
        event=event,
    )
    if not vel_ok:
        logger.info(
            "checkin_velocity_implausible event=%s detail=%s",
            event_id,
            vel_reject,
        )
        return CheckinResponse(status="velocity_implausible")

    # Phase 10: the attendee can declare a method on the request body
    # (e.g. "nfc" for a phone-to-phone tap). If declared, the server
    # validates it against the event's per-method opt-ins. If omitted,
    # we fall back to the event's canonical checkin_method.
    declared_method = payload.checkin_method
    method = declared_method or event.checkin_method
    if method == "none":
        raise HTTPException(
            status_code=409,
            detail={"code": "checkin_disabled", "checkin_method": method},
        )

    # NFC requires explicit per-event opt-in. The default is OFF.
    if method == "nfc" and not bool(getattr(event, "allow_nfc_checkin", False)):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "nfc_disabled",
                "reason": "This event does not have NFC tap check-in enabled.",
            },
        )

    needs_qr = method in {"qr", "qr_geo"}
    needs_geo = method in {"geo", "qr_geo"}

    # Two-phase QR verification: peek first (read-only), consume only after
    # the geofence + insert have succeeded. This prevents the "single-use
    # token burned by a failed geofence check" bug where an out-of-range
    # location would permanently invalidate the token even though no
    # check-in row was created.
    qr_token_hash: Optional[str] = None
    qr_row = None
    if needs_qr:
        if not payload.qr_token:
            return CheckinResponse(status="invalid_token")
        peek_result = peek_token(
            db,
            raw_token=payload.qr_token,
            event_id=event_id,
            event_table="events",
            attendee_user_id=target_user_id,
        )
        if not peek_result.ok:
            logger.info(
                "checkin_qr_peek_failed event=%s reason=%s",
                event_id,
                peek_result.status,
            )
            # P1 fix (A04) — surface attendee-binding mismatch with a
            # distinct status so anti-sharing signals can be tracked
            # separately from generic invalid tokens.
            if peek_result.status == QrTokenVerifyResult.ATTENDEE_MISMATCH:
                return CheckinResponse(status="attendee_mismatch")
            return CheckinResponse(status="invalid_token")
        qr_row = peek_result.qr_row
        qr_token_hash = sha256_full(payload.qr_token)

    geofence_passed_flag: Optional[int] = None
    distance_m: Optional[float] = None
    lat_h: Optional[str] = None
    lon_h: Optional[str] = None
    if needs_geo:
        result = verify_distance(
            submitted_lat=payload.lat,
            submitted_lon=payload.lon,
            event_lat=float(event.latitude) if event.latitude is not None else None,
            event_lon=float(event.longitude) if event.longitude is not None else None,
            radius_m=event.geofence_radius_m,
        )
        distance_m = result.distance_m
        geofence_passed_flag = 1 if result.passed else 0
        if not result.passed:
            return CheckinResponse(
                status="geofence_failed",
                geofence_passed=False,
                distance_m=result.distance_m,
            )
        # Hash the submitted coordinates (rounded to ~100m) for the audit row.
        lat_h = hash_coordinate(payload.lat)
        lon_h = hash_coordinate(payload.lon)

    # Phase 2.1 fix — require a pre-existing registration row before
    # check-in. This is the implicit tenant-scope guard for self-service
    # PNM check-ins: a fan can't check in to an event they didn't RSVP
    # for. For admin walk-in scenarios the admin is also covered by this
    # rule because POST /register is the canonical path; an admin who
    # wants to walk a PNM in must POST /register first (or call
    # /register and /checkin in sequence).
    #
    # Previously this was a "soft" lookup that auto-created attendance
    # for missing registrations, which combined with the fact that
    # POST /register doesn't enforce school scope meant a fan could
    # check in to any school's event without ever RSVP'ing.
    registration = (
        db.query(EventRegistration)
        .filter(
            EventRegistration.event_id == event_id,
            EventRegistration.attendee_user_id == target_user_id,
        )
        .first()
    )
    if registration is None:
        return CheckinResponse(status="registration_required")
    if registration.status == "cancelled":
        return CheckinResponse(status="registration_required")

    checkin = EventCheckin(
        school_id=event.school_id,
        event_id=event_id,
        attendee_user_id=target_user_id,
        checkin_method=method if method != "none" else "manual",
        qr_token_hash=qr_token_hash,
        lat_hash=lat_h,
        lon_hash=lon_h,
        geofence_passed=geofence_passed_flag,
        notes_sn=sanitize_text(payload.notes, max_len=500),
    )
    db.add(checkin)
    try:
        db.commit()
    except IntegrityError:
        # Duplicate (event_id, attendee_user_id) — already checked in.
        db.rollback()
        existing = (
            db.query(EventCheckin)
            .filter(
                EventCheckin.event_id == event_id,
                EventCheckin.attendee_user_id == target_user_id,
            )
            .first()
        )
        return CheckinResponse(
            status="duplicate",
            checkin_id=existing.id if existing else None,
            checkin_at=existing.checkin_at if existing else None,
        )
    db.refresh(checkin)

    # Mark the registration as 'attended' if one exists.
    if registration is not None and registration.status != "cancelled":
        registration.status = "attended"
        db.commit()

    # Phase 2.1 fix — consume the QR token NOW that the rest of the flow
    # has succeeded. Previously verify_token() consumed the token before
    # geofence verification, so a single-use token would be permanently
    # burned by an out-of-range location attempt.
    if qr_row is not None:
        consume_token(db, qr_row=qr_row, redeeming_user_id=target_user_id)

    return CheckinResponse(
        status="success",
        checkin_id=checkin.id,
        geofence_passed=bool(geofence_passed_flag) if geofence_passed_flag is not None else None,
        distance_m=distance_m,
        checkin_at=checkin.checkin_at,
    )
