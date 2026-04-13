"""
Phase 10 — TDD coverage for the event_invitations router.

Written BEFORE the router exists. Expected to fail until:
  1. event_invitations table is added to the conftest schema
  2. EventInvitation ORM model lands
  3. routers/event_invitations.py implements the 4 routes:
     - POST /api/checkin/events/{id}/invitations          (organizer sends)
     - GET  /api/checkin/events/{id}/invitations          (organizer lists)
     - POST /api/checkin/events/{id}/invitations/{iid}/respond
                                                          (invitee accepts/declines)
     - GET  /api/checkin/me/invitations                   (invitee browses)
  4. The events POST gate flips from require_admin to require_event_creator
     so non-admin owners (creator/brand/coach) can author events first.

PII contract:
  - All response payloads include `hashed_invitee_id` (HMAC-SHA256[:16])
  - The raw `invitee_user_id` is ONLY echoed in admin-bypass responses
    OR when the invitee is reading their own row via /me/invitations
"""
from __future__ import annotations

import re
from typing import Dict, Any

import pytest

HEX16 = re.compile(r"^[0-9a-f]{16}$")


# ── Helpers ──────────────────────────────────────────────────────────


def _create_event(
    client_factory,
    actor: Dict[str, Any],
    *,
    title: str = "Phase 10 test event",
    visibility: str = "invite_only",
    allow_nfc_checkin: bool = False,
    max_capacity: int = 50,
) -> int:
    """Create an event as `actor` and return the event id. Used by every
    invitation test as setup."""
    client = client_factory(actor)
    resp = client.post(
        "/api/checkin/events/",
        json={
            "title": title,
            "event_type": "generic",
            "visibility": visibility,
            "allow_nfc_checkin": allow_nfc_checkin,
            "max_capacity": max_capacity,
            "status": "published",
        },
    )
    assert resp.status_code == 201, f"event create failed: {resp.text}"
    return resp.json()["id"]


# ── Sending invitations ──────────────────────────────────────────────


class TestSendInvitations:
    def test_owner_sends_batch_of_invitations(self, client_factory, admin_actor):
        event_id = _create_event(client_factory, admin_actor)
        client = client_factory(admin_actor)

        resp = client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={
                "invitees": [
                    {"invitee_user_id": "fan-uid-100", "reason": "VIP slot"},
                    {"invitee_user_id": "fan-uid-200"},
                    {"invitee_user_id": "fan-uid-300"},
                ],
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["sent"] == 3
        assert body["already_existed"] == 0
        # PII guard: response includes hashed ids only
        for row in body["invitations"]:
            assert HEX16.match(row["hashed_invitee_id"])
            assert "invitee_user_id" not in row

    def test_invitations_idempotent_on_event_invitee(
        self, client_factory, admin_actor
    ):
        event_id = _create_event(client_factory, admin_actor)
        client = client_factory(admin_actor)

        first = client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={"invitees": [{"invitee_user_id": "fan-uid-100"}]},
        )
        assert first.status_code == 201
        assert first.json()["sent"] == 1

        # Resend the same invitee — server returns already_existed=1
        second = client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={"invitees": [{"invitee_user_id": "fan-uid-100"}]},
        )
        assert second.status_code == 201
        body = second.json()
        assert body["sent"] == 0
        assert body["already_existed"] == 1

    def test_partial_duplicate_batch_preserves_new_inserts(
        self, client_factory, admin_actor
    ):
        """Phase 10 review-fix: happy-path partial-duplicate batch.

        A single batch containing [new, duplicate, new] must:
          - return sent=2, already_existed=1
          - actually persist BOTH new rows
          - NOT touch the pre-existing duplicate

        This exercises the SELECT-first happy path: the duplicate is
        caught by the per-row idempotency check before the SAVEPOINT
        even runs. The harder race-condition path (SELECT misses, INSERT
        trips UNIQUE) is exercised by
        test_savepoint_isolates_concurrent_collision below.
        """
        event_id = _create_event(client_factory, admin_actor)
        client = client_factory(admin_actor)

        # Pre-seed the duplicate so the second item in the batch trips
        # the SELECT-first idempotency check mid-batch.
        client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={"invitees": [{"invitee_user_id": "fan-existing-2"}]},
        )

        # Batch: new, duplicate, new
        resp = client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={
                "invitees": [
                    {"invitee_user_id": "fan-new-1"},
                    {"invitee_user_id": "fan-existing-2"},
                    {"invitee_user_id": "fan-new-3"},
                ]
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["sent"] == 2, f"counts wrong: {body}"
        assert body["already_existed"] == 1
        assert len(body["invitations"]) == 3

        # The contract is "the metadata matches what was actually
        # committed". Verify by listing — both new fans must be present
        # AND the existing fan must still be present (none rolled back).
        list_resp = client.get(
            f"/api/checkin/events/{event_id}/invitations"
        )
        assert list_resp.status_code == 200
        invitee_ids = {
            row["invitee_user_id"] for row in list_resp.json()["invitations"]
        }
        assert "fan-existing-2" in invitee_ids
        assert "fan-new-1" in invitee_ids, f"fan-new-1 missing — rollback wiped it: {invitee_ids}"
        assert "fan-new-3" in invitee_ids, f"fan-new-3 missing — rollback wiped it: {invitee_ids}"

    def test_savepoint_isolates_concurrent_collision(
        self, client_factory, admin_actor, db_session
    ):
        """Phase 10 review-fix: SAVEPOINT pattern smoke test.

        Simulates the race condition the rollback-in-loop bug actually
        depends on:

          1. The SELECT-first idempotency check returns None (we patch
             the EventInvitation lookup so the second item appears new
             even though it isn't).
          2. The INSERT then trips the (event_id, invitee_user_id)
             UNIQUE constraint mid-batch.
          3. WITHOUT the SAVEPOINT pattern, the resulting db.rollback()
             would wipe the previously-inserted rows from this request.
          4. WITH the SAVEPOINT pattern, db.begin_nested() rolls back
             ONLY the colliding row; previous rows in the same batch
             stay intact.

        We assert: BOTH new rows survive AND the response counts match
        what's actually committed.
        """
        from unittest.mock import patch
        from sqlalchemy.orm import Query as _Query

        event_id = _create_event(client_factory, admin_actor)
        client = client_factory(admin_actor)

        # Pre-seed the row that will collide on INSERT.
        client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={"invitees": [{"invitee_user_id": "race-target"}]},
        )

        # Now patch the per-row idempotency SELECT to return None for
        # the race-target row only — simulating a race where another
        # writer inserted between our SELECT and our INSERT.
        original_first = _Query.first
        seen_race_target = {"count": 0}

        def _flaky_first(self):
            # The router calls db.query(EventInvitation).filter(...).first()
            # twice per row: once for the idempotency check, once again
            # in the IntegrityError except branch. We simulate the race
            # ONLY for the idempotency check: return None the FIRST time
            # we see race-target, then fall through to real lookup
            # afterwards.
            sql = str(self.statement.compile(
                compile_kwargs={"literal_binds": True}
            ))
            if (
                "race-target" in sql
                and "event_invitations" in sql
                and seen_race_target["count"] == 0
            ):
                seen_race_target["count"] += 1
                return None
            return original_first(self)

        with patch.object(_Query, "first", _flaky_first):
            resp = client.post(
                f"/api/checkin/events/{event_id}/invitations",
                json={
                    "invitees": [
                        {"invitee_user_id": "savepoint-survivor-A"},
                        {"invitee_user_id": "race-target"},
                        {"invitee_user_id": "savepoint-survivor-B"},
                    ]
                },
            )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        # The race-target row was already pre-seeded → already_existed=1
        # Both savepoint-survivor rows must have been committed → sent=2
        assert body["sent"] == 2, f"sent wrong: {body}"
        assert body["already_existed"] == 1, f"already_existed wrong: {body}"

        # Read the DB and prove BOTH new rows survived the rollback.
        list_resp = client.get(
            f"/api/checkin/events/{event_id}/invitations"
        )
        assert list_resp.status_code == 200
        invitee_ids = {
            row["invitee_user_id"]
            for row in list_resp.json()["invitations"]
        }
        assert "race-target" in invitee_ids
        assert "savepoint-survivor-A" in invitee_ids, (
            f"SAVEPOINT failed — survivor A wiped by IntegrityError "
            f"rollback. Rows: {invitee_ids}"
        )
        assert "savepoint-survivor-B" in invitee_ids, (
            f"SAVEPOINT failed — survivor B wiped by IntegrityError "
            f"rollback. Rows: {invitee_ids}"
        )

    def test_creator_can_send_invitations_for_own_event(
        self, client_factory, creator_actor
    ):
        # Phase 10: event ownership flows to creators / brands too
        event_id = _create_event(client_factory, creator_actor)
        client = client_factory(creator_actor)

        resp = client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={"invitees": [{"invitee_user_id": "fan-uid-100"}]},
        )
        assert resp.status_code == 201, resp.text

    def test_non_owner_cannot_send_invitations(
        self, client_factory, creator_actor, brand_actor
    ):
        event_id = _create_event(client_factory, creator_actor)
        client = client_factory(brand_actor)

        resp = client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={"invitees": [{"invitee_user_id": "fan-uid-100"}]},
        )
        # Cross-tenant — brand has a different personal namespace
        # (user:brand-uid-400 vs user:creator-uid-300), so the event
        # lookup returns 404. NEVER 403 — we don't leak existence.
        assert resp.status_code == 404

    def test_admin_in_same_school_can_send_invitations_to_any_event(
        self, client_factory, admin_actor
    ):
        event_id = _create_event(client_factory, admin_actor)
        client = client_factory(admin_actor)

        resp = client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={"invitees": [{"invitee_user_id": "fan-uid-100"}]},
        )
        assert resp.status_code == 201

    def test_invitation_reason_is_sanitized(self, client_factory, admin_actor):
        event_id = _create_event(client_factory, admin_actor)
        client = client_factory(admin_actor)

        resp = client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={
                "invitees": [
                    {
                        "invitee_user_id": "fan-uid-100",
                        "reason": "Welcome <b>VIP</b> & friend",
                    },
                ],
            },
        )
        assert resp.status_code == 201
        # The sanitized form escapes < and &
        sanitized = resp.json()["invitations"][0]["reason_sn"]
        assert "<b>" not in sanitized
        assert "&lt;" in sanitized
        assert "&amp;" in sanitized

    def test_fan_cannot_send_invitations(self, client_factory, fan_actor):
        # Fans don't own events, period — 403 (the gate is on the
        # event ownership lookup, not the role check)
        client = client_factory(fan_actor)
        # The fan first tries to fetch a phantom event id
        resp = client.post(
            "/api/checkin/events/9999/invitations",
            json={"invitees": [{"invitee_user_id": "other-fan"}]},
        )
        # Either 403 (no event-creator role) or 404 (no event) — we
        # accept either, the contract is "fan cannot do this".
        assert resp.status_code in (403, 404)


# ── Listing invitations (organizer view) ─────────────────────────────


class TestListInvitations:
    def test_owner_lists_invitations_with_hashed_ids(
        self, client_factory, admin_actor
    ):
        event_id = _create_event(client_factory, admin_actor)
        client = client_factory(admin_actor)
        client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={
                "invitees": [
                    {"invitee_user_id": "fan-uid-100"},
                    {"invitee_user_id": "fan-uid-200"},
                ],
            },
        )

        resp = client.get(f"/api/checkin/events/{event_id}/invitations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        for row in body["invitations"]:
            assert HEX16.match(row["hashed_invitee_id"])
            # Admin list intentionally includes raw invitee for the
            # organizer's roster view; hashed form is also present.
            assert "invitee_user_id" in row

    def test_non_owner_cannot_list_invitations(
        self, client_factory, creator_actor, brand_actor
    ):
        event_id = _create_event(client_factory, creator_actor)
        client = client_factory(brand_actor)
        resp = client.get(f"/api/checkin/events/{event_id}/invitations")
        assert resp.status_code == 404


# ── Invitee response (accept / decline) ──────────────────────────────


class TestInviteeResponse:
    def test_invitee_accepts_invitation(self, client_factory, admin_actor, fan_actor):
        event_id = _create_event(client_factory, admin_actor)
        admin_client = client_factory(admin_actor)
        send_resp = admin_client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={"invitees": [{"invitee_user_id": fan_actor["user_id"]}]},
        )
        invitation_id = send_resp.json()["invitations"][0]["id"]

        fan_client = client_factory(fan_actor)
        resp = fan_client.post(
            f"/api/checkin/events/{event_id}/invitations/{invitation_id}/respond",
            json={"decision": "accepted"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["responded_at"] is not None

    def test_invitee_declines_invitation(
        self, client_factory, admin_actor, fan_actor
    ):
        event_id = _create_event(client_factory, admin_actor)
        admin_client = client_factory(admin_actor)
        send_resp = admin_client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={"invitees": [{"invitee_user_id": fan_actor["user_id"]}]},
        )
        invitation_id = send_resp.json()["invitations"][0]["id"]

        fan_client = client_factory(fan_actor)
        resp = fan_client.post(
            f"/api/checkin/events/{event_id}/invitations/{invitation_id}/respond",
            json={"decision": "declined"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "declined"

    def test_other_user_cannot_accept_invitation(
        self, client_factory, admin_actor, fan_actor, fan_actor_other
    ):
        event_id = _create_event(client_factory, admin_actor)
        admin_client = client_factory(admin_actor)
        send_resp = admin_client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={"invitees": [{"invitee_user_id": fan_actor["user_id"]}]},
        )
        invitation_id = send_resp.json()["invitations"][0]["id"]

        # Different fan tries to accept fan_actor's invite → 403
        other_client = client_factory(fan_actor_other)
        resp = other_client.post(
            f"/api/checkin/events/{event_id}/invitations/{invitation_id}/respond",
            json={"decision": "accepted"},
        )
        assert resp.status_code == 403

    def test_invalid_decision_400(self, client_factory, admin_actor, fan_actor):
        event_id = _create_event(client_factory, admin_actor)
        admin_client = client_factory(admin_actor)
        send_resp = admin_client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={"invitees": [{"invitee_user_id": fan_actor["user_id"]}]},
        )
        invitation_id = send_resp.json()["invitations"][0]["id"]

        fan_client = client_factory(fan_actor)
        resp = fan_client.post(
            f"/api/checkin/events/{event_id}/invitations/{invitation_id}/respond",
            json={"decision": "garbage"},
        )
        assert resp.status_code == 422


# ── /me/invitations (invitee browses their own) ──────────────────────


class TestMyInvitations:
    def test_invitee_lists_their_invitations(
        self, client_factory, admin_actor, fan_actor
    ):
        event_id = _create_event(client_factory, admin_actor)
        admin_client = client_factory(admin_actor)
        admin_client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={"invitees": [{"invitee_user_id": fan_actor["user_id"]}]},
        )

        fan_client = client_factory(fan_actor)
        resp = fan_client.get("/api/checkin/me/invitations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        row = body["invitations"][0]
        assert row["event_id"] == event_id
        assert row["status"] == "sent"

    def test_me_invitations_only_returns_caller_rows(
        self, client_factory, admin_actor, fan_actor, fan_actor_other
    ):
        event_id = _create_event(client_factory, admin_actor)
        admin_client = client_factory(admin_actor)
        # Invite both fans
        admin_client.post(
            f"/api/checkin/events/{event_id}/invitations",
            json={
                "invitees": [
                    {"invitee_user_id": fan_actor["user_id"]},
                    {"invitee_user_id": fan_actor_other["user_id"]},
                ]
            },
        )

        # fan_actor sees ONLY their own invitation
        fan_client = client_factory(fan_actor)
        resp = fan_client.get("/api/checkin/me/invitations")
        assert resp.status_code == 200
        invs = resp.json()["invitations"]
        assert len(invs) == 1
