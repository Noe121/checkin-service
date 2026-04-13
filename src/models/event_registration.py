"""EventRegistration ORM model — RSVP/registration with waitlist support."""
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from ..database import Base


class EventRegistration(Base):
    __tablename__ = "event_registrations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    school_id = Column(String(36), nullable=False)
    event_id = Column(Integer, nullable=False)
    attendee_user_id = Column(String(36), nullable=False)

    status = Column(
        Enum(
            "registered",
            "waitlisted",
            "cancelled",
            "attended",
            "no_show",
            name="event_registration_status_enum",
        ),
        nullable=False,
        default="registered",
    )
    waitlist_position = Column(Integer, nullable=True)

    # Per-event idempotency: replaying the same key returns the original row.
    idempotency_key = Column(String(128), nullable=True)

    registered_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("event_id", "attendee_user_id", name="uk_er_event_attendee"),
        UniqueConstraint("event_id", "idempotency_key", name="uk_er_event_idem"),
        Index("idx_er_school", "school_id"),
        Index("idx_er_status", "event_id", "status"),
        Index("idx_er_waitlist", "event_id", "waitlist_position"),
    )
