"""Pydantic v2 schemas for QR token mint + list."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class QrTokenMintRequest(BaseModel):
    ttl_minutes: int = Field(default=60, ge=1, le=720)  # 1 min .. 12 hours
    single_use: bool = True
    # P1 fix (A04) — optional per-attendee QR binding. When supplied,
    # the minted token will ONLY verify for a check-in where the
    # claimed attendee matches. Admins can mint one bound token per
    # registered PNM as a lightweight anti-sharing defense. Omit to
    # preserve legacy event-scoped behavior (any registered attendee
    # who presents the token passes QR verification).
    attendee_user_id: Optional[str] = Field(default=None, max_length=36)


class QrTokenMintResponse(BaseModel):
    """Mint response — `raw_token` is returned EXACTLY ONCE here. The
    server only stores its sha256 hash. The admin caller is responsible
    for encoding it into a QR code and never persisting the raw form."""

    qr_token_id: int
    event_id: int
    event_table: Literal["events", "greek_rush_events"]
    raw_token: str
    expires_at: datetime
    single_use: bool


class QrTokenListItem(BaseModel):
    """List response — never includes the raw token, only metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    event_table: Literal["events", "greek_rush_events"]
    issued_at: datetime
    expires_at: datetime
    single_use: bool
    used_at: Optional[datetime] = None
