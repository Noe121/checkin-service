"""Phase 2 tests — pure-unit tests for the service layer (no DB / no app)."""
from __future__ import annotations

import math

import pytest

from src.services.geofence_service import (
    hash_coordinate,
    haversine_distance_m,
    round_for_hash,
    verify_distance,
)
from src.services.hashing import (
    hash_pii,
    hmac_sign,
    hmac_verify,
    make_nonce,
    sanitize_text,
    sha256_full,
)


# ── hashing ──────────────────────────────────────────────────────────────


def test_hash_pii_deterministic():
    a = hash_pii("user-123")
    b = hash_pii("user-123")
    assert a == b
    assert len(a) == 16


def test_hash_pii_different_inputs_different_outputs():
    assert hash_pii("user-123") != hash_pii("user-456")


def test_hash_pii_none_returns_empty():
    assert hash_pii(None) == ""


def test_sha256_full_64_chars():
    h = sha256_full("hello")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_sanitize_text_html_escape():
    out = sanitize_text("<script>alert(1)</script>")
    assert out is not None
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_sanitize_text_strips_control_chars():
    out = sanitize_text("hello\x00\x01world")
    assert out == "helloworld"


def test_sanitize_text_truncates():
    out = sanitize_text("a" * 500, max_len=100)
    assert out is not None
    assert len(out) == 100


def test_sanitize_text_empty_returns_none():
    assert sanitize_text("") is None
    assert sanitize_text("   ") is None
    assert sanitize_text(None) is None


def test_make_nonce_unique():
    nonces = {make_nonce() for _ in range(100)}
    assert len(nonces) == 100
    for n in nonces:
        assert len(n) == 32


def test_hmac_sign_and_verify_roundtrip():
    sig = hmac_sign("payload-123")
    assert hmac_verify("payload-123", sig)
    assert not hmac_verify("payload-456", sig)


def test_hmac_verify_constant_time():
    """hmac.compare_digest should be used — there's no timing leak.
    We just confirm a small mutation invalidates the signature."""
    sig = hmac_sign("payload-123")
    bad = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    assert not hmac_verify("payload-123", bad)


# ── geofence ─────────────────────────────────────────────────────────────


def test_haversine_zero_distance():
    d = haversine_distance_m(33.21, -87.56, 33.21, -87.56)
    assert d == pytest.approx(0.0, abs=0.001)


def test_haversine_known_distance():
    """Tuscaloosa, AL to Birmingham, AL ~ 80km."""
    d = haversine_distance_m(33.2098, -87.5692, 33.5186, -86.8104)
    assert 75_000 < d < 90_000


def test_round_for_hash_3_decimals():
    assert round_for_hash(33.2098765) == 33.21
    assert round_for_hash(-87.5691234) == -87.569


def test_hash_coordinate_passes_through_none():
    assert hash_coordinate(None) is None


def test_hash_coordinate_deterministic():
    a = hash_coordinate(33.21)
    b = hash_coordinate(33.21)
    assert a == b
    assert len(a) == 16


def test_verify_distance_inside():
    r = verify_distance(
        submitted_lat=33.21001,
        submitted_lon=-87.56930,
        event_lat=33.21000,
        event_lon=-87.56930,
        radius_m=200,
    )
    assert r.passed
    assert r.distance_m < 5


def test_verify_distance_outside():
    r = verify_distance(
        submitted_lat=33.6,
        submitted_lon=-87.6,
        event_lat=33.21,
        event_lon=-87.5693,
        radius_m=200,
    )
    assert not r.passed
    assert r.reason == "out_of_range"
    assert r.distance_m > 200


def test_verify_distance_missing_submitted():
    r = verify_distance(
        submitted_lat=None,
        submitted_lon=None,
        event_lat=33.21,
        event_lon=-87.56,
        radius_m=200,
    )
    assert not r.passed
    assert r.reason == "missing_submitted_coords"


def test_verify_distance_invalid_radius():
    r = verify_distance(
        submitted_lat=33.21,
        submitted_lon=-87.56,
        event_lat=33.21,
        event_lon=-87.56,
        radius_m=10_000,
    )
    assert not r.passed
    assert r.reason == "invalid_radius"


# ── QR token format ──────────────────────────────────────────────────────


def test_qr_token_format_lifecycle():
    """Verify the round-trip via the service layer with a SQLite session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from src.database import Base
    from src.services.qr_token_service import (
        QrTokenVerifyResult,
        mint_token,
        verify_token,
    )

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()

    raw, row = mint_token(
        db,
        event_id=42,
        school_id="school-A",
        issued_by_user_id="admin-1",
        ttl_minutes=10,
    )
    parts = raw.split(":")
    assert len(parts) == 5
    assert parts[0] == "events"
    assert parts[1] == "42"

    # Happy path
    result = verify_token(db, raw_token=raw, event_id=42)
    assert result.ok

    # Replay (single_use → already used)
    replay = verify_token(db, raw_token=raw, event_id=42)
    assert replay.status == QrTokenVerifyResult.ALREADY_USED

    # Wrong event
    wrong_event = verify_token(db, raw_token=raw, event_id=99)
    assert wrong_event.status == QrTokenVerifyResult.EVENT_MISMATCH

    # Tampered signature
    bad = raw[:-2] + ("aa" if raw[-2:] != "aa" else "bb")
    tampered = verify_token(db, raw_token=bad, event_id=42)
    assert tampered.status == QrTokenVerifyResult.SIGNATURE_MISMATCH

    db.close()
