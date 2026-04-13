"""Event ORM model — generic event surface for check-ins."""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from ..database import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    school_id = Column(String(36), nullable=False, index=True)
    owner_user_id = Column(String(36), nullable=False, index=True)

    event_type = Column(
        Enum(
            "rush",
            "coach_clinic",
            "brand_activation",
            "agency_mixer",
            "generic",
            name="event_type_enum",
        ),
        nullable=False,
        default="generic",
    )

    title = Column(String(200), nullable=False)
    description_sn = Column(Text, nullable=True)

    location_name = Column(String(200), nullable=True)
    # Raw lat/lon are kept on the venue row only — never echoed to non-admin
    # callers and never stored on attendee check-in rows.
    latitude = Column(Numeric(10, 7), nullable=True)
    longitude = Column(Numeric(10, 7), nullable=True)
    geofence_radius_m = Column(Integer, nullable=True, default=100)

    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    max_capacity = Column(Integer, nullable=True)

    checkin_method = Column(
        Enum("manual", "qr", "geo", "qr_geo", "none", name="event_checkin_method_enum"),
        nullable=False,
        default="none",
    )
    status = Column(
        Enum(
            "draft",
            "published",
            "active",
            "completed",
            "cancelled",
            name="event_status_enum",
        ),
        nullable=False,
        default="draft",
    )

    # Phase 10 (V120): visibility tier for the event.
    #   public      — visible in /events/discover, anyone signed in can RSVP
    #   school_only — visible only to users in the same school as the
    #                 event. school_admin / college_school_nil_admin /
    #                 hs_school_nil_admin / coach roles can author these.
    #                 Pure non-school owners (creator/brand) cannot.
    #   unlisted    — not in discover, but anyone with the link can RSVP
    #   invite_only — must have an accepted event_invitations row to
    #                 register; owner is implicitly accepted
    visibility = Column(
        Enum(
            "public",
            "school_only",
            "unlisted",
            "invite_only",
            "group_only",
            name="event_visibility_enum",
        ),
        nullable=False,
        default="public",
    )

    # Phase 10 (V120): explicit per-event NFC opt-in. The phone-to-phone
    # tap surface is OFF by default. Setting this to True opens the
    # `nfc` checkin_method on POST /checkin for this event only.
    allow_nfc_checkin = Column(Boolean, nullable=False, default=False)

    # Phase 10 (V120): caller role recorded at create time for audit.
    organizer_role = Column(String(64), nullable=True)

    # Phase 11 (V121): group-scoped event metadata.
    #   group_kind == 'school_admin_group' → group_id is a row in
    #     nilbx_db.school_admin_groups (V061). Members live in
    #     school_admin_group_members. Used by college_coach /
    #     college_team_lead / hs_coach / hs_team_lead callers who run
    #     a school-attached roster.
    #   group_kind == 'team_lead_cohort' → group_id is the team_lead's
    #     own auth_db.users.id, and the cohort is the set of accepted
    #     team_lead_relationships rows for that team_lead. Used by
    #     free-agent (non-school) team_leads.
    # Both NULL = legacy non-group event (Phase 10 surface unchanged).
    group_id = Column(Integer, nullable=True)
    group_kind = Column(
        Enum(
            "school_admin_group",
            "team_lead_cohort",
            name="event_group_kind_enum",
        ),
        nullable=True,
    )

    # Per-school idempotency key for replay-safe POST /events.
    idempotency_key = Column(String(128), nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("school_id", "idempotency_key", name="uk_ev_school_idem"),
        Index("idx_ev_school_status", "school_id", "status", "start_time"),
        Index("idx_ev_type_status", "event_type", "status"),
        # Phase 10 (V120) — discover + ownership lookups
        Index("idx_ev_visibility_status", "visibility", "status", "start_time"),
        Index("idx_ev_owner", "owner_user_id", "status"),
        # Phase 11 (V121) — per-group event lookup
        Index("idx_ev_group_kind_id", "group_kind", "group_id", "status", "start_time"),
    )
