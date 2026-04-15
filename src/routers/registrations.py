"""Event registration (RSVP) router.

Tenant-scope contract (clarified 2026-04-11 in response to a reviewer
finding):

  * POST /api/checkin/events/{event_id}/register
      Open to ANY authenticated user. The handler does NOT enforce
      school-tenant scope on the event lookup — by design, since fans
      and PNMs (prospective new members at a sorority recruitment event)
      do not have a school binding on their JWT. Anyone can RSVP for any
      `published` or `active` event regardless of which school owns it.
      The only gates are:
        - bearer JWT validates
        - event.status IN ('published', 'active')
        - assert_self_or_admin (if attendee_user_id is supplied, it must
          equal the actor's user_id unless the actor is an admin)

  * GET /api/checkin/events/{event_id}/registrations
      Admin-only. STRICTLY school-scoped: cross-school reads return 404.

  * DELETE /api/checkin/events/{event_id}/registrations/{user_id}
      Self-or-admin. Same scope rules as POST register.

The check-in router (POST /api/checkin/events/{event_id}/checkin)
enforces an additional implicit scope guard: a fan cannot check in to an
event they did not register for. So while RSVP is open, the check-in
flow requires a pre-existing registration row that ties the attendee to
the event's school via the registration's school_id column.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import assert_self_or_admin, require_admin, require_bearer_actor
from ..database import get_db
from ..models import (
    Event,
    EventInvitation,
    EventRegistration,
    SchoolAdminGroupMember,
    TeamLeadRelationship,
)
from ..schemas.registration import (
    RegistrationCreateRequest,
    RegistrationListResponse,
    RegistrationResponse,
)
from ..services.hashing import hash_pii

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/checkin/events", tags=["registrations"])

_IDEM_RE = re.compile(r"^[A-Za-z0-9_\-:.]{8,128}$")
_ADMIN_ROLES = {
    "admin", "platform_admin", "platform_ops", "platform_system_admin",
    "platform_support_admin", "super_admin", "nilbx_admin", "service",
    "school_admin", "college_school_nil_admin", "hs_school_nil_admin",
    "compliance_officer",
}


def _is_admin(actor: Dict[str, Any]) -> bool:
    role = str(actor.get("canonical_role") or actor.get("role") or "").strip().lower()
    return role in _ADMIN_ROLES


def _validate_idem_key(key: Optional[str]) -> Optional[str]:
    if key is None or key == "":
        return None
    if not _IDEM_RE.match(key):
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key must match [A-Za-z0-9_\\-:.] (8-128 chars)",
        )
    return key


def _resolve_event_or_404(db: Session, event_id: int, school_id: Optional[str]) -> Event:
    """Look up the event. If `school_id` is set (admin caller), enforce
    cross-tenant scope; otherwise (PNM self-register) just check existence."""
    query = db.query(Event).filter(Event.id == event_id)
    if school_id:
        query = query.filter(Event.school_id == school_id)
    event = query.first()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post(
    "/{event_id}/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_for_event(
    event_id: int,
    payload: RegistrationCreateRequest,
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_bearer_actor),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> EventRegistration:
    """PNM (or admin on behalf of a PNM) registers for an event.

    - Open to any bearer-validated user.
    - If `attendee_user_id` is omitted, defaults to the bearer actor.
    - If supplied AND the actor is not admin, must match the actor's user_id.
    """
    _validate_idem_key(idempotency_key)

    target_user_id = payload.attendee_user_id or (actor.get("user_id") and str(actor["user_id"]))
    if not target_user_id:
        raise HTTPException(
            status_code=400,
            detail="attendee_user_id is required when bearer actor has no user_id (e.g. service token)",
        )
    assert_self_or_admin(actor, target_user_id)

    # Admins enforce cross-tenant scope; self-registering PNMs don't have
    # a school_id on their JWT and just need the event to exist.
    school_filter = actor.get("school_id") if _is_admin(actor) else None
    event = _resolve_event_or_404(db, event_id, school_filter)

    if event.status not in {"published", "active"}:
        raise HTTPException(
            status_code=409,
            detail={"code": "event_not_open", "status": event.status},
        )

    # Phase 10 visibility gates ──────────────────────────────────────
    actor_user_id = str(actor.get("user_id") or "") if actor.get("user_id") else None
    is_owner = (
        actor_user_id is not None
        and actor_user_id == str(event.owner_user_id)
    )
    actor_is_admin = _is_admin(actor)
    actor_school = actor.get("school_id")

    visibility = getattr(event, "visibility", "public") or "public"

    # school_only events: caller MUST be in the same school as the
    # event. We return 404 (not 403) so we never leak existence to
    # users in other schools.
    if visibility == "school_only" and not (is_owner or actor_is_admin):
        if not actor_school or str(actor_school) != str(event.school_id):
            raise HTTPException(status_code=404, detail="Event not found")

    # invite_only events: caller MUST have an accepted invitation OR
    # be the owner OR be an admin in the same school.
    if visibility == "invite_only" and not (is_owner or actor_is_admin):
        invitation = (
            db.query(EventInvitation)
            .filter(
                EventInvitation.event_id == event_id,
                EventInvitation.invitee_user_id == target_user_id,
                EventInvitation.status == "accepted",
            )
            .first()
        )
        if invitation is None:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "invitation_required",
                    "reason": "This event is invite-only; an accepted invitation is required to register.",
                },
            )

    # Phase 11 — group_only events: caller MUST be a member of the
    # bound group. Cross-group attempts return 404, never 403, so the
    # existence of other groups' events is never leaked.
    if visibility == "group_only" and not (is_owner or actor_is_admin):
        group_kind = getattr(event, "group_kind", None)
        group_id = getattr(event, "group_id", None)
        if group_kind == "school_admin_group":
            membership = (
                db.query(SchoolAdminGroupMember)
                .filter(
                    SchoolAdminGroupMember.group_id == group_id,
                    SchoolAdminGroupMember.user_id == target_user_id,
                    SchoolAdminGroupMember.status == "active",
                )
                .first()
            )
            if membership is None:
                raise HTTPException(status_code=404, detail="Event not found")
        elif group_kind == "team_lead_cohort":
            relationship = (
                db.query(TeamLeadRelationship)
                .filter(
                    TeamLeadRelationship.member_user_id == target_user_id,
                    TeamLeadRelationship.consent_status == "accepted",
                )
                .first()
            )
            if relationship is None:
                raise HTTPException(status_code=404, detail="Event not found")
        else:
            # Malformed group event — fail closed
            raise HTTPException(status_code=404, detail="Event not found")

    # Idempotency replay: same (event_id, idempotency_key) returns the
    # original row even if it was for a different attendee. The unique
    # key on (event_id, idempotency_key) enforces this.
    if idempotency_key:
        existing = (
            db.query(EventRegistration)
            .filter(
                EventRegistration.event_id == event_id,
                EventRegistration.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing:
            return existing

    # P0 fix (A04) — Atomic capacity check.
    #
    # Previously COUNT() → check vs max_capacity → INSERT was three separate
    # statements, so N concurrent requests could each read `count < capacity`
    # and all insert, over-registering. The fix:
    #
    #   1. Row-lock the `events` row with SELECT ... FOR UPDATE so only one
    #      request can own the capacity-check window at a time (MySQL-compat
    #      and already used in the rest of nilbx_db for similar races).
    #   2. Re-query the live active count INSIDE the lock.
    #   3. Insert + commit, releasing the lock.
    #
    # SQLite in the test harness is a no-op for with_for_update(); the
    # capacity check still runs correctly — the race is only reproducible
    # under a real MySQL pool.
    #
    # TODO: a dedicated concurrency harness test for this path requires a
    # thread pool and a real MySQL fixture — skipped for now, as the
    # existing pytest stack is SQLite in-memory with StaticPool (serialized
    # by design). Integration coverage should live in the e2e suite.
    waitlist_position: Optional[int] = None
    target_status = "registered"

    # Lock the event row before the capacity arithmetic + INSERT. If the
    # row disappears between the earlier _resolve_event_or_404 and the
    # lock acquisition, treat it as a 404 (event was deleted concurrently).
    locked_event = (
        db.query(Event)
        .filter(Event.id == event_id)
        .with_for_update()
        .first()
    )
    if locked_event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if locked_event.max_capacity is not None:
        active_count = (
            db.query(func.count(EventRegistration.id))
            .filter(
                EventRegistration.event_id == event_id,
                EventRegistration.status.in_(("registered", "attended")),
            )
            .scalar()
            or 0
        )
        if active_count >= locked_event.max_capacity:
            # Compute next waitlist position
            current_max = (
                db.query(func.max(EventRegistration.waitlist_position))
                .filter(
                    EventRegistration.event_id == event_id,
                    EventRegistration.status == "waitlisted",
                )
                .scalar()
            ) or 0
            waitlist_position = current_max + 1
            target_status = "waitlisted"

    # Use the event's school_id (not the actor's, since fans don't have one).
    registration = EventRegistration(
        school_id=locked_event.school_id,
        event_id=event_id,
        attendee_user_id=target_user_id,
        status=target_status,
        waitlist_position=waitlist_position,
        idempotency_key=idempotency_key,
    )
    db.add(registration)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Duplicate registration (event, attendee) — return the existing row.
        existing = (
            db.query(EventRegistration)
            .filter(
                EventRegistration.event_id == event_id,
                EventRegistration.attendee_user_id == target_user_id,
            )
            .first()
        )
        if existing:
            return existing
        raise HTTPException(status_code=409, detail={"code": "duplicate_registration"})
    db.refresh(registration)
    return registration


@router.get(
    "/{event_id}/registrations",
    response_model=List[RegistrationListResponse],
)
def list_registrations(
    event_id: int,
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_admin),
) -> List[Dict[str, Any]]:
    """Admin-only list. Returns hashed attendee IDs (never raw)."""
    school_id = actor.get("school_id")
    if not school_id:
        raise HTTPException(status_code=403, detail="school_id required")
    event = _resolve_event_or_404(db, event_id, str(school_id))

    rows = (
        db.query(EventRegistration)
        .filter(EventRegistration.event_id == event.id)
        .order_by(EventRegistration.registered_at.asc())
        .all()
    )
    return [
        {
            "id": r.id,
            "event_id": r.event_id,
            "hashed_attendee_id": hash_pii(r.attendee_user_id),
            "status": r.status,
            "waitlist_position": r.waitlist_position,
            "registered_at": r.registered_at,
        }
        for r in rows
    ]


@router.delete(
    "/{event_id}/registrations/{attendee_user_id}",
    status_code=status.HTTP_200_OK,
)
def cancel_registration(
    event_id: int,
    attendee_user_id: str,
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_bearer_actor),
) -> Dict[str, Any]:
    """Cancel a registration. Self-or-admin gate."""
    assert_self_or_admin(actor, attendee_user_id)

    school_filter = actor.get("school_id") if _is_admin(actor) else None
    event = _resolve_event_or_404(db, event_id, school_filter)

    registration = (
        db.query(EventRegistration)
        .filter(
            EventRegistration.event_id == event.id,
            EventRegistration.attendee_user_id == attendee_user_id,
        )
        .first()
    )
    if registration is None:
        raise HTTPException(status_code=404, detail="Registration not found")
    registration.status = "cancelled"
    db.commit()
    return {"ok": True, "id": registration.id, "status": "cancelled"}
