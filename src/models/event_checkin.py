"""EventCheckin ORM model — PII-hashed coordinates only, raw lat/lon never stored."""
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


class EventCheckin(Base):
    __tablename__ = "event_checkins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    school_id = Column(String(36), nullable=False)
    event_id = Column(Integer, nullable=False)
    attendee_user_id = Column(String(36), nullable=False)

    checkin_at = Column(DateTime, server_default=func.now(), nullable=False)
    checkin_method = Column(
        Enum(
            "manual", "qr", "geo", "qr_geo", "nfc",
            name="event_checkin_method_audit_enum",
        ),
        nullable=False,
    )

    # sha256 of the QR token presented at check-in. Raw token NEVER stored.
    qr_token_hash = Column(String(64), nullable=True)

    # hash_pii() of latitude / longitude rounded to ~100m precision.
    # Raw coordinates NEVER stored.
    lat_hash = Column(String(16), nullable=True)
    lon_hash = Column(String(16), nullable=True)

    geofence_passed = Column(Integer, nullable=True)  # 1 / 0 / NULL

    notes_sn = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("event_id", "attendee_user_id", name="uk_ec_event_attendee"),
        Index("idx_ec_school", "school_id", "checkin_at"),
        Index("idx_ec_event", "event_id", "checkin_at"),
    )
