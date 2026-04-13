"""
Phase 10 — visibility + ownership + NFC TDD coverage.

Covers the user-asked enhancements:
  - Non-fan users can create events (creator, brand, coach, school_admin)
  - Fans cannot create events (403)
  - Visibility tiers: public / school_only / unlisted / invite_only
  - school_only events:
      * Only callable by users with a real school binding
      * Visible only to same-school users via discover
      * Cross-school register returns 404 (existence-leak guard)
  - invite_only events require an accepted invitation to register
  - Owner-or-admin gate on PATCH/DELETE event
  - allow_nfc_checkin opt-in column persists + gates the nfc method
  - new GET /api/checkin/events/discover surface

Written BEFORE the implementation. Expected to fail until the matching
code lands. Each test class maps to a single concern.
"""
from __future__ import annotations

from typing import Any, Dict


# ── Event create — who can author what ──────────────────────────────


class TestEventCreatorRoles:
    def test_creator_can_create_public_event(self, client_factory, creator_actor):
        client = client_factory(creator_actor)
        resp = client.post(
            "/api/checkin/events/",
            json={
                "title": "Brand workshop",
                "event_type": "generic",
                "visibility": "public",
                "status": "published",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["visibility"] == "public"
        assert body["owner_user_id"] == creator_actor["user_id"]
        # Creator has no school — server falls back to f"user:{user_id}"
        # so the multi-tenant scope still works
        assert body["school_id"] == f"user:{creator_actor['user_id']}"

    def test_brand_can_create_event_under_personal_namespace(
        self, client_factory, brand_actor
    ):
        client = client_factory(brand_actor)
        resp = client.post(
            "/api/checkin/events/",
            json={
                "title": "Brand activation",
                "event_type": "brand_activation",
                "visibility": "public",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["school_id"] == f"user:{brand_actor['user_id']}"

    def test_coach_can_create_event_with_school_binding(
        self, client_factory, coach_actor
    ):
        client = client_factory(coach_actor)
        resp = client.post(
            "/api/checkin/events/",
            json={
                "title": "Football skills clinic",
                "event_type": "coach_clinic",
                "visibility": "public",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["school_id"] == coach_actor["school_id"]

    def test_fan_cannot_create_event_403(self, client_factory, fan_actor):
        client = client_factory(fan_actor)
        resp = client.post(
            "/api/checkin/events/",
            json={"title": "Should be blocked", "event_type": "generic"},
        )
        assert resp.status_code == 403

    def test_organizer_role_recorded_on_create(
        self, client_factory, creator_actor
    ):
        client = client_factory(creator_actor)
        resp = client.post(
            "/api/checkin/events/",
            json={"title": "Audit trail check", "event_type": "generic"},
        )
        assert resp.status_code == 201
        # Server stamps the caller's role at create time for audit
        assert resp.json()["organizer_role"] == "creator"


# ── Owner-or-admin PATCH/DELETE gate ─────────────────────────────────


class TestOwnerOrAdminMutation:
    def test_owner_can_patch_own_event(self, client_factory, creator_actor):
        client = client_factory(creator_actor)
        create = client.post(
            "/api/checkin/events/",
            json={"title": "Original", "event_type": "generic"},
        )
        eid = create.json()["id"]
        patch = client.patch(
            f"/api/checkin/events/{eid}",
            json={"title": "Updated"},
        )
        assert patch.status_code == 200
        assert patch.json()["title"] == "Updated"

    def test_other_user_cannot_patch_event(
        self, client_factory, creator_actor, brand_actor
    ):
        creator_client = client_factory(creator_actor)
        eid = creator_client.post(
            "/api/checkin/events/",
            json={"title": "creator-owned", "event_type": "generic"},
        ).json()["id"]

        brand_client = client_factory(brand_actor)
        # Different personal namespace → 404 (not 403)
        resp = brand_client.patch(
            f"/api/checkin/events/{eid}", json={"title": "Hijacked"}
        )
        assert resp.status_code == 404

    def test_school_admin_can_patch_event_in_same_school(
        self, client_factory, coach_actor, admin_actor
    ):
        coach_client = client_factory(coach_actor)
        eid = coach_client.post(
            "/api/checkin/events/",
            json={"title": "coach event", "event_type": "coach_clinic"},
        ).json()["id"]

        admin_client = client_factory(admin_actor)
        resp = admin_client.patch(
            f"/api/checkin/events/{eid}", json={"title": "Admin override"}
        )
        # Same school admin bypass — coach + admin both in school-uuid-A
        assert resp.status_code == 200

    def test_owner_can_cancel_own_event(self, client_factory, creator_actor):
        client = client_factory(creator_actor)
        eid = client.post(
            "/api/checkin/events/",
            json={"title": "to cancel", "event_type": "generic"},
        ).json()["id"]
        resp = client.delete(f"/api/checkin/events/{eid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"


# ── school_only visibility ──────────────────────────────────────────


class TestSchoolOnlyVisibility:
    def test_school_admin_can_create_school_only_event(
        self, client_factory, admin_actor
    ):
        client = client_factory(admin_actor)
        resp = client.post(
            "/api/checkin/events/",
            json={
                "title": "Bama internal mixer",
                "event_type": "generic",
                "visibility": "school_only",
                "status": "published",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["visibility"] == "school_only"
        assert body["school_id"] == "school-uuid-A"

    def test_creator_without_school_cannot_create_school_only_event(
        self, client_factory, creator_actor
    ):
        client = client_factory(creator_actor)
        resp = client.post(
            "/api/checkin/events/",
            json={
                "title": "Should fail — no school",
                "event_type": "generic",
                "visibility": "school_only",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "school_binding_required"

    def test_fan_in_school_can_register_for_same_school_only_event(
        self, client_factory, admin_actor, fan_in_school
    ):
        admin_client = client_factory(admin_actor)
        eid = admin_client.post(
            "/api/checkin/events/",
            json={
                "title": "school internal",
                "event_type": "generic",
                "visibility": "school_only",
                "status": "published",
            },
        ).json()["id"]

        fan_client = client_factory(fan_in_school)
        resp = fan_client.post(
            f"/api/checkin/events/{eid}/register",
            json={"attendee_user_id": fan_in_school["user_id"]},
        )
        assert resp.status_code == 201

    def test_fan_in_other_school_cannot_register_for_school_only_event(
        self, client_factory, admin_actor, fan_in_school_b
    ):
        admin_client = client_factory(admin_actor)
        eid = admin_client.post(
            "/api/checkin/events/",
            json={
                "title": "school internal",
                "event_type": "generic",
                "visibility": "school_only",
                "status": "published",
            },
        ).json()["id"]

        # fan_in_school_b is in school-uuid-B; the event is in school-uuid-A
        fan_client = client_factory(fan_in_school_b)
        resp = fan_client.post(
            f"/api/checkin/events/{eid}/register",
            json={"attendee_user_id": fan_in_school_b["user_id"]},
        )
        # 404 (not 403) — never leak existence
        assert resp.status_code == 404

    def test_no_school_fan_cannot_register_for_school_only_event(
        self, client_factory, admin_actor, fan_actor
    ):
        admin_client = client_factory(admin_actor)
        eid = admin_client.post(
            "/api/checkin/events/",
            json={
                "title": "school internal",
                "event_type": "generic",
                "visibility": "school_only",
                "status": "published",
            },
        ).json()["id"]

        fan_client = client_factory(fan_actor)
        resp = fan_client.post(
            f"/api/checkin/events/{eid}/register",
            json={"attendee_user_id": fan_actor["user_id"]},
        )
        assert resp.status_code == 404


# ── invite_only visibility ─────────────────────────────────────────


class TestInviteOnlyRegister:
    def test_fan_cannot_register_for_invite_only_without_invitation(
        self, client_factory, admin_actor, fan_actor
    ):
        admin_client = client_factory(admin_actor)
        eid = admin_client.post(
            "/api/checkin/events/",
            json={
                "title": "VIP only",
                "event_type": "generic",
                "visibility": "invite_only",
                "status": "published",
            },
        ).json()["id"]

        fan_client = client_factory(fan_actor)
        resp = fan_client.post(
            f"/api/checkin/events/{eid}/register",
            json={"attendee_user_id": fan_actor["user_id"]},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "invitation_required"

    def test_fan_with_accepted_invitation_can_register(
        self, client_factory, admin_actor, fan_actor
    ):
        admin_client = client_factory(admin_actor)
        eid = admin_client.post(
            "/api/checkin/events/",
            json={
                "title": "VIP only",
                "event_type": "generic",
                "visibility": "invite_only",
                "status": "published",
            },
        ).json()["id"]
        # Send + accept invitation
        send = admin_client.post(
            f"/api/checkin/events/{eid}/invitations",
            json={"invitees": [{"invitee_user_id": fan_actor["user_id"]}]},
        )
        invitation_id = send.json()["invitations"][0]["id"]

        fan_client = client_factory(fan_actor)
        fan_client.post(
            f"/api/checkin/events/{eid}/invitations/{invitation_id}/respond",
            json={"decision": "accepted"},
        )
        # Now register — should succeed
        resp = fan_client.post(
            f"/api/checkin/events/{eid}/register",
            json={"attendee_user_id": fan_actor["user_id"]},
        )
        assert resp.status_code == 201

    def test_owner_can_register_themselves_to_invite_only_without_invitation(
        self, client_factory, creator_actor
    ):
        client = client_factory(creator_actor)
        eid = client.post(
            "/api/checkin/events/",
            json={
                "title": "self-invite",
                "event_type": "generic",
                "visibility": "invite_only",
                "status": "published",
            },
        ).json()["id"]
        resp = client.post(
            f"/api/checkin/events/{eid}/register",
            json={"attendee_user_id": creator_actor["user_id"]},
        )
        assert resp.status_code == 201

    def test_public_register_unchanged(
        self, client_factory, creator_actor, fan_actor
    ):
        creator_client = client_factory(creator_actor)
        eid = creator_client.post(
            "/api/checkin/events/",
            json={
                "title": "Public party",
                "event_type": "generic",
                "visibility": "public",
                "status": "published",
            },
        ).json()["id"]

        fan_client = client_factory(fan_actor)
        resp = fan_client.post(
            f"/api/checkin/events/{eid}/register",
            json={"attendee_user_id": fan_actor["user_id"]},
        )
        assert resp.status_code == 201


# ── Discover endpoint ────────────────────────────────────────────────


class TestDiscoverEndpoint:
    def test_discover_returns_only_public_events(
        self, client_factory, creator_actor, admin_actor, fan_actor
    ):
        # 1 public, 1 invite_only, 1 unlisted, 1 school_only
        creator_client = client_factory(creator_actor)
        creator_client.post(
            "/api/checkin/events/",
            json={
                "title": "PUBLIC EVENT",
                "event_type": "generic",
                "visibility": "public",
                "status": "published",
            },
        )
        creator_client.post(
            "/api/checkin/events/",
            json={
                "title": "INVITE ONLY",
                "event_type": "generic",
                "visibility": "invite_only",
                "status": "published",
            },
        )
        creator_client.post(
            "/api/checkin/events/",
            json={
                "title": "UNLISTED",
                "event_type": "generic",
                "visibility": "unlisted",
                "status": "published",
            },
        )
        admin_client = client_factory(admin_actor)
        admin_client.post(
            "/api/checkin/events/",
            json={
                "title": "SCHOOL ONLY",
                "event_type": "generic",
                "visibility": "school_only",
                "status": "published",
            },
        )

        fan_client = client_factory(fan_actor)
        resp = fan_client.get("/api/checkin/events/discover")
        assert resp.status_code == 200
        events = resp.json()["events"]
        titles = {e["title"] for e in events}
        assert "PUBLIC EVENT" in titles
        assert "INVITE ONLY" not in titles
        assert "UNLISTED" not in titles
        assert "SCHOOL ONLY" not in titles  # cross-school fan can't see

    def test_discover_includes_school_only_when_caller_is_in_school(
        self, client_factory, admin_actor, fan_in_school
    ):
        admin_client = client_factory(admin_actor)
        admin_client.post(
            "/api/checkin/events/",
            json={
                "title": "SCHOOL_ONLY_VISIBLE",
                "event_type": "generic",
                "visibility": "school_only",
                "status": "published",
            },
        )

        fan_client = client_factory(fan_in_school)
        resp = fan_client.get("/api/checkin/events/discover")
        assert resp.status_code == 200
        titles = {e["title"] for e in resp.json()["events"]}
        assert "SCHOOL_ONLY_VISIBLE" in titles

    def test_discover_filters_by_event_type(
        self, client_factory, creator_actor, fan_actor
    ):
        creator_client = client_factory(creator_actor)
        creator_client.post(
            "/api/checkin/events/",
            json={
                "title": "creator party",
                "event_type": "generic",
                "visibility": "public",
                "status": "published",
            },
        )
        creator_client.post(
            "/api/checkin/events/",
            json={
                "title": "brand activation",
                "event_type": "brand_activation",
                "visibility": "public",
                "status": "published",
            },
        )

        fan_client = client_factory(fan_actor)
        resp = fan_client.get(
            "/api/checkin/events/discover?event_type=brand_activation"
        )
        assert resp.status_code == 200
        events = resp.json()["events"]
        assert all(e["event_type"] == "brand_activation" for e in events)

    def test_discover_excludes_lat_lon_pii(
        self, client_factory, creator_actor, fan_actor
    ):
        creator_client = client_factory(creator_actor)
        creator_client.post(
            "/api/checkin/events/",
            json={
                "title": "with venue",
                "event_type": "generic",
                "visibility": "public",
                "status": "published",
                "latitude": 33.2098,
                "longitude": -87.5692,
            },
        )

        fan_client = client_factory(fan_actor)
        resp = fan_client.get("/api/checkin/events/discover")
        assert resp.status_code == 200
        for e in resp.json()["events"]:
            # location_name is fine; raw lat/lon is NOT (PII guard)
            assert "latitude" not in e
            assert "longitude" not in e

    def test_discover_total_is_match_count_not_page_size(
        self, client_factory, creator_actor, fan_actor
    ):
        """Phase 10 review-fix: `total` MUST be the count of all matching
        rows, not just the current page. Pagination metadata is wrong if
        page 2 of 50 still reports total=50 even though 12 events match.
        """
        creator_client = client_factory(creator_actor)
        # Seed 12 public events
        for i in range(12):
            creator_client.post(
                "/api/checkin/events/",
                json={
                    "title": f"public event {i}",
                    "event_type": "generic",
                    "visibility": "public",
                    "status": "published",
                },
            )

        fan_client = client_factory(fan_actor)
        # Page 1: limit=5
        page1 = fan_client.get("/api/checkin/events/discover?limit=5&offset=0")
        assert page1.status_code == 200
        body1 = page1.json()
        assert len(body1["events"]) == 5
        assert body1["total"] == 12, (
            f"page 1 total must be the full match count (12), "
            f"not the page size (5); got {body1['total']}"
        )

        # Page 2: limit=5, offset=5
        page2 = fan_client.get("/api/checkin/events/discover?limit=5&offset=5")
        assert page2.status_code == 200
        body2 = page2.json()
        assert len(body2["events"]) == 5
        assert body2["total"] == 12

        # Page 3: tail (2 events left)
        page3 = fan_client.get("/api/checkin/events/discover?limit=5&offset=10")
        assert page3.status_code == 200
        body3 = page3.json()
        assert len(body3["events"]) == 2
        assert body3["total"] == 12

    def test_discover_total_respects_event_type_filter(
        self, client_factory, creator_actor, fan_actor
    ):
        """The `total` count must reflect the filter set, not the
        unfiltered universe. e.g. filtering by `brand_activation`
        when 3 of 10 events match must return total=3, not total=10.
        """
        creator_client = client_factory(creator_actor)
        for i in range(7):
            creator_client.post(
                "/api/checkin/events/",
                json={
                    "title": f"generic {i}",
                    "event_type": "generic",
                    "visibility": "public",
                    "status": "published",
                },
            )
        for i in range(3):
            creator_client.post(
                "/api/checkin/events/",
                json={
                    "title": f"brand {i}",
                    "event_type": "brand_activation",
                    "visibility": "public",
                    "status": "published",
                },
            )

        fan_client = client_factory(fan_actor)
        resp = fan_client.get(
            "/api/checkin/events/discover?event_type=brand_activation&limit=10"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["events"]) == 3


# ── NFC checkin opt-in ───────────────────────────────────────────────


class TestNfcCheckinOptIn:
    def test_allow_nfc_checkin_persists_on_create(
        self, client_factory, creator_actor
    ):
        client = client_factory(creator_actor)
        resp = client.post(
            "/api/checkin/events/",
            json={
                "title": "NFC event",
                "event_type": "generic",
                "visibility": "public",
                "allow_nfc_checkin": True,
                "checkin_method": "qr",
                "status": "published",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["allow_nfc_checkin"] is True

    def test_default_allow_nfc_checkin_is_false(
        self, client_factory, creator_actor
    ):
        client = client_factory(creator_actor)
        resp = client.post(
            "/api/checkin/events/",
            json={
                "title": "default NFC off",
                "event_type": "generic",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["allow_nfc_checkin"] is False

    def test_nfc_method_accepted_when_allow_nfc_checkin_true(
        self, client_factory, creator_actor, fan_actor
    ):
        creator_client = client_factory(creator_actor)
        eid = creator_client.post(
            "/api/checkin/events/",
            json={
                "title": "nfc-enabled",
                "event_type": "generic",
                "visibility": "public",
                "allow_nfc_checkin": True,
                "checkin_method": "qr",
                "status": "published",
            },
        ).json()["id"]
        # PNM registers first
        fan_client = client_factory(fan_actor)
        fan_client.post(
            f"/api/checkin/events/{eid}/register",
            json={"attendee_user_id": fan_actor["user_id"]},
        )
        # Then taps NFC
        resp = fan_client.post(
            f"/api/checkin/events/{eid}/checkin",
            headers={"Idempotency-Key": "nfc-test-12345678"},
            json={
                "attendee_user_id": fan_actor["user_id"],
                "checkin_method": "nfc",
            },
        )
        # POST /checkin returns 200 (not 201) — the success outcome is
        # in the body's `status` field per the existing checkin-router
        # contract. Either is acceptable here.
        assert resp.status_code in (200, 201), resp.text
        assert resp.json()["status"] == "success"

    def test_nfc_method_rejected_when_allow_nfc_checkin_false(
        self, client_factory, creator_actor, fan_actor
    ):
        creator_client = client_factory(creator_actor)
        eid = creator_client.post(
            "/api/checkin/events/",
            json={
                "title": "nfc-disabled",
                "event_type": "generic",
                "visibility": "public",
                "allow_nfc_checkin": False,
                "checkin_method": "qr",
                "status": "published",
            },
        ).json()["id"]
        fan_client = client_factory(fan_actor)
        fan_client.post(
            f"/api/checkin/events/{eid}/register",
            json={"attendee_user_id": fan_actor["user_id"]},
        )
        resp = fan_client.post(
            f"/api/checkin/events/{eid}/checkin",
            headers={"Idempotency-Key": "nfc-blocked-1234567"},
            json={
                "attendee_user_id": fan_actor["user_id"],
                "checkin_method": "nfc",
            },
        )
        # Either 409 nfc_disabled or 422 (Pydantic enum reject)
        assert resp.status_code in (409, 422)
        if resp.status_code == 409:
            assert resp.json()["detail"]["code"] == "nfc_disabled"
