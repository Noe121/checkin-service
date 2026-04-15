"""Pydantic v2 schemas for check-in submissions."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

CheckinMethodAudit = Literal["manual", "qr", "geo", "qr_geo", "nfc"]


class DeviceAttestation(BaseModel):
    """Optional mobile attestation payload.

    P1 fix (A02/A04) — see src/services/geo_verification.py for the
    full design. `platform` is the client OS family; `token` is the
    raw DeviceCheck (iOS) or Play Integrity (Android) token. Real
    verification is a TODO stub; the field exists today so mobile
    clients can start sending it.
    """

    platform: Literal["ios", "android"]
    token: str = Field(min_length=1, max_length=4096)


class CheckinRequest(BaseModel):
    """Body for POST /api/checkin/events/{event_id}/checkin.

    `attendee_user_id` is OPTIONAL — defaults to the bearer actor when
    omitted (PNM checks themselves in). Admins can supply any user.

    `qr_token` is the raw HMAC-signed token presented at the door.
    Required for `qr` / `qr_geo` checkin_method, ignored for `manual`/`geo`.

    `lat` / `lon` are the attendee's submitted coordinates. Required for
    `geo` / `qr_geo` checkin_method, ignored for `manual`/`qr`. They are
    NEVER persisted at full precision — the handler rounds + hashes
    before writing to event_checkins.lat_hash / lon_hash.

    `checkin_method` (Phase 10): the attendee can DECLARE the channel
    they used (e.g. `nfc` for a phone-to-phone tap, even if the event's
    canonical checkin_method is `qr`). The server still validates the
    declared method against the event's allow_nfc_checkin opt-in.
    Omitted = use the event's default method.
    """

    attendee_user_id: Optional[str] = Field(default=None, max_length=36)
    qr_token: Optional[str] = Field(default=None, max_length=512)
    lat: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    lon: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    notes: Optional[str] = Field(default=None, max_length=500)
    checkin_method: Optional[CheckinMethodAudit] = None
    # P1 fix (A02/A04) — optional device attestation payload. Required
    # only when REQUIRE_DEVICE_ATTESTATION=true in the service env.
    device_attestation: Optional[DeviceAttestation] = None


class CheckinResponse(BaseModel):
    """Response from POST checkin. Status enum is the OUTCOME, NOT the
    HTTP status. The router still returns 200 for success and 400/404/409/422
    for the various failure shapes — the status field is the machine-
    readable reason."""

    model_config = ConfigDict(from_attributes=True)

    checkin_id: Optional[int] = None
    status: Literal[
        "success",
        "duplicate",
        "geofence_failed",
        "invalid_token",
        "event_not_active",
        "registration_required",
        # P1 fix (A02/A04) — multi-signal GPS spoofing defenses
        "velocity_implausible",
        "ip_country_mismatch",
        "attestation_missing",
        "attestation_not_implemented",
        "attestation_invalid",
        "attendee_mismatch",
    ]
    geofence_passed: Optional[bool] = None
    distance_m: Optional[float] = None
    checkin_at: Optional[datetime] = None
