"""Pydantic v2 schemas for event registration request/response."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

RegistrationStatus = Literal["registered", "waitlisted", "cancelled", "attended", "no_show"]


class RegistrationCreateRequest(BaseModel):
    """Body for POST /api/checkin/events/{event_id}/register.

    `attendee_user_id` is OPTIONAL. When omitted, the handler defaults to
    the bearer actor's user_id (PNM registers themselves). When supplied,
    the handler enforces `assert_self_or_admin` so a fan can only set it
    to their own ID; an admin can register anyone.
    """

    attendee_user_id: Optional[str] = Field(default=None, max_length=36)


class RegistrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: str
    event_id: int
    # Hashed in the response by the router for non-admin callers; raw for admin.
    # The router substitutes hashed_attendee_id when the actor is not admin.
    attendee_user_id: str
    status: RegistrationStatus
    waitlist_position: Optional[int] = None
    registered_at: datetime
    updated_at: datetime


class RegistrationListResponse(BaseModel):
    """Admin list response — `attendee_user_id` is replaced with a hashed
    16-char hex value for non-admin callers via `hashed_attendee_id`."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    hashed_attendee_id: str
    status: RegistrationStatus
    waitlist_position: Optional[int] = None
    registered_at: datetime
