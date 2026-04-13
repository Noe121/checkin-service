"""QR token mint + verify service.

Token format (Base32-friendly): `{event_id}:{nonce}:{expires_at_unix}:{hmac_sig}`

The token body contains NO PII — only the event ID, a random nonce,
the expiry epoch, and an HMAC signature over those three fields signed
with the QR_SIGNING_KEY env var. The token is stored ONLY as its
sha256 hash in the qr_tokens table; the raw token is returned to the
admin once at mint time and never persisted.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models import QrToken
from .hashing import hmac_sign, hmac_verify, make_nonce, sha256_full

_TOKEN_DELIM = ":"
_DEFAULT_TTL_MINUTES = 60
_MAX_TTL_MINUTES = 12 * 60  # 12 hours — outer bound on rush event door tokens


_VALID_EVENT_TABLES = {"events", "greek_rush_events"}


def mint_token(
    db: Session,
    *,
    event_id: int,
    school_id: str,
    issued_by_user_id: str,
    event_table: str = "events",
    ttl_minutes: int = _DEFAULT_TTL_MINUTES,
    single_use: bool = True,
) -> tuple[str, QrToken]:
    """Mint a new HMAC-signed QR token for an event.

    `event_table` is the polymorphic discriminator: 'events' (generic,
    used by checkin-service) or 'greek_rush_events' (used by
    greek_life_advisor.py when it adopts this service in Phase 3).

    Returns `(raw_token, qr_token_row)`. The raw token is the only time
    the caller will see the unhashed value — it should be encoded into a
    QR code and discarded.
    """
    if event_table not in _VALID_EVENT_TABLES:
        raise ValueError(f"event_table must be one of {_VALID_EVENT_TABLES}")
    if ttl_minutes <= 0 or ttl_minutes > _MAX_TTL_MINUTES:
        raise ValueError(f"ttl_minutes must be 1..{_MAX_TTL_MINUTES}")

    nonce = make_nonce()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    expires_unix = int(expires_at.timestamp())

    # Token signature includes the event_table discriminator so a token
    # minted for events.id=42 cannot be replayed against greek_rush_events.id=42.
    payload = (
        f"{event_table}{_TOKEN_DELIM}{event_id}"
        f"{_TOKEN_DELIM}{nonce}{_TOKEN_DELIM}{expires_unix}"
    )
    signature = hmac_sign(payload)
    raw_token = f"{payload}{_TOKEN_DELIM}{signature}"
    token_hash = sha256_full(raw_token)

    row = QrToken(
        school_id=school_id,
        event_table=event_table,
        event_id=event_id,
        token_hash=token_hash,
        nonce=nonce,
        expires_at=expires_at.replace(tzinfo=None),  # MySQL DATETIME is naive
        single_use=1 if single_use else 0,
        used_at=None,
        used_by_user_id=None,
        issued_by_user_id=issued_by_user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw_token, row


class QrTokenVerifyResult:
    """Result of verifying a QR token presented at check-in."""

    OK = "ok"
    INVALID_FORMAT = "invalid_format"
    SIGNATURE_MISMATCH = "signature_mismatch"
    EXPIRED = "expired"
    NOT_FOUND = "not_found"
    EVENT_MISMATCH = "event_mismatch"
    ALREADY_USED = "already_used"

    def __init__(self, status: str, qr_row: Optional[QrToken] = None) -> None:
        self.status = status
        self.qr_row = qr_row

    @property
    def ok(self) -> bool:
        return self.status == self.OK


def verify_token(
    db: Session,
    *,
    raw_token: str,
    event_id: int,
    event_table: str = "events",
    redeeming_user_id: Optional[str] = None,
    consume: bool = True,
) -> QrTokenVerifyResult:
    """Verify an incoming QR token.

    NB: Phase 2.1 fix — `consume` defaults to True for backwards compat,
    but the check-in router calls `peek_token()` (consume=False) FIRST,
    runs geofence + insert + commit, and only THEN calls `consume_token()`
    once the rest of the flow has succeeded. This prevents the
    "single-use token burned on geofence_failed" bug where a fan whose
    submitted coordinates were out-of-range had their QR token
    permanently marked used even though no event_checkins row was
    created.

    Returns a QrTokenVerifyResult — caller checks `.ok` and acts on the
    `.status` for failure cases.
    """
    if event_table not in _VALID_EVENT_TABLES:
        return QrTokenVerifyResult(QrTokenVerifyResult.INVALID_FORMAT)
    if not raw_token or not isinstance(raw_token, str):
        return QrTokenVerifyResult(QrTokenVerifyResult.INVALID_FORMAT)

    parts = raw_token.split(_TOKEN_DELIM)
    if len(parts) != 5:
        return QrTokenVerifyResult(QrTokenVerifyResult.INVALID_FORMAT)

    token_event_table, token_event_id_str, nonce, expires_unix_str, signature = parts
    if token_event_table not in _VALID_EVENT_TABLES:
        return QrTokenVerifyResult(QrTokenVerifyResult.INVALID_FORMAT)
    try:
        token_event_id = int(token_event_id_str)
        expires_unix = int(expires_unix_str)
    except ValueError:
        return QrTokenVerifyResult(QrTokenVerifyResult.INVALID_FORMAT)

    if token_event_id != event_id or token_event_table != event_table:
        return QrTokenVerifyResult(QrTokenVerifyResult.EVENT_MISMATCH)

    payload = (
        f"{token_event_table}{_TOKEN_DELIM}{token_event_id}"
        f"{_TOKEN_DELIM}{nonce}{_TOKEN_DELIM}{expires_unix}"
    )
    if not hmac_verify(payload, signature):
        return QrTokenVerifyResult(QrTokenVerifyResult.SIGNATURE_MISMATCH)

    if expires_unix < int(time.time()):
        return QrTokenVerifyResult(QrTokenVerifyResult.EXPIRED)

    token_hash = sha256_full(raw_token)
    row = db.query(QrToken).filter(QrToken.token_hash == token_hash).first()
    if row is None:
        # HMAC verified but no row — token was minted by a different process
        # or the row was deleted. Treat as invalid for safety.
        return QrTokenVerifyResult(QrTokenVerifyResult.NOT_FOUND)

    if row.single_use and row.used_at is not None:
        return QrTokenVerifyResult(QrTokenVerifyResult.ALREADY_USED, row)

    if consume:
        consume_token(db, qr_row=row, redeeming_user_id=redeeming_user_id)

    return QrTokenVerifyResult(QrTokenVerifyResult.OK, row)


def peek_token(
    db: Session,
    *,
    raw_token: str,
    event_id: int,
    event_table: str = "events",
) -> QrTokenVerifyResult:
    """Read-only QR token verification.

    Same checks as verify_token (HMAC signature, expiry, single-use status,
    event match) but does NOT mark the row as used. The check-in router
    uses this for the FIRST validation pass, then runs geofence + insert,
    and only calls consume_token() once everything else has succeeded.
    """
    return verify_token(
        db,
        raw_token=raw_token,
        event_id=event_id,
        event_table=event_table,
        consume=False,
    )


def consume_token(
    db: Session,
    *,
    qr_row: QrToken,
    redeeming_user_id: Optional[str] = None,
) -> None:
    """Mark a QR token row as used. Idempotent on non-single-use tokens.

    Called by the check-in router AFTER geofence verification + the
    event_checkins INSERT have succeeded. The two-phase pattern (peek
    then consume) prevents the "single-use token burned by a failed
    geofence check" regression.
    """
    if not qr_row.single_use:
        return
    if qr_row.used_at is not None:
        return
    qr_row.used_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if redeeming_user_id:
        qr_row.used_by_user_id = str(redeeming_user_id)
    db.commit()
    db.refresh(qr_row)
