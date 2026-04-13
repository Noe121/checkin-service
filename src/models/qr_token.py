"""QrToken ORM model — HMAC-signed nonces. Raw tokens NEVER stored.

Polymorphic event reference: (event_table, event_id) disambiguates
between the generic `events` table and `greek_rush_events` so the same
qr_tokens table serves both surfaces without ID-space collisions.
"""
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


class QrToken(Base):
    __tablename__ = "qr_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    school_id = Column(String(36), nullable=False)

    # Polymorphic discriminator: which table event_id refers to.
    event_table = Column(
        Enum("events", "greek_rush_events", name="qr_event_table_enum"),
        nullable=False,
        default="events",
    )
    event_id = Column(Integer, nullable=False)

    # sha256 of the issued QR token. Raw token returned exactly once at
    # mint time and never persisted.
    token_hash = Column(String(64), nullable=False)
    nonce = Column(String(32), nullable=False)

    issued_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)

    single_use = Column(Integer, nullable=False, default=1)
    used_at = Column(DateTime, nullable=True)
    used_by_user_id = Column(String(36), nullable=True)

    issued_by_user_id = Column(String(36), nullable=False)

    __table_args__ = (
        UniqueConstraint("token_hash", name="uk_qr_token_hash"),
        Index("idx_qr_event", "event_table", "event_id", "expires_at"),
        Index("idx_qr_school", "school_id", "issued_at"),
    )
