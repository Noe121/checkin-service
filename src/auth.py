"""
Auth gate for checkin-service.

This module mirrors the canonical auth shape from crm-service/src/auth.py
and notification-service/src/auth.py, but with a different bypass set
appropriate for the check-in domain:

  ADMIN_BYPASS_ROLES (write/admin routes): platform admins + school
  admins. Brand and agency are NOT here — they are not the operators
  of the events surface; events are run by school admins, NIL admins,
  compliance officers, and (in the Greek case) the recruitment council.

  Authenticated routes (POST /register, POST /checkin) are open to any
  bearer-validated user via require_bearer_actor — fans (PNMs in the
  Greek workflow) need to register themselves and check themselves in.

Three-way auth:
  1. Internal X-Service-Token (matches INTERNAL_SERVICE_TOKEN env) — used
     by greek_life_advisor.py POST /api/greek-life/rush-events/{id}/checkin
     proxy and any future service-to-service caller. Reported as `service`.
  2. Bearer JWT validated by auth-service /validate-token.
  3. Missing → 401.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Set

import requests
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

AUTH_SERVICE_URL = os.getenv(
    "AUTH_SERVICE_URL",
    "http://auth-service.dev.local:9000",
).rstrip("/")

# Internal service-to-service token. When the caller sends
# `X-Service-Token: <this value>` AND the env var is non-empty, the user
# auth gate is bypassed and the actor is reported as `service`. Used by
# the greek_life_advisor.py proxy and any other internal caller.
_INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "").strip()

# P1 fix (A07) — service-token callers must identify themselves via
# `X-Service-Name`. The allowlist comes from SERVICE_TOKEN_ALLOWED_CALLERS
# (comma-separated), mirroring the pattern established in
# streaming-deliverable-service. An accepted service call is logged with
# the caller name for audit; an unnamed or unknown caller gets 403.
_SERVICE_TOKEN_ALLOWED_CALLERS: Set[str] = {
    name.strip().lower()
    for name in os.getenv("SERVICE_TOKEN_ALLOWED_CALLERS", "").split(",")
    if name.strip()
}

# Roles that get blanket admin access to check-in management routes
# (event create/list/update/delete, QR token mint, registration list).
# Mirrors the bypass set used by other school-side services.
ADMIN_BYPASS_ROLES: Set[str] = {
    "admin",
    "platform_admin",
    "platform_ops",
    "platform_system_admin",
    "platform_support_admin",
    "super_admin",
    "nilbx_admin",
    "service",  # internal service token caller
    # School-side roles run the events surface. Brand/agency are NOT here.
    "school_admin",
    "college_school_nil_admin",
    "hs_school_nil_admin",
    "compliance_officer",
}

# Phase 10 — roles allowed to AUTHOR events. Strictly excludes `fan` and
# `guardian` (and the legacy `parent_guardian`). Includes ADMIN_BYPASS_ROLES
# transitively, plus creator / brand / agency / coach / team_lead / lawyer
# / governing-body roles. The check is "anyone except a fan-class viewer".
# Mirrors the institutional_sponsorships UPGRADEABLE_ROLES intent but
# scoped to event ownership rather than role escalation.
EVENT_CREATOR_ROLES: Set[str] = ADMIN_BYPASS_ROLES | {
    # Creator-class authors
    "creator",
    "student_creator",
    # Commercial authors
    "brand",
    "agency",
    # Coaching staff (school-bound and free-agent)
    "coach",
    "college_coach",
    "hs_coach",
    "college_team_lead",
    "hs_team_lead",
    "team_lead",
    # Cross-scope professionals
    "lawyer",
    # Governing body chain
    "governing_body_admin",
    "conference_admin",
    "nfhs_admin",
    "state_association_admin",
    "district_admin",
    "college_governing_body",
    "college_conference",
    "hs_nfhs",
    "hs_state_association",
    "hs_state_district",
    # Greek life student leader (Phase 9)
    "chapter_president",
}

# Roles that hold a real school binding via auth_db.users.school_id.
# Used by `assert_school_only_eligible` — only these roles are allowed
# to create or own events with visibility='school_only'. The check is
# "is your authoring scope a school, not a personal namespace?"
SCHOOL_BOUND_ROLES: Set[str] = {
    "school_admin",
    "college_school_nil_admin",
    "hs_school_nil_admin",
    "compliance_officer",
    "coach",
    "college_coach",
    "hs_coach",
    "college_team_lead",
    "hs_team_lead",
    "team_lead",
    "chapter_president",
    "governing_body_admin",
    "conference_admin",
    "nfhs_admin",
    "state_association_admin",
    "district_admin",
    "college_governing_body",
    "college_conference",
    "hs_nfhs",
    "hs_state_association",
    "hs_state_district",
}

_bearer_scheme = HTTPBearer(auto_error=False)


def _canonicalize_role(role: Any) -> str:
    return str(role or "").strip().lower()


def _validate_bearer_via_auth_service(token: str) -> Dict[str, Any]:
    """Round-trip the bearer token through auth-service's /validate-token.

    Returns the actor dict on success. Raises 401 on invalid token, 503 if
    the auth-service is unreachable.
    """
    try:
        response = requests.post(
            f"{AUTH_SERVICE_URL}/validate-token",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        logger.error("checkin-service auth validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )

    payload = response.json()
    raw_user_id = payload.get("user_id") or payload.get("id")
    user_id: Optional[str] = None
    if raw_user_id is not None:
        # Store as string to match the VARCHAR(36) school_id / user_id
        # convention used in the rest of nilbx_db.
        user_id = str(raw_user_id)

    role = _canonicalize_role(payload.get("canonical_role") or payload.get("role"))
    return {
        "user_id": user_id,
        "role": role,
        "canonical_role": role,
        "school_id": payload.get("school_id"),
        "email": payload.get("email"),
        "permissions": payload.get("permissions") or [],
        "auth_mode": "bearer",
    }


def require_bearer_actor(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    x_service_token: Optional[str] = Header(default=None, alias="X-Service-Token"),
    x_service_name: Optional[str] = Header(default=None, alias="X-Service-Name"),
) -> Dict[str, Any]:
    """Resolve an actor from either:
      1. An internal X-Service-Token (matches INTERNAL_SERVICE_TOKEN env)
      2. A Bearer JWT validated by auth-service /validate-token

    Raises 401 if neither is present or valid.

    P1 fix (A07) — service-token callers must additionally send an
    `X-Service-Name` header that is present in the
    SERVICE_TOKEN_ALLOWED_CALLERS allowlist. The accepted service
    call is logged with the caller name. This mirrors the audit
    pattern used in streaming-deliverable-service.
    """
    if _INTERNAL_SERVICE_TOKEN and x_service_token and x_service_token == _INTERNAL_SERVICE_TOKEN:
        service_name = (x_service_name or "").strip().lower()
        if not service_name:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "service_name_required",
                    "reason": "Service-token callers must identify themselves via X-Service-Name",
                },
            )
        # If the allowlist is configured, enforce it. If the env is
        # unset we log-only so dev environments without a configured
        # allowlist keep working — prod deploys must set the env.
        if _SERVICE_TOKEN_ALLOWED_CALLERS and service_name not in _SERVICE_TOKEN_ALLOWED_CALLERS:
            logger.warning(
                "service_call_rejected caller=%s path=%s",
                service_name,
                request.url.path,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "service_caller_not_allowlisted",
                    "caller": service_name,
                },
            )
        logger.info(
            "service_call_accepted caller=%s method=%s path=%s",
            service_name,
            request.method,
            request.url.path,
        )
        return {
            "user_id": None,
            "role": "service",
            "canonical_role": "service",
            "school_id": None,
            "email": None,
            "permissions": [],
            "auth_mode": "service_token",
            "service_name": service_name,
        }

    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
        )
    return _validate_bearer_via_auth_service(creds.credentials)


def require_admin(
    actor: Dict[str, Any] = Depends(require_bearer_actor),
) -> Dict[str, Any]:
    """Require admin / school_admin / compliance_officer / service role.

    Used for routes that manage events, mint QR tokens, list registrations,
    or otherwise act on behalf of the entire school. Regular bearer-only
    routes (POST /register, POST /checkin) use require_bearer_actor and
    enforce ownership inside the handler.
    """
    role = _canonicalize_role(actor.get("canonical_role") or actor.get("role"))
    if role not in ADMIN_BYPASS_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "permission_denied",
                "required": "admin/school_admin/compliance_officer",
                "actor_role": role,
            },
        )
    return actor


def assert_self_or_admin(actor: Dict[str, Any], target_user_id: str) -> None:
    """Helper called from inside handlers (POST /register, POST /checkin)
    that have already resolved the bearer actor.

    Raises 403 if the actor is neither the target user nor an admin/bypass
    role. Used for the "PNM checks themselves in, but admin can also check
    them in" flow.
    """
    role = _canonicalize_role(actor.get("canonical_role") or actor.get("role"))
    if role in ADMIN_BYPASS_ROLES:
        return
    actor_user_id = actor.get("user_id")
    if actor_user_id is not None and str(actor_user_id) == str(target_user_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "permission_denied",
            "reason": "user_id mismatch — caller can only act on their own registration / check-in",
        },
    )


# ── Phase 10 helpers ─────────────────────────────────────────────────


def require_event_creator(
    actor: Dict[str, Any] = Depends(require_bearer_actor),
) -> Dict[str, Any]:
    """Gate `POST /events` to non-fan event organizers.

    Replaces the legacy `require_admin` gate on event create. Permits any
    role in EVENT_CREATOR_ROLES (creator / student_creator / brand /
    agency / coach / school_admin / governing_body_*, etc.) and 403s
    fan / guardian / parent_guardian.
    """
    role = _canonicalize_role(actor.get("canonical_role") or actor.get("role"))
    if role not in EVENT_CREATOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "permission_denied",
                "reason": "Event creation requires a non-fan role",
                "actor_role": role,
            },
        )
    return actor


def resolve_event_tenant(actor: Dict[str, Any]) -> str:
    """Return the multi-tenant scope key for an event-create caller.

    For school-bound roles (school_admin / coach / chapter_president
    etc.) the actor.school_id from their JWT is the tenant. For
    free-agent roles (creator / brand / agency) we synthesize a
    personal namespace `user:<user_id>` so each owner gets their own
    isolated bucket inside the same `events.school_id` column without
    leaking events across users.

    The pattern matches what greek_life_advisor does for "no school"
    callers — same VARCHAR(36) column, same uniqueness story.
    """
    sid = actor.get("school_id")
    if sid:
        return str(sid)
    user_id = actor.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "tenant_required",
                "reason": "Caller has neither a school_id nor a user_id; cannot resolve event tenant",
            },
        )
    return f"user:{user_id}"


def assert_school_only_eligible(actor: Dict[str, Any]) -> None:
    """Raise 403 if the caller is trying to author a school_only event
    but does not have a real school binding (or a role that's allowed
    to scope events to a school community).

    Pure `creator` / `brand` / `agency` callers have no school — they
    can't author school_only events because there's no school to scope
    to. Coaches, school admins, governing-body roles, etc. can.
    """
    role = _canonicalize_role(actor.get("canonical_role") or actor.get("role"))
    sid = actor.get("school_id")
    if not sid or role not in SCHOOL_BOUND_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "school_binding_required",
                "reason": (
                    "school_only events require both a school_id binding "
                    "and a school-bound role (coach, school_admin, "
                    "chapter_president, governing_body_*, etc.)"
                ),
            },
        )


def assert_group_event_eligible(
    actor: Dict[str, Any],
    group_kind: str,
    group_id: int,
    db,  # type: ignore[no-untyped-def]  -- avoid circular import on Session
) -> str:
    """Phase 11 — owner check for group-scoped event creation.

    Verifies the caller is allowed to author a `group_only` event for
    the given (group_kind, group_id) tuple. Returns the resolved
    `school_id` for the event row (the calling router stamps it).

    Rules:

      group_kind == 'school_admin_group':
        - Group must exist and be is_active=1
        - Caller must be ONE of:
          * the group's `team_lead_user_id`
          * the group's `created_by_user_id`
          * an admin in the SAME school as the group (school_admin /
            college_school_nil_admin / hs_school_nil_admin / etc.)
        - Returns the group's school_id

      group_kind == 'team_lead_cohort':
        - group_id MUST equal the caller's own user_id (numeric).
          Free-agent team_lead cohorts are owned exclusively by the
          team_lead themselves; admins do NOT bypass this check.
        - Returns the personal namespace `user:<id>` (free-agent
          team_leads have no school binding).

    Raises HTTPException with detail.code = 'not_group_owner' on a
    failure that should NOT leak existence (the router converts to
    404 in some cases).
    """
    from .models import SchoolAdminGroup  # local import — avoid cycle

    role = _canonicalize_role(actor.get("canonical_role") or actor.get("role"))
    actor_uid = str(actor.get("user_id") or "")

    if group_kind == "school_admin_group":
        group = (
            db.query(SchoolAdminGroup)
            .filter(
                SchoolAdminGroup.id == group_id,
                SchoolAdminGroup.is_active == 1,
            )
            .first()
        )
        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )

        # Owner / lead check
        is_lead = (
            actor_uid != ""
            and (
                actor_uid == str(group.team_lead_user_id or "")
                or actor_uid == str(group.created_by_user_id or "")
            )
        )
        is_same_school_admin = (
            role in ADMIN_BYPASS_ROLES
            and actor.get("school_id")
            and str(actor["school_id"]) == str(group.school_id)
        )
        if not (is_lead or is_same_school_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "not_group_owner",
                    "reason": "Only the group's team lead, the original creator, or a same-school admin can author group_only events for this group.",
                },
            )
        return str(group.school_id)

    if group_kind == "team_lead_cohort":
        # Cohort id MUST be the caller's own user_id (extract numeric
        # suffix to match the INT column shape). The cohort itself
        # lives in team_lead_relationships keyed by team_lead_user_id.
        digits = "".join(c for c in actor_uid if c.isdigit())
        if not digits or int(digits) != int(group_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "not_group_owner",
                    "reason": "team_lead cohort group_id must match the caller's own user_id.",
                },
            )
        # Free-agent team_lead has no school binding — use the personal
        # namespace, same as resolve_event_tenant for non-school owners.
        return f"user:{actor_uid}"

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "invalid_group_kind", "group_kind": group_kind},
    )


def assert_event_owner_or_admin(
    actor: Dict[str, Any],
    event_owner_user_id: str,
    event_school_id: str,
) -> None:
    """Allow PATCH/DELETE/invitation actions if EITHER:
      - actor is the event owner (actor.user_id == event.owner_user_id)
      - actor is an admin in the SAME school as the event

    Cross-tenant non-owner non-admin callers get 404 from the upstream
    SELECT (so they never even reach this assertion). This helper just
    enforces the in-tenant ownership check.
    """
    role = _canonicalize_role(actor.get("canonical_role") or actor.get("role"))
    actor_user_id = actor.get("user_id")
    if actor_user_id is not None and str(actor_user_id) == str(event_owner_user_id):
        return
    if role in ADMIN_BYPASS_ROLES:
        # Admin bypass still requires same tenant — a school_admin in
        # school A cannot reach into school B's events.
        actor_sid = actor.get("school_id")
        if actor_sid and str(actor_sid) == str(event_school_id):
            return
        # Service-token caller has no school binding but the upstream
        # SELECT already constrained to the right tenant.
        if role == "service":
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "not_event_owner",
            "reason": "Only the event owner or an admin in the same school can perform this action",
        },
    )
