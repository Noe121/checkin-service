"""
Phase 11 — /api/checkin/me/eligible-groups picker.

Returns the groups the caller is allowed to author `group_only` events
for. Two ownership paths:

  1. school_admin_groups: rows the caller leads (team_lead_user_id ==
     caller) OR rows the caller created (created_by_user_id == caller)
     OR ALL rows in the caller's school if they're a school admin.

  2. team_lead_cohort: a single virtual cohort if the caller has at
     least one accepted team_lead_relationships row owned by them.

Used by the frontend / iOS / Android event-creation UI to populate
the "create for which group?" picker. Read-only — no writes.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import (
    ADMIN_BYPASS_ROLES,
    require_bearer_actor,
)
from ..database import get_db
from ..models import SchoolAdminGroup, TeamLeadRelationship

router = APIRouter(prefix="/api/checkin/me", tags=["eligible-groups"])


def _canonicalize_role(actor: Dict[str, Any]) -> str:
    return str(actor.get("canonical_role") or actor.get("role") or "").strip().lower()


@router.get("/eligible-groups")
def list_eligible_groups(
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_bearer_actor),
) -> Dict[str, Any]:
    """List the groups the caller can author group_only events for.

    Response shape:
        {
            "school_admin_groups": [
                {"group_id": int, "name": str, "sport": str | None,
                 "school_id": str, "member_count": int}
            ],
            "team_lead_cohort": {
                "cohort_id": int,             # caller's user_id (numeric)
                "member_count": int,
                "sport": str | None,
            } | None
        }

    school_admin_groups list is empty for free-agent creators / brands /
    fans. team_lead_cohort is null unless the caller has at least one
    accepted team_lead_relationships row keyed to them.
    """
    actor_uid_raw = actor.get("user_id")
    actor_uid = str(actor_uid_raw) if actor_uid_raw is not None else ""
    actor_school = actor.get("school_id")
    role = _canonicalize_role(actor)
    is_admin = role in ADMIN_BYPASS_ROLES

    school_groups: List[Dict[str, Any]] = []
    if actor_uid or is_admin:
        query = db.query(SchoolAdminGroup).filter(
            SchoolAdminGroup.is_active == 1,
        )
        if is_admin and actor_school:
            # School admins see ALL groups in their school.
            query = query.filter(SchoolAdminGroup.school_id == str(actor_school))
        else:
            # Coaches / team_leads see groups they lead OR created.
            query = query.filter(
                (SchoolAdminGroup.team_lead_user_id == actor_uid)
                | (SchoolAdminGroup.created_by_user_id == actor_uid)
            )
        rows = query.order_by(SchoolAdminGroup.name.asc()).all()
        from ..models import SchoolAdminGroupMember
        for g in rows:
            mc = (
                db.query(func.count(SchoolAdminGroupMember.id))
                .filter(
                    SchoolAdminGroupMember.group_id == g.id,
                    SchoolAdminGroupMember.status == "active",
                )
                .scalar()
                or 0
            )
            school_groups.append({
                "group_id": g.id,
                "name": g.name,
                "sport": g.sport,
                "school_id": g.school_id,
                "member_count": mc,
            })

    # team_lead cohort — single virtual group keyed to the caller's
    # own user_id. Returns null if the caller has no accepted rows.
    team_lead_cohort = None
    if actor_uid:
        accepted = (
            db.query(TeamLeadRelationship)
            .filter(
                TeamLeadRelationship.team_lead_user_id == actor_uid,
                TeamLeadRelationship.consent_status == "accepted",
            )
            .all()
        )
        if accepted:
            digits = "".join(c for c in actor_uid if c.isdigit())
            cohort_id = int(digits) if digits else 0
            sports = {r.sport for r in accepted if r.sport}
            team_lead_cohort = {
                "cohort_id": cohort_id,
                "member_count": len(accepted),
                "sport": next(iter(sports)) if len(sports) == 1 else None,
            }

    return {
        "school_admin_groups": school_groups,
        "team_lead_cohort": team_lead_cohort,
    }
