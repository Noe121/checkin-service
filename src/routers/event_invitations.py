"""
Phase 10 — event invitations router.

Surfaces:
  POST   /api/checkin/events/{event_id}/invitations
  GET    /api/checkin/events/{event_id}/invitations
  POST   /api/checkin/events/{event_id}/invitations/{invitation_id}/respond
  GET    /api/checkin/me/invitations

Auth model:
  - SEND  + LIST: organizer-or-admin via assert_event_owner_or_admin
  - RESPOND: invitee only (assert actor.user_id == invitation.invitee_user_id)
  - /me/invitations: any bearer actor; returns only their own rows

PII contract:
  - The CREATE batch response uses InvitationCreateBatchRow which omits
    raw invitee_user_id. The hashed form is always present.
  - The LIST response uses InvitationOrganizerRow which DOES include
    raw invitee_user_id (the organizer needs to see their roster).
  - The /me response uses MyInvitationRow which omits raw invitee_user_id
    (the caller is the invitee, they already know who they are).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import (
    ADMIN_BYPASS_ROLES,
    assert_event_owner_or_admin,
    require_bearer_actor,
    resolve_event_tenant,
)
from ..database import get_db
from ..models import Event, EventInvitation
from ..schemas.event_invitation import (
    InvitationCreateBatchResponse,
    InvitationCreateBatchRow,
    InvitationListResponse,
    InvitationOrganizerRow,
    InvitationRespondRequest,
    InvitationRespondResponse,
    InvitationSendRequest,
    MyInvitationRow,
    MyInvitationsResponse,
)
from ..services.hashing import hash_pii, sanitize_text

logger = logging.getLogger(__name__)

# Two routers — one is event-scoped, one is /me scoped. Same tag for
# the OpenAPI grouping.
event_invitations_router = APIRouter(
    prefix="/api/checkin/events", tags=["invitations"]
)
me_invitations_router = APIRouter(
    prefix="/api/checkin/me", tags=["invitations"]
)


def _canonicalize_role(actor: Dict[str, Any]) -> str:
    return str(actor.get("canonical_role") or actor.get("role") or "").strip().lower()


def _resolve_event_for_owner(
    db: Session, event_id: int, actor: Dict[str, Any]
) -> Event:
    """Look up the event and 404 cross-tenant.

    A creator-owned event lives under tenant key `user:<creator_uid>`;
    a school-owned event lives under tenant key `<school_uuid>`. We
    walk both tenant keys (the actor's school AND their personal
    namespace) so admins reach school-owned events AND owners reach
    their own personal-namespace events.
    """
    role = _canonicalize_role(actor)
    candidate_tenants = []
    if actor.get("school_id"):
        candidate_tenants.append(str(actor["school_id"]))
    user_id = actor.get("user_id")
    if user_id:
        candidate_tenants.append(f"user:{user_id}")
    # Service token has no tenant binding — admins handle this via the
    # explicit owner check below; for now we 404 service tokens here.
    if not candidate_tenants:
        raise HTTPException(404, "Event not found")
    event = (
        db.query(Event)
        .filter(Event.id == event_id, Event.school_id.in_(candidate_tenants))
        .first()
    )
    if event is None:
        raise HTTPException(404, "Event not found")
    return event


# ── POST /events/{event_id}/invitations ─────────────────────────────


@event_invitations_router.post(
    "/{event_id}/invitations",
    response_model=InvitationCreateBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_invitations(
    event_id: int,
    payload: InvitationSendRequest,
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_bearer_actor),
) -> InvitationCreateBatchResponse:
    """Owner-or-admin batch-sends event invitations.

    Idempotent on (event_id, invitee_user_id) — re-inviting the same
    attendee returns the existing row instead of duplicating it. The
    response distinguishes `sent` (newly created) from `already_existed`
    (replay).
    """
    event = _resolve_event_for_owner(db, event_id, actor)
    assert_event_owner_or_admin(actor, event.owner_user_id, event.school_id)

    inviter_user_id = str(actor.get("user_id") or "service")
    hashed_inviter = hash_pii(inviter_user_id)

    sent = 0
    already_existed = 0
    rows: List[EventInvitation] = []

    # Phase 10 review-fix 2026-04-12 (rollback-in-loop SAVEPOINT pattern):
    # the previous implementation called `db.rollback()` from inside the
    # loop on IntegrityError, which wipes EVERY uncommitted row from the
    # current request — including all the previously-successful inserts
    # in the same batch. The reported counts (`sent` / `already_existed`)
    # would then drift away from what the DB actually held.
    #
    # Fix: wrap each per-row INSERT in `db.begin_nested()` (a SAVEPOINT).
    # An IntegrityError during the savepoint rolls back ONLY that row's
    # changes; the outer transaction (and every successful prior row in
    # this loop) stays intact. We then re-SELECT to convert the
    # collision into the `already_existed` accounting.
    #
    # Mirrors the canonical fix applied in:
    #   - admin-dashboard-service/src/routers/greek_life_advisor.py
    #     assign_pnms_to_group + submit_pnm_preferences
    #   - live-commerce-service register_contract_products
    for item in payload.invitees:
        invitee_id = str(item.invitee_user_id)
        # Idempotency check first to avoid stamping a NEW row when
        # there's already one — even if the existing one is in a
        # different status. (Happy-path duplicate detection.)
        existing = (
            db.query(EventInvitation)
            .filter(
                EventInvitation.event_id == event_id,
                EventInvitation.invitee_user_id == invitee_id,
            )
            .first()
        )
        if existing is not None:
            already_existed += 1
            rows.append(existing)
            continue

        invite = EventInvitation(
            school_id=event.school_id,
            event_id=event_id,
            inviter_user_id=inviter_user_id,
            hashed_inviter_id=hashed_inviter,
            invitee_user_id=invitee_id,
            hashed_invitee_id=hash_pii(invitee_id),
            status="sent",
            reason_sn=sanitize_text(item.reason, max_len=2000),
        )
        try:
            with db.begin_nested():
                # SAVEPOINT — exits cleanly on success; rolls back ONLY
                # this row's changes on IntegrityError. db.add() inside
                # the savepoint context ensures the INSERT is the
                # operation that gets undone, not the entire batch.
                db.add(invite)
                db.flush()
        except IntegrityError:
            # Concurrent writer beat us to this (event_id, invitee_user_id).
            # The savepoint already rolled back the bad row; the rest
            # of the batch is still alive. Re-SELECT to grab the row
            # the other writer created and account it as already_existed.
            existing = (
                db.query(EventInvitation)
                .filter(
                    EventInvitation.event_id == event_id,
                    EventInvitation.invitee_user_id == invitee_id,
                )
                .first()
            )
            if existing is not None:
                already_existed += 1
                rows.append(existing)
                continue
            raise
        sent += 1
        rows.append(invite)

    db.commit()
    for r in rows:
        db.refresh(r)

    logger.info(
        "checkin_invitations_sent event=%s by=%s sent=%s already=%s",
        event_id,
        hashed_inviter,
        sent,
        already_existed,
    )
    return InvitationCreateBatchResponse(
        sent=sent,
        already_existed=already_existed,
        invitations=[
            InvitationCreateBatchRow.model_validate(r) for r in rows
        ],
    )


# ── GET /events/{event_id}/invitations ──────────────────────────────


@event_invitations_router.get(
    "/{event_id}/invitations",
    response_model=InvitationListResponse,
)
def list_invitations(
    event_id: int,
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_bearer_actor),
) -> InvitationListResponse:
    event = _resolve_event_for_owner(db, event_id, actor)
    assert_event_owner_or_admin(actor, event.owner_user_id, event.school_id)

    rows = (
        db.query(EventInvitation)
        .filter(EventInvitation.event_id == event_id)
        .order_by(EventInvitation.created_at.asc())
        .all()
    )
    return InvitationListResponse(
        invitations=[InvitationOrganizerRow.model_validate(r) for r in rows],
        total=len(rows),
    )


# ── POST /events/{event_id}/invitations/{invitation_id}/respond ─────


@event_invitations_router.post(
    "/{event_id}/invitations/{invitation_id}/respond",
    response_model=InvitationRespondResponse,
)
def respond_to_invitation(
    event_id: int,
    invitation_id: int,
    payload: InvitationRespondRequest,
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_bearer_actor),
) -> InvitationRespondResponse:
    """Invitee accepts or declines their own invitation.

    The actor MUST equal the invitee_user_id on the row. Admins do
    NOT bypass this check — accepting on behalf of a user is the
    user's own decision, not the admin's.
    """
    invitation = (
        db.query(EventInvitation)
        .filter(
            EventInvitation.id == invitation_id,
            EventInvitation.event_id == event_id,
        )
        .first()
    )
    if invitation is None:
        raise HTTPException(404, "Invitation not found")

    actor_user_id = actor.get("user_id")
    if actor_user_id is None or str(actor_user_id) != str(invitation.invitee_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "permission_denied",
                "reason": "Only the invitee may respond to this invitation",
            },
        )

    invitation.status = payload.decision
    invitation.responded_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invitation)
    return InvitationRespondResponse.model_validate(invitation)


# ── GET /me/invitations ─────────────────────────────────────────────


@me_invitations_router.get(
    "/invitations",
    response_model=MyInvitationsResponse,
)
def list_my_invitations(
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_bearer_actor),
) -> MyInvitationsResponse:
    actor_user_id = actor.get("user_id")
    if not actor_user_id:
        raise HTTPException(
            status_code=400,
            detail="Bearer actor has no user_id; service tokens cannot list /me invitations",
        )
    rows = (
        db.query(EventInvitation)
        .filter(EventInvitation.invitee_user_id == str(actor_user_id))
        .order_by(EventInvitation.created_at.desc())
        .all()
    )
    return MyInvitationsResponse(
        invitations=[MyInvitationRow.model_validate(r) for r in rows],
        total=len(rows),
    )
