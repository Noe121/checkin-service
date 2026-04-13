"""EventInvitation ORM model — Phase 10 invite-only event gate.

Each row represents an organizer-issued invitation for a single
attendee to a single event. The PII shape mirrors the rest of the
service:

  - `inviter_user_id` and `invitee_user_id` are stored as raw VARCHAR
    so the organizer can list their roster.
  - `hashed_inviter_id` / `hashed_invitee_id` are HMAC-SHA256[:16]
    pre-computed at insert time so any read path that needs PII-safe
    output can return them directly without re-hashing.
  - `reason_sn` is HTML-escaped + truncated to 2000 chars.

Idempotency: UNIQUE(event_id, invitee_user_id) — re-inviting the same
attendee returns the existing row instead of creating a duplicate.

Status transitions:
    sent     → accepted  (invitee tap on accept)
    sent     → declined  (invitee tap on decline)
    sent     → revoked   (organizer pulls the invite)
    sent     → expired   (background job — not implemented in V1)
    accepted → declined  (allowed — invitee changes their mind)
    declined → accepted  (allowed — invitee changes their mind back)
"""
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from ..database import Base


class EventInvitation(Base):
    __tablename__ = "event_invitations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    school_id = Column(String(36), nullable=False)
    event_id = Column(Integer, nullable=False)

    inviter_user_id = Column(String(36), nullable=False)
    hashed_inviter_id = Column(String(16), nullable=False)

    invitee_user_id = Column(String(36), nullable=False)
    hashed_invitee_id = Column(String(16), nullable=False)

    status = Column(
        Enum(
            "sent",
            "accepted",
            "declined",
            "revoked",
            "expired",
            name="event_invitation_status_enum",
        ),
        nullable=False,
        default="sent",
    )

    reason_sn = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    responded_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("event_id", "invitee_user_id", name="uk_ei_event_invitee"),
        Index("idx_ei_event_status", "event_id", "status"),
        Index("idx_ei_invitee_status", "invitee_user_id", "status"),
        Index("idx_ei_school_created", "school_id", "created_at"),
    )
