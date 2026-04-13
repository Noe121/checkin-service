"""Pydantic v2 schemas for event create/update/response."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

EventType = Literal["rush", "coach_clinic", "brand_activation", "agency_mixer", "generic"]
EventStatus = Literal["draft", "published", "active", "completed", "cancelled"]
CheckinMethod = Literal["manual", "qr", "geo", "qr_geo", "none"]
# Phase 10 + 11 — visibility tier
EventVisibility = Literal[
    "public", "school_only", "unlisted", "invite_only", "group_only"
]
# Phase 11 — group ownership discriminator
EventGroupKind = Literal["school_admin_group", "team_lead_cohort"]


class EventCreate(BaseModel):
    event_type: EventType = "generic"
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)

    location_name: Optional[str] = Field(default=None, max_length=200)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    geofence_radius_m: Optional[int] = Field(default=100, ge=10, le=5000)

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    max_capacity: Optional[int] = Field(default=None, ge=1, le=100_000)

    checkin_method: CheckinMethod = "none"
    status: EventStatus = "draft"

    # Phase 10 fields
    visibility: EventVisibility = "public"
    allow_nfc_checkin: bool = False

    # Phase 11 — group-scoped event linkage
    group_id: Optional[int] = Field(default=None)
    group_kind: Optional[EventGroupKind] = None

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, v: Optional[datetime], info) -> Optional[datetime]:
        start = info.data.get("start_time")
        if v is not None and start is not None and v <= start:
            raise ValueError("end_time must be strictly after start_time")
        return v

    @field_validator("longitude")
    @classmethod
    def lon_requires_lat(cls, v: Optional[float], info) -> Optional[float]:
        lat = info.data.get("latitude")
        if (v is None) != (lat is None):
            raise ValueError("latitude and longitude must be supplied together")
        return v


class EventUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    location_name: Optional[str] = Field(default=None, max_length=200)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    geofence_radius_m: Optional[int] = Field(default=None, ge=10, le=5000)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    max_capacity: Optional[int] = Field(default=None, ge=1, le=100_000)
    checkin_method: Optional[CheckinMethod] = None
    status: Optional[EventStatus] = None
    visibility: Optional[EventVisibility] = None
    allow_nfc_checkin: Optional[bool] = None


class EventResponse(BaseModel):
    """Public-facing event response.

    Lat/lon are intentionally OMITTED from this response — they are only
    surfaced via a separate admin-only `EventResponseWithVenue` for
    operations that need to render the venue on a map. Non-admin callers
    only see the `location_name` string.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: str
    owner_user_id: str
    event_type: EventType
    title: str
    description_sn: Optional[str] = None
    location_name: Optional[str] = None
    geofence_radius_m: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    max_capacity: Optional[int] = None
    checkin_method: CheckinMethod
    status: EventStatus
    visibility: EventVisibility = "public"
    allow_nfc_checkin: bool = False
    organizer_role: Optional[str] = None
    group_id: Optional[int] = None
    group_kind: Optional[EventGroupKind] = None
    created_at: datetime
    updated_at: datetime


class EventAdminResponse(EventResponse):
    """Admin-only response that includes venue lat/lon. Used by the
    QR-token mint flow + the admin tablet view that renders the venue
    on a map. Never returned to fan/PNM callers."""

    latitude: Optional[float] = None
    longitude: Optional[float] = None


class EventDiscoverResponse(BaseModel):
    """PII-stripped response for the public /events/discover feed.

    Intentionally OMITS:
      - latitude / longitude (raw venue coordinates)
      - owner_user_id (would let an unauthenticated viewer enumerate
        organizers)
      - school_id (we don't want to expose the tenant key to other
        tenants — they only need to see the event itself)

    The location_name string is fine to surface (it's already
    organizer-curated text).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: EventType
    title: str
    description_sn: Optional[str] = None
    location_name: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    max_capacity: Optional[int] = None
    visibility: EventVisibility
    status: EventStatus
