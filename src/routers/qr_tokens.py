"""QR token mint + list router (admin-only)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import Event, QrToken
from ..schemas.qr_token import QrTokenListItem, QrTokenMintRequest, QrTokenMintResponse
from ..services.qr_token_service import mint_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/checkin/events", tags=["qr_tokens"])


@router.post(
    "/{event_id}/qr-tokens",
    response_model=QrTokenMintResponse,
    status_code=status.HTTP_201_CREATED,
)
def mint_qr_token(
    event_id: int,
    payload: QrTokenMintRequest,
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_admin),
) -> QrTokenMintResponse:
    """Mint a fresh HMAC-signed QR token for an event.

    Returns the raw token EXACTLY ONCE — the admin caller must encode it
    into a QR code immediately and never persist it. The server only
    stores its sha256 hash in qr_tokens.token_hash.
    """
    school_id = actor.get("school_id")
    if not school_id:
        raise HTTPException(status_code=403, detail="school_id required")

    event = (
        db.query(Event)
        .filter(Event.id == event_id, Event.school_id == str(school_id))
        .first()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    issued_by = str(actor.get("user_id") or "service")
    raw_token, row = mint_token(
        db,
        event_id=event_id,
        school_id=str(school_id),
        issued_by_user_id=issued_by,
        event_table="events",
        ttl_minutes=payload.ttl_minutes,
        single_use=payload.single_use,
    )
    return QrTokenMintResponse(
        qr_token_id=row.id,
        event_id=event_id,
        event_table="events",
        raw_token=raw_token,
        expires_at=row.expires_at,
        single_use=bool(row.single_use),
    )


@router.get(
    "/{event_id}/qr-tokens",
    response_model=List[QrTokenListItem],
)
def list_qr_tokens(
    event_id: int,
    db: Session = Depends(get_db),
    actor: Dict[str, Any] = Depends(require_admin),
) -> List[QrToken]:
    """List minted tokens for an event (metadata only — never raw)."""
    school_id = actor.get("school_id")
    if not school_id:
        raise HTTPException(status_code=403, detail="school_id required")

    # Cross-tenant guard
    event = (
        db.query(Event)
        .filter(Event.id == event_id, Event.school_id == str(school_id))
        .first()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    return (
        db.query(QrToken)
        .filter(
            QrToken.event_table == "events",
            QrToken.event_id == event_id,
        )
        .order_by(QrToken.issued_at.desc())
        .all()
    )
