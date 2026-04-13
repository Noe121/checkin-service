"""Phase 2 tests — registrations (RSVP / capacity / waitlist / idempotency)."""
from __future__ import annotations


def _create_event(client, **overrides):
    body = {
        "event_type": "rush",
        "title": "Philanthropy Round",
        "status": "published",
        "checkin_method": "none",
        "max_capacity": 2,
    }
    body.update(overrides)
    return client.post("/api/checkin/events/", json=body)


def test_fan_self_register_201(client_factory, admin_actor, fan_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event(admin).json()["id"]

    fan = client_factory(fan_actor)
    r = fan.post(f"/api/checkin/events/{event_id}/register", json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "registered"
    assert body["attendee_user_id"] == fan_actor["user_id"]


def test_capacity_waitlist(client_factory, admin_actor, fan_actor, fan_actor_other):
    admin = client_factory(admin_actor)
    event_id = _create_event(admin, max_capacity=1).json()["id"]

    fan_a = client_factory(fan_actor)
    fan_a.post(f"/api/checkin/events/{event_id}/register", json={})

    fan_b = client_factory(fan_actor_other)
    r = fan_b.post(f"/api/checkin/events/{event_id}/register", json={})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "waitlisted"
    assert body["waitlist_position"] == 1


def test_idempotency_replay_returns_same_row(client_factory, admin_actor, fan_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event(admin).json()["id"]

    fan = client_factory(fan_actor)
    headers = {"Idempotency-Key": "fan-rsvp-abc12345"}
    first = fan.post(f"/api/checkin/events/{event_id}/register", json={}, headers=headers)
    assert first.status_code == 201
    second = fan.post(f"/api/checkin/events/{event_id}/register", json={}, headers=headers)
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_idempotency_malformed_key_400(client_factory, admin_actor, fan_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event(admin).json()["id"]
    fan = client_factory(fan_actor)
    r = fan.post(
        f"/api/checkin/events/{event_id}/register",
        json={},
        headers={"Idempotency-Key": "<script>"},
    )
    assert r.status_code == 400


def test_duplicate_register_returns_existing(client_factory, admin_actor, fan_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event(admin).json()["id"]
    fan = client_factory(fan_actor)
    first = fan.post(f"/api/checkin/events/{event_id}/register", json={})
    second = fan.post(f"/api/checkin/events/{event_id}/register", json={})
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_register_for_unpublished_event_409(client_factory, admin_actor, fan_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event(admin, status="draft").json()["id"]
    fan = client_factory(fan_actor)
    r = fan.post(f"/api/checkin/events/{event_id}/register", json={})
    assert r.status_code == 409


def test_fan_cannot_register_someone_else_403(client_factory, admin_actor, fan_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event(admin).json()["id"]
    fan = client_factory(fan_actor)
    r = fan.post(
        f"/api/checkin/events/{event_id}/register",
        json={"attendee_user_id": "different-uid"},
    )
    assert r.status_code == 403


def test_admin_lists_registrations_with_hashed_ids(client_factory, admin_actor, fan_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event(admin).json()["id"]
    fan = client_factory(fan_actor)
    fan.post(f"/api/checkin/events/{event_id}/register", json={})

    admin2 = client_factory(admin_actor)
    r = admin2.get(f"/api/checkin/events/{event_id}/registrations")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    # Raw user_id is never echoed; only hashed_attendee_id (16 hex chars)
    assert "attendee_user_id" not in rows[0]
    assert len(rows[0]["hashed_attendee_id"]) == 16
    assert rows[0]["hashed_attendee_id"] != fan_actor["user_id"]


def test_cancel_self_registration(client_factory, admin_actor, fan_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event(admin).json()["id"]
    fan = client_factory(fan_actor)
    fan.post(f"/api/checkin/events/{event_id}/register", json={})
    r = fan.delete(f"/api/checkin/events/{event_id}/registrations/{fan_actor['user_id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_cancel_someone_else_403(client_factory, fan_actor, fan_actor_other, admin_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event(admin).json()["id"]
    fan_a = client_factory(fan_actor)
    fan_a.post(f"/api/checkin/events/{event_id}/register", json={})
    fan_b = client_factory(fan_actor_other)
    r = fan_b.delete(f"/api/checkin/events/{event_id}/registrations/{fan_actor['user_id']}")
    assert r.status_code == 403
