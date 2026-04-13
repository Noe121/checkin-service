"""Phase 2 tests — events CRUD router."""
from __future__ import annotations


def _create_event(client, **overrides):
    body = {
        "event_type": "rush",
        "title": "Open House Round 1",
        "description": "Welcome to <Bama> rush week",
        "location_name": "Sorority Row",
        "latitude": 33.2098,
        "longitude": -87.5692,
        "geofence_radius_m": 200,
        "max_capacity": 50,
        "checkin_method": "qr_geo",
        "status": "published",
    }
    body.update(overrides)
    return client.post("/api/checkin/events/", json=body)


# ── Auth gate ────────────────────────────────────────────────────────────


def test_unauthenticated_event_create_401(unauthed_client):
    r = unauthed_client.post("/api/checkin/events/", json={"title": "x"})
    assert r.status_code == 401


def test_unauthenticated_event_list_401(unauthed_client):
    r = unauthed_client.get("/api/checkin/events/")
    assert r.status_code == 401


def test_fan_cannot_create_event_403(client_factory, fan_actor):
    client = client_factory(fan_actor)
    r = _create_event(client)
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "permission_denied"


# ── Create / read ────────────────────────────────────────────────────────


def test_admin_creates_event_201(client_factory, admin_actor):
    client = client_factory(admin_actor)
    r = _create_event(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["event_type"] == "rush"
    assert body["title"] == "Open House Round 1"
    assert body["status"] == "published"
    assert body["school_id"] == admin_actor["school_id"]
    assert body["latitude"] == 33.2098  # admin response includes coords
    assert body["longitude"] == -87.5692


def test_admin_get_by_id(client_factory, admin_actor):
    client = client_factory(admin_actor)
    create = _create_event(client)
    event_id = create.json()["id"]
    r = client.get(f"/api/checkin/events/{event_id}")
    assert r.status_code == 200
    assert r.json()["id"] == event_id


def test_admin_list_filters(client_factory, admin_actor):
    client = client_factory(admin_actor)
    _create_event(client, event_type="rush", title="Rush A")
    _create_event(client, event_type="coach_clinic", title="Clinic A")
    r = client.get("/api/checkin/events/?event_type=rush")
    assert r.status_code == 200
    titles = [e["title"] for e in r.json()]
    assert "Rush A" in titles
    assert "Clinic A" not in titles


# ── Validation ───────────────────────────────────────────────────────────


def test_lat_without_lon_422(client_factory, admin_actor):
    client = client_factory(admin_actor)
    r = _create_event(client, latitude=33.0, longitude=None)
    assert r.status_code == 422


def test_end_before_start_422(client_factory, admin_actor):
    client = client_factory(admin_actor)
    r = _create_event(
        client,
        start_time="2026-08-15T10:00:00",
        end_time="2026-08-15T09:00:00",
    )
    assert r.status_code == 422


def test_geofence_radius_capped_422(client_factory, admin_actor):
    client = client_factory(admin_actor)
    r = _create_event(client, geofence_radius_m=10_000)
    assert r.status_code == 422


def test_title_html_escaped(client_factory, admin_actor):
    client = client_factory(admin_actor)
    r = _create_event(client, title="<script>alert(1)</script> Round")
    assert r.status_code == 201
    title = r.json()["title"]
    # _sn() escapes < > & "
    assert "<script>" not in title
    assert "&lt;script&gt;" in title


# ── Idempotency-Key ──────────────────────────────────────────────────────


def test_invalid_idempotency_key_400(client_factory, admin_actor):
    client = client_factory(admin_actor)
    r = client.post(
        "/api/checkin/events/",
        json={"title": "x", "event_type": "rush", "status": "draft", "checkin_method": "none"},
        headers={"Idempotency-Key": "with space"},
    )
    assert r.status_code == 400


def test_idempotency_replay_returns_same_event(client_factory, admin_actor):
    """Phase 2.1 fix (Finding #3) — POST /events with the same
    Idempotency-Key MUST return the original event row, not create a
    duplicate. The previous version of this router validated the
    Idempotency-Key regex and then ignored it; the V116 schema fix
    added an idempotency_key column + (school_id, idempotency_key) UNIQUE
    and the router now does the replay lookup."""
    client = client_factory(admin_actor)
    headers = {"Idempotency-Key": "rush-event-abc12345"}
    first = _create_event(client, headers=headers) if False else client.post(
        "/api/checkin/events/",
        json={
            "event_type": "rush",
            "title": "Replay Test Event",
            "status": "published",
            "checkin_method": "none",
        },
        headers=headers,
    )
    assert first.status_code == 201
    second = client.post(
        "/api/checkin/events/",
        json={
            "event_type": "rush",
            "title": "Replay Test Event",
            "status": "published",
            "checkin_method": "none",
        },
        headers=headers,
    )
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"], "replay must return the same event id"


def test_idempotency_different_keys_create_distinct_events(client_factory, admin_actor):
    client = client_factory(admin_actor)
    a = client.post(
        "/api/checkin/events/",
        json={"event_type": "rush", "title": "A", "status": "published", "checkin_method": "none"},
        headers={"Idempotency-Key": "key-aaaaaaaa"},
    )
    b = client.post(
        "/api/checkin/events/",
        json={"event_type": "rush", "title": "B", "status": "published", "checkin_method": "none"},
        headers={"Idempotency-Key": "key-bbbbbbbb"},
    )
    assert a.json()["id"] != b.json()["id"]


def test_idempotency_no_key_creates_distinct_events(client_factory, admin_actor):
    """Without Idempotency-Key, two POSTs always create distinct events."""
    client = client_factory(admin_actor)
    first = _create_event(client)
    second = _create_event(client)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


# ── Cross-tenant ─────────────────────────────────────────────────────────


def test_cross_tenant_get_404(client_factory, admin_actor, admin_actor_other_school):
    admin_a = client_factory(admin_actor)
    create = _create_event(admin_a)
    event_id = create.json()["id"]

    admin_b = client_factory(admin_actor_other_school)
    r = admin_b.get(f"/api/checkin/events/{event_id}")
    assert r.status_code == 404


def test_cross_tenant_patch_404(client_factory, admin_actor, admin_actor_other_school):
    admin_a = client_factory(admin_actor)
    event_id = _create_event(admin_a).json()["id"]

    admin_b = client_factory(admin_actor_other_school)
    r = admin_b.patch(f"/api/checkin/events/{event_id}", json={"title": "Hijack"})
    assert r.status_code == 404


# ── Soft delete ──────────────────────────────────────────────────────────


def test_delete_soft_cancels(client_factory, admin_actor):
    client = client_factory(admin_actor)
    event_id = _create_event(client).json()["id"]
    r = client.delete(f"/api/checkin/events/{event_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    # Still readable, just with cancelled status
    follow = client.get(f"/api/checkin/events/{event_id}")
    assert follow.status_code == 200
    assert follow.json()["status"] == "cancelled"
