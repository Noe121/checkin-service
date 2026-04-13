"""PII hashing + sanitization helpers for checkin-service.

Mirrors the canonical helpers used in admin-dashboard-service routers
(`_hp` / `_sn` in greek_life_advisor.py and institutional_sponsorships.py).

We do NOT import from `shared/pii_crypto.py` directly because that module
takes its key from `PII_HMAC_KEY` env var with a dev fallback — and on
local pytest runs we don't want to require that env var. Instead we
re-implement the same SHA-256 truncation here, with an env-var-overridable
salt for production use.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import os
import re
import secrets
from typing import Optional

# Salt baked into the PII hash. Defaults to a dev-only fallback so local
# pytest runs don't need an env var. Production sets PII_HMAC_KEY via
# Secrets Manager (same env var used by shared/pii_crypto.py).
_PII_HMAC_KEY = os.getenv(
    "PII_HMAC_KEY",
    "dev-checkin-pii-hmac-do-not-use-in-prod",
).encode("utf-8")

# Salt baked into the QR token signature. Defaults to a dev-only fallback.
_QR_SIGNING_KEY = os.getenv(
    "QR_SIGNING_KEY",
    "dev-checkin-qr-signing-do-not-use-in-prod",
).encode("utf-8")


def hash_pii(value: object) -> str:
    """HMAC-SHA256 of `value` truncated to 16 hex chars.

    Used for: lat_hash, lon_hash, hashed_decider_id, audit log actor IDs.
    Deterministic — same input always produces the same hash. NOT reversible.
    """
    if value is None:
        return ""
    digest = hmac.new(_PII_HMAC_KEY, str(value).encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:16]


def sha256_full(value: object) -> str:
    """Plain SHA-256 of `value`, full 64-char hex.

    Used for: qr_token_hash. Plain SHA-256 (NOT HMAC) so an attacker who
    sees the hash cannot brute-force the underlying token without also
    knowing the QR signing key — but the token itself already contains
    the HMAC signature, so the hash here is just for storage lookup.
    """
    if value is None:
        return ""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value: Optional[str], max_len: int = 200) -> Optional[str]:
    """HTML-escape, strip control chars, truncate.

    Defends against stored XSS in event titles, descriptions, notes,
    and any other admin-supplied free text. Mirrors `_sn()` in the
    greek_life_advisor.py / institutional_sponsorships.py routers.

    Returns None for empty input (so we never persist `""` and never
    persist a row of stripped-control-char garbage).
    """
    if value is None:
        return None
    cleaned = _CONTROL_CHAR_RE.sub("", str(value)).strip()
    if not cleaned:
        return None
    escaped = html.escape(cleaned, quote=True)
    return escaped[:max_len] if len(escaped) > max_len else escaped


def make_nonce() -> str:
    """32-char hex random nonce for QR token signing."""
    return secrets.token_hex(16)


def hmac_sign(payload: str) -> str:
    """HMAC-SHA256 hex signature of `payload` using the QR signing key."""
    return hmac.new(_QR_SIGNING_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def hmac_verify(payload: str, signature: str) -> bool:
    """Constant-time HMAC verify."""
    expected = hmac_sign(payload)
    return hmac.compare_digest(expected, signature)
