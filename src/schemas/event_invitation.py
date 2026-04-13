"""Pydantic v2 schemas for the event_invitations router (Phase 10)."""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

InvitationStatus = Literal["sent", "accepted", "declined", "revoked", "expired"]
InvitationDecision = Literal["accepted", "declined"]


class InvitationSendItem(BaseModel):
    invitee_user_id: str = Field(min_length=1, max_length=36)
    reason: Optional[str] = Field(default=None, max_length=2000)


class InvitationSendRequest(BaseModel):
    invitees: List[InvitationSendItem] = Field(min_length=1, max_length=500)


class InvitationOrganizerRow(BaseModel):
    """Organizer-side row — INCLUDES raw `invitee_user_id` so the
    organizer can render their roster. Hashed form is also included
    for any UI that wants the audit-trail-shaped id."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    invitee_user_id: str
    hashed_invitee_id: str
    status: InvitationStatus
    reason_sn: Optional[str] = None
    created_at: datetime
    responded_at: Optional[datetime] = None


class InvitationCreateBatchRow(BaseModel):
    """A single row in the POST /invitations batch response. PII guard:
    the raw `invitee_user_id` is intentionally OMITTED from this shape
    so the create response is safe to log / cache."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    hashed_invitee_id: str
    status: InvitationStatus
    reason_sn: Optional[str] = None
    created_at: datetime


class InvitationCreateBatchResponse(BaseModel):
    sent: int = Field(ge=0)
    already_existed: int = Field(ge=0)
    invitations: List[InvitationCreateBatchRow]


class InvitationListResponse(BaseModel):
    invitations: List[InvitationOrganizerRow]
    total: int


class InvitationRespondRequest(BaseModel):
    decision: InvitationDecision


class InvitationRespondResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    status: InvitationStatus
    responded_at: Optional[datetime] = None


class MyInvitationRow(BaseModel):
    """Invitee-side row from GET /me/invitations. The invitee already
    knows their own user id (it's the bearer caller) so we don't echo
    it; the hashed form is included for parity with organizer reads."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    hashed_invitee_id: str
    status: InvitationStatus
    reason_sn: Optional[str] = None
    created_at: datetime
    responded_at: Optional[datetime] = None


class MyInvitationsResponse(BaseModel):
    invitations: List[MyInvitationRow]
    total: int
