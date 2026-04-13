"""Phase 2 tests — QR token mint, geofence verification, and check-in submission."""
from __future__ import annotations


def _create_event_with_geo(client, **overrides):
    body = {
        "event_type": "rush",
        "title": "Sisterhood Round",
        "status": "active",  # active so check-in is allowed
        "checkin_method": "qr_geo",
        "max_capacity": 100,
        "location_name": "Sorority House 7",
        "latitude": 33.21000,
        "longitude": -87.56930,
        "geofence_radius_m": 200,
    }
    body.update(overrides)
    return client.post("/api/checkin/events/", json=body)


def _register_fan(fan_client, event_id):
    """Phase 2.1 — POST /checkin requires a pre-existing registration row."""
    return fan_client.post(f"/api/checkin/events/{event_id}/register", json={})


# ── QR token mint ────────────────────────────────────────────────────────


def test_admin_mints_qr_token(client_factory, admin_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin).json()["id"]
    r = admin.post(
        f"/api/checkin/events/{event_id}/qr-tokens",
        json={"ttl_minutes": 30, "single_use": True},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["event_id"] == event_id
    assert body["event_table"] == "events"
    assert body["raw_token"]  # raw token only returned once
    # Format: "events:{event_id}:{nonce}:{expires_unix}:{sig}"
    parts = body["raw_token"].split(":")
    assert len(parts) == 5
    assert parts[0] == "events"
    assert parts[1] == str(event_id)


def test_qr_token_list_no_raw(client_factory, admin_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin).json()["id"]
    admin.post(f"/api/checkin/events/{event_id}/qr-tokens", json={"ttl_minutes": 30})
    r = admin.get(f"/api/checkin/events/{event_id}/qr-tokens")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    # Raw token never appears in list responses
    assert "raw_token" not in rows[0]
    assert "token_hash" not in rows[0]


def test_fan_cannot_mint_qr_token_403(client_factory, admin_actor, fan_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin).json()["id"]
    fan = client_factory(fan_actor)
    r = fan.post(
        f"/api/checkin/events/{event_id}/qr-tokens",
        json={"ttl_minutes": 30},
    )
    assert r.status_code == 403


# ── Successful check-in (qr + geo) ───────────────────────────────────────


def test_qr_geo_checkin_success(client_factory, admin_actor, fan_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin).json()["id"]
    mint = admin.post(
        f"/api/checkin/events/{event_id}/qr-tokens",
        json={"ttl_minutes": 30, "single_use": True},
    )
    raw_token = mint.json()["raw_token"]

    fan = client_factory(fan_actor)
    _register_fan(fan, event_id)
    # Submit coords ~50m north of the venue (well within 200m radius)
    r = fan.post(
        f"/api/checkin/events/{event_id}/checkin",
        json={
            "qr_token": raw_token,
            "lat": 33.21045,
            "lon": -87.56930,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["geofence_passed"] is True
    assert body["distance_m"] is not None
    assert body["distance_m"] < 200


def test_tampered_qr_token_invalid(client_factory, admin_actor, fan_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin).json()["id"]
    mint = admin.post(f"/api/checkin/events/{event_id}/qr-tokens", json={"ttl_minutes": 30})
    raw_token = mint.json()["raw_token"]

    # Flip one character of the signature
    bad_token = raw_token[:-2] + ("aa" if raw_token[-2:] != "aa" else "bb")

    fan = client_factory(fan_actor)
    _register_fan(fan, event_id)
    r = fan.post(
        f"/api/checkin/events/{event_id}/checkin",
        json={
            "qr_token": bad_token,
            "lat": 33.21000,
            "lon": -87.56930,
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "invalid_token"


def test_geofence_failed(client_factory, admin_actor, fan_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin).json()["id"]
    mint = admin.post(f"/api/checkin/events/{event_id}/qr-tokens", json={"ttl_minutes": 30})
    raw_token = mint.json()["raw_token"]

    fan = client_factory(fan_actor)
    _register_fan(fan, event_id)
    # Submit coords ~50km away
    r = fan.post(
        f"/api/checkin/events/{event_id}/checkin",
        json={
            "qr_token": raw_token,
            "lat": 33.6,
            "lon": -87.6,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "geofence_failed"
    assert body["geofence_passed"] is False
    assert body["distance_m"] > 200


def test_qr_only_event(client_factory, admin_actor, fan_actor):
    """checkin_method='qr' — coords are ignored, only token matters."""
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin, checkin_method="qr").json()["id"]
    mint = admin.post(f"/api/checkin/events/{event_id}/qr-tokens", json={"ttl_minutes": 30})
    raw_token = mint.json()["raw_token"]
    fan = client_factory(fan_actor)
    _register_fan(fan, event_id)
    r = fan.post(
        f"/api/checkin/events/{event_id}/checkin",
        json={"qr_token": raw_token},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "success"


def test_qr_token_single_use_replay_invalid(client_factory, admin_actor, fan_actor, fan_actor_other):
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin, checkin_method="qr").json()["id"]
    mint = admin.post(
        f"/api/checkin/events/{event_id}/qr-tokens",
        json={"ttl_minutes": 30, "single_use": True},
    )
    raw_token = mint.json()["raw_token"]

    fan_a = client_factory(fan_actor)
    _register_fan(fan_a, event_id)
    first = fan_a.post(
        f"/api/checkin/events/{event_id}/checkin",
        json={"qr_token": raw_token},
    )
    assert first.json()["status"] == "success"

    fan_b = client_factory(fan_actor_other)
    _register_fan(fan_b, event_id)
    second = fan_b.post(
        f"/api/checkin/events/{event_id}/checkin",
        json={"qr_token": raw_token},
    )
    assert second.json()["status"] == "invalid_token"


def test_duplicate_checkin_returns_duplicate(client_factory, admin_actor, fan_actor):
    """Same fan checking in twice (different tokens) → second is duplicate."""
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin, checkin_method="qr").json()["id"]
    mint1 = admin.post(
        f"/api/checkin/events/{event_id}/qr-tokens",
        json={"ttl_minutes": 30, "single_use": False},  # reusable
    )
    raw_token = mint1.json()["raw_token"]

    fan = client_factory(fan_actor)
    _register_fan(fan, event_id)
    fan.post(f"/api/checkin/events/{event_id}/checkin", json={"qr_token": raw_token})
    second = fan.post(f"/api/checkin/events/{event_id}/checkin", json={"qr_token": raw_token})
    assert second.json()["status"] == "duplicate"


# ── Phase 2.1 review-fix regression guards ───────────────────────────────


def test_checkin_without_registration_returns_required(client_factory, admin_actor, fan_actor):
    """Phase 2.1 fix (Finding #1) — POST /checkin requires a pre-existing
    registration row. The previous version of the router auto-created
    attendance for missing registrations, which combined with the lack
    of school-tenant filtering on the event lookup meant a fan could
    check in to any school's event without ever RSVPing."""
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin, checkin_method="qr").json()["id"]
    mint = admin.post(f"/api/checkin/events/{event_id}/qr-tokens", json={"ttl_minutes": 30})
    raw_token = mint.json()["raw_token"]

    # Fan tries to check in WITHOUT registering first
    fan = client_factory(fan_actor)
    r = fan.post(f"/api/checkin/events/{event_id}/checkin", json={"qr_token": raw_token})
    assert r.status_code == 200
    assert r.json()["status"] == "registration_required"


def test_checkin_after_cancelled_registration_returns_required(client_factory, admin_actor, fan_actor):
    """A cancelled registration should not allow check-in."""
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin, checkin_method="qr").json()["id"]
    mint = admin.post(f"/api/checkin/events/{event_id}/qr-tokens", json={"ttl_minutes": 30})
    raw_token = mint.json()["raw_token"]

    fan = client_factory(fan_actor)
    _register_fan(fan, event_id)
    fan.delete(f"/api/checkin/events/{event_id}/registrations/{fan_actor['user_id']}")

    r = fan.post(f"/api/checkin/events/{event_id}/checkin", json={"qr_token": raw_token})
    assert r.json()["status"] == "registration_required"


def test_qr_token_not_burnt_on_geofence_failure(client_factory, admin_actor, fan_actor):
    """Phase 2.1 fix (Finding #2) — single-use QR tokens must NOT be
    consumed by a failed geofence verification. The reviewer reproduced
    the original bug: first request returned geofence_failed, second
    request with the same token + valid coords returned invalid_token.
    With the peek/consume split, a failed geofence check leaves the
    token usable so a fan whose phone GPS was wonky on the first
    attempt can simply move closer and retry."""
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin).json()["id"]  # qr_geo
    mint = admin.post(
        f"/api/checkin/events/{event_id}/qr-tokens",
        json={"ttl_minutes": 30, "single_use": True},
    )
    raw_token = mint.json()["raw_token"]

    fan = client_factory(fan_actor)
    _register_fan(fan, event_id)

    # Attempt 1: bad coordinates → geofence_failed (token must NOT be consumed)
    first = fan.post(
        f"/api/checkin/events/{event_id}/checkin",
        json={"qr_token": raw_token, "lat": 33.6, "lon": -87.6},
    )
    assert first.json()["status"] == "geofence_failed"

    # Attempt 2: same token, good coordinates → success (token is still alive)
    second = fan.post(
        f"/api/checkin/events/{event_id}/checkin",
        json={"qr_token": raw_token, "lat": 33.21045, "lon": -87.56930},
    )
    assert second.json()["status"] == "success", second.text


def test_qr_token_not_burnt_on_invalid_token(client_factory, admin_actor, fan_actor):
    """Tampered token doesn't cause subsequent valid attempts to fail."""
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin, checkin_method="qr").json()["id"]
    mint = admin.post(
        f"/api/checkin/events/{event_id}/qr-tokens",
        json={"ttl_minutes": 30, "single_use": True},
    )
    raw_token = mint.json()["raw_token"]
    bad_token = raw_token[:-2] + ("aa" if raw_token[-2:] != "aa" else "bb")

    fan = client_factory(fan_actor)
    _register_fan(fan, event_id)

    # Bad token attempt — peek_token returns SIGNATURE_MISMATCH, never consumes
    bad = fan.post(f"/api/checkin/events/{event_id}/checkin", json={"qr_token": bad_token})
    assert bad.json()["status"] == "invalid_token"

    # Real token still works
    good = fan.post(f"/api/checkin/events/{event_id}/checkin", json={"qr_token": raw_token})
    assert good.json()["status"] == "success"


def test_qr_token_consumed_after_successful_checkin(client_factory, admin_actor, fan_actor, fan_actor_other):
    """The consume HAPPENS — just AFTER the insert, not before. A second
    fan trying to use a single-use token after the first fan succeeded
    should be rejected."""
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin, checkin_method="qr").json()["id"]
    mint = admin.post(
        f"/api/checkin/events/{event_id}/qr-tokens",
        json={"ttl_minutes": 30, "single_use": True},
    )
    raw_token = mint.json()["raw_token"]

    fan_a = client_factory(fan_actor)
    _register_fan(fan_a, event_id)
    first = fan_a.post(f"/api/checkin/events/{event_id}/checkin", json={"qr_token": raw_token})
    assert first.json()["status"] == "success"

    fan_b = client_factory(fan_actor_other)
    _register_fan(fan_b, event_id)
    second = fan_b.post(f"/api/checkin/events/{event_id}/checkin", json={"qr_token": raw_token})
    assert second.json()["status"] == "invalid_token"


def test_checkin_requires_method(client_factory, admin_actor, fan_actor):
    """Event with checkin_method='none' → check-in disabled (409)."""
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin, checkin_method="none").json()["id"]
    fan = client_factory(fan_actor)
    r = fan.post(f"/api/checkin/events/{event_id}/checkin", json={})
    assert r.status_code == 409


def test_checkin_event_not_active(client_factory, admin_actor, fan_actor):
    admin = client_factory(admin_actor)
    event_id = _create_event_with_geo(admin, status="draft").json()["id"]
    fan = client_factory(fan_actor)
    r = fan.post(f"/api/checkin/events/{event_id}/checkin", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "event_not_active"
