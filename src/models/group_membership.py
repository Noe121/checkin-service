"""
Phase 11 — read-only mirror models for the group membership tables
that live in the admin-dashboard-service domain but share the same
nilbx_db database.

  - SchoolAdminGroup            ← V061__school_admin_go_live_and_groups
  - SchoolAdminGroupMember      ← V061
  - TeamLeadRelationship        ← V032__add_team_lead_relationships

checkin-service does NOT mutate these tables — it only reads them to
gate `group_only` events:

  * `assert_group_event_eligible` — owner check at create time:
    confirms the caller actually owns / leads the group they're
    stamping the event with.

  * Visibility-aware register / discover — confirms the caller is a
    member of the event's bound group_id when visibility=group_only.

The tables are defined as part of admin-dashboard-service migrations,
so this file does NOT participate in `Base.metadata.create_all()` for
production. The conftest fixture mirrors the columns in raw SQL so
the in-memory test DB has them.
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


class SchoolAdminGroup(Base):
    """V061 school_admin_groups — used by school-bound coach/team_lead."""

    __tablename__ = "school_admin_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    school_id = Column(String(36), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    sport = Column(String(64), nullable=True)
    team_lead_user_id = Column(String(36), nullable=True)
    created_by_user_id = Column(String(36), nullable=False)
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("school_id", "name", name="uk_sag_school_name"),
        Index("idx_sag_team_lead", "team_lead_user_id"),
    )


class SchoolAdminGroupMember(Base):
    """V061 school_admin_group_members — group roster membership."""

    __tablename__ = "school_admin_group_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, nullable=False, index=True)
    user_id = Column(String(36), nullable=True)
    invite_email = Column(String(320), nullable=True)
    status = Column(
        Enum(
            "pending",
            "active",
            "declined",
            "removed",
            name="sag_member_status_enum",
        ),
        nullable=False,
        default="pending",
    )
    invited_by_user_id = Column(String(36), nullable=False)
    invited_at = Column(DateTime, server_default=func.now(), nullable=False)
    responded_at = Column(DateTime, nullable=True)


class TeamLeadRelationship(Base):
    """V032 team_lead_relationships — free-agent (non-school) cohorts."""

    __tablename__ = "team_lead_relationships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_lead_user_id = Column(String(36), nullable=False, index=True)
    member_user_id = Column(String(36), nullable=True)
    invite_email = Column(String(320), nullable=True)
    member_type = Column(String(32), nullable=True)
    relationship_type = Column(String(32), nullable=True)
    sport = Column(String(64), nullable=True)
    consent_status = Column(
        Enum(
            "pending",
            "accepted",
            "declined",
            "revoked",
            name="tlr_consent_enum",
        ),
        nullable=False,
        default="pending",
    )
    invited_at = Column(DateTime, server_default=func.now(), nullable=False)
    responded_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
