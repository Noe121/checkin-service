"""Events CRUD router for checkin-service.

All routes require admin/school_admin/compliance_officer/service via
`require_admin`. Cross-tenant scope is enforced server-side: every query
filters by the actor's `school_id`. Cross-school reads return 404 (not
403) to avoid leaking existence — same pattern as institutional_sponsorships.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import (
    ADMIN_BYPASS_ROLES,
    SCHOOL_BOUND_ROLES,
    assert_event_owner_or_admin,
    assert_group_event_eligible,
    assert_school_only_eligible,
    require_admin,
    require_bearer_actor,
    require_event_creator,
    resolve_event_tenant,
)
from ..database import get_db
from ..models import Event, SchoolAdminGroup, SchoolAdminGroupMember, TeamLeadRelationship
from ..schemas.event import (
    EventAdminResponse,
    EventCreate,
    EventDiscoverResponse,
    EventResponse,
    EventUpdate,
)
from ..services.hashing import sanitize_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/checkin/events", tags=["events"])

_IDEM_RE = re.compile(r"^[A-Za-z0-9_\-:.]{8,128}$")


def _validate_idem_key(key: Optional[str]) -> Optional[str]:
    """Mirror of the idempotency-key regex used by institutional_sponsorships
    and shared/middleware/idempotency."""
    if key is None or key == "":
        return None
    if not _IDEM_RE.match(key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must match [A-Za-z0-9_\\-:.] (8-128 chars)",
        )
    return key


def _resolve_school_id(actor: Dict[str, Any]) -> str:
    """Pull the actor's school_id from the validated bearer payload.

    Mirrors `_resolve_caller_school` from institutional_sponsorships.py
    in spirit. Service-token callers must specify school_id explicitly
    on the request body — we cannot infer one for them. Bearer admins
    must have a school_id in their JWT.
    """
    sid = actor.get("school_id")
    if sid:
        return str(sid)
    # Platform-bypass admins (admin/super_admin/etc.) act on behalf of
    # an explicit school via X-Acting-School-Id header in a future
    # iteration. For now, refuse so we never accidentally write rows
    # under an unknown school.
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "school_id_required",
            "reason": "Bearer JWT must include school_id; platform-bypass callers must use the X-Acting-School-Id header (not yet supported).",
        },
    )


def _canonicalize_role(actor: Dict[str, Any]) -> str:
    return str(actor.get("canonical_role") or actor.get("role") or "").strip().lower()


@router.post(
    "/",
    response_model=EventAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_event(
    payload: EventCreate,
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_event_creator),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> Event:
    """Create an event.

    Phase 10: gate flipped from `require_admin` to `require_event_creator`
    so creator / brand / agency / coach / school_admin can all author
    events. Tenant scope is resolved via `resolve_event_tenant`:
      - school-bound roles use their school_id
      - free-agent roles (creator/brand/agency) use a personal namespace
        `user:<user_id>` so they get isolation without leaking events
        across creators.
    """
    school_id = resolve_event_tenant(actor)
    safe_idem = _validate_idem_key(idempotency_key)

    # school_only events require both a school binding AND a
    # school-bound role. Free-agent creators / brands cannot author them.
    if payload.visibility == "school_only":
        assert_school_only_eligible(actor)

    # Phase 11 — group_only events. The body MUST carry both group_id
    # and group_kind. The auth helper validates ownership and returns
    # the resolved tenant key (school_id for school_admin_group, or
    # `user:<id>` for team_lead_cohort) which we use as the row's
    # school_id so the existing scope filters keep working.
    if payload.visibility == "group_only":
        if payload.group_id is None or payload.group_kind is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "group_required",
                    "reason": "group_only events must carry both group_id and group_kind",
                },
            )
        school_id = assert_group_event_eligible(
            actor=actor,
            group_kind=payload.group_kind,
            group_id=payload.group_id,
            db=db,
        )

    # Phase 2.1 fix — idempotency replay. Same school replaying the same
    # Idempotency-Key returns the original event row instead of creating
    # a duplicate. The (school_id, idempotency_key) UNIQUE on V116 events
    # backs this lookup.
    if safe_idem:
        existing = (
            db.query(Event)
            .filter(
                Event.school_id == school_id,
                Event.idempotency_key == safe_idem,
            )
            .first()
        )
        if existing:
            return existing

    sanitized_title = sanitize_text(payload.title, max_len=200)
    if not sanitized_title:
        raise HTTPException(status_code=422, detail="title cannot be empty after sanitization")

    event = Event(
        school_id=school_id,
        owner_user_id=str(actor.get("user_id") or "service"),
        event_type=payload.event_type,
        title=sanitized_title,
        description_sn=sanitize_text(payload.description, max_len=5000),
        location_name=sanitize_text(payload.location_name, max_len=200),
        latitude=payload.latitude,
        longitude=payload.longitude,
        geofence_radius_m=payload.geofence_radius_m,
        start_time=payload.start_time,
        end_time=payload.end_time,
        max_capacity=payload.max_capacity,
        checkin_method=payload.checkin_method,
        status=payload.status,
        # Phase 10 fields
        visibility=payload.visibility,
        allow_nfc_checkin=bool(payload.allow_nfc_checkin),
        organizer_role=_canonicalize_role(actor),
        # Phase 11 — group ownership stamps
        group_id=payload.group_id if payload.visibility == "group_only" else None,
        group_kind=payload.group_kind if payload.visibility == "group_only" else None,
        idempotency_key=safe_idem,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent retry hit the (school_id, idempotency_key) UNIQUE
        # AFTER our SELECT but BEFORE our INSERT. Re-fetch and return.
        db.rollback()
        if safe_idem:
            existing = (
                db.query(Event)
                .filter(
                    Event.school_id == school_id,
                    Event.idempotency_key == safe_idem,
                )
                .first()
            )
            if existing:
                return existing
        raise
    db.refresh(event)
    return event


@router.get("/", response_model=List[EventResponse])
def list_events(
    event_type: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_admin),
) -> List[Event]:
    school_id = _resolve_school_id(actor)
    query = db.query(Event).filter(Event.school_id == school_id)
    if event_type:
        query = query.filter(Event.event_type == event_type)
    if status_filter:
        query = query.filter(Event.status == status_filter)
    return query.order_by(Event.start_time.desc().nullslast(), Event.id.desc()).offset(offset).limit(limit).all()


# ── Phase 10 — public discovery (registered BEFORE /{event_id} so the
# static "/discover" path wins over the int-parameterized route) ───


@router.get("/discover", tags=["discover"])
def discover_events(
    event_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_bearer_actor),
) -> Dict[str, Any]:
    """Public discovery feed.

    Returns:
      - All `public` events across every tenant
      - PLUS `school_only` events whose `school_id` matches the
        caller's school (if the caller has a school binding)

    Excludes:
      - `unlisted` events (link-only)
      - `invite_only` events (require accepted invitation)
      - cancelled / draft events

    PII guard: response is `EventDiscoverResponse` which OMITS
    latitude/longitude/owner_user_id from the payload.

    Pagination contract: `total` is the COUNT of all matching rows
    across the filter set, NOT the size of the current page. The page
    itself is `events`. Phase 10 review-fix 2026-04-12 — the previous
    implementation returned `len(rows)` which made page 2 of 50 still
    report total=50 even when 500 events matched.
    """
    actor_school = actor.get("school_id")
    actor_uid = str(actor.get("user_id") or "") if actor.get("user_id") else None

    base_filter = [Event.status.in_(("published", "active"))]

    # Phase 11 — discover NEVER returns group_only events. The caller
    # finds those via /api/checkin/me/group-events (Phase 11.B follow-up
    # if the UI needs a dedicated picker) or by direct deep link.
    # Visibility filter: public is always visible. school_only is
    # visible only when the caller is in the same school. unlisted /
    # invite_only / group_only NEVER appear in discover.
    if actor_school:
        base_filter.append(
            (Event.visibility == "public")
            | (
                (Event.visibility == "school_only")
                & (Event.school_id == str(actor_school))
            )
        )
    else:
        base_filter.append(Event.visibility == "public")

    if event_type:
        base_filter.append(Event.event_type == event_type)

    # True total: count all matching rows BEFORE applying limit/offset.
    # Uses func.count() against the same filter set so the count and
    # the page draw from a single source of truth.
    from sqlalchemy import func as _sa_func
    total = (
        db.query(_sa_func.count(Event.id))
        .filter(*base_filter)
        .scalar()
        or 0
    )

    rows = (
        db.query(Event)
        .filter(*base_filter)
        .order_by(Event.start_time.asc().nullslast(), Event.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "events": [
            EventDiscoverResponse.model_validate(r).model_dump() for r in rows
        ],
        "total": total,
        # Convenience pagination metadata
        "limit": limit,
        "offset": offset,
    }


@router.get("/{event_id}", response_model=EventAdminResponse)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_admin),
) -> Event:
    school_id = _resolve_school_id(actor)
    event = (
        db.query(Event)
        .filter(Event.id == event_id, Event.school_id == school_id)
        .first()
    )
    if event is None:
        # 404 not 403 — never leak existence to a different school admin.
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch("/{event_id}", response_model=EventAdminResponse)
def update_event(
    event_id: int,
    payload: EventUpdate,
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_bearer_actor),
) -> Event:
    """Update an event.

    Phase 10: gate flipped from `require_admin` to `require_bearer_actor`
    + `assert_event_owner_or_admin`. The event owner can patch their
    own event; same-school admins (school_admin / college_school_nil_admin
    / etc.) can patch any event in their school. Cross-tenant non-owner
    callers get a 404 from the upstream SELECT (existence-leak guard).
    """
    # Cross-tenant resolution: a non-school-bound actor (creator/brand)
    # is scoped to user:<user_id>; a school-bound actor is scoped to
    # their school_id. Either way the SELECT below filters to that
    # tenant, so cross-tenant attempts 404.
    actor_tenant = resolve_event_tenant(actor)
    role = _canonicalize_role(actor)
    if role in ADMIN_BYPASS_ROLES:
        # Admins act inside their own school only — re-anchor the
        # SELECT on actor.school_id (not user:<id>) so we don't accidentally
        # let a school_admin reach into a creator's personal namespace.
        actor_tenant = actor.get("school_id") or actor_tenant
    event = (
        db.query(Event)
        .filter(Event.id == event_id, Event.school_id == actor_tenant)
        .first()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    assert_event_owner_or_admin(actor, event.owner_user_id, event.school_id)

    update_data = payload.model_dump(exclude_unset=True)
    if "title" in update_data:
        sanitized = sanitize_text(update_data["title"], max_len=200)
        if not sanitized:
            raise HTTPException(status_code=422, detail="title cannot be empty after sanitization")
        update_data["title"] = sanitized
    if "description" in update_data:
        update_data["description_sn"] = sanitize_text(update_data.pop("description"), max_len=5000)
    if "location_name" in update_data:
        update_data["location_name"] = sanitize_text(update_data["location_name"], max_len=200)

    # end_time > start_time invariant — re-check after merge
    new_start = update_data.get("start_time", event.start_time)
    new_end = update_data.get("end_time", event.end_time)
    if new_start is not None and new_end is not None and new_end <= new_start:
        raise HTTPException(status_code=422, detail="end_time must be strictly after start_time")

    for key, value in update_data.items():
        setattr(event, key, value)
    db.commit()
    db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_200_OK)
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_bearer_actor),
) -> Dict[str, Any]:
    """Soft cancel — flip status to 'cancelled'. Hard delete is reserved
    for platform admin via the database directly.

    Phase 10: gate flipped to bearer + owner-or-admin check (same as PATCH).
    """
    actor_tenant = resolve_event_tenant(actor)
    role = _canonicalize_role(actor)
    if role in ADMIN_BYPASS_ROLES:
        actor_tenant = actor.get("school_id") or actor_tenant
    event = (
        db.query(Event)
        .filter(Event.id == event_id, Event.school_id == actor_tenant)
        .first()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    assert_event_owner_or_admin(actor, event.owner_user_id, event.school_id)
    event.status = "cancelled"
    db.commit()
    return {"ok": True, "id": event_id, "status": "cancelled"}
