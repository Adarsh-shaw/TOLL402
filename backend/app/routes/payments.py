from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.models import AuditLog, PaymentTransaction
from backend.app.schemas.schemas import AuditLogResponse, PaymentTransactionResponse
from backend.app.services.payment_service import PaymentService

router = APIRouter(prefix="/api/payments", tags=["Payments Explorer"])


@router.get("", response_model=list[PaymentTransactionResponse])
def list_transactions(
    agent_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    settlement_mode: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(PaymentTransaction)
    if agent_id:
        q = q.filter(PaymentTransaction.agent_id == agent_id)
    if status:
        q = q.filter(PaymentTransaction.verification_status == status)
    if settlement_mode:
        q = q.filter(PaymentTransaction.settlement_mode == settlement_mode)
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            q = q.filter(PaymentTransaction.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            q = q.filter(PaymentTransaction.created_at <= dt_to)
        except ValueError:
            pass

    txs = q.order_by(PaymentTransaction.created_at.desc()).limit(limit).all()
    results = [PaymentService.tx_to_response(db, t) for t in txs]

    if search and search.strip():
        needle = search.strip().lower()
        results = [
            r
            for r in results
            if needle in r.id.lower()
            or needle in (r.blockchain_tx_id or "").lower()
            or needle in (r.local_receipt_ref or "").lower()
            or needle in r.payer_address.lower()
            or needle in r.recipient_address.lower()
            or needle in r.endpoint.lower()
        ]
    return results


@router.get("/{tx_id}")
def get_transaction_detail(tx_id: str, db: Session = Depends(get_db)):
    tx = db.query(PaymentTransaction).filter(PaymentTransaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    audits = (
        db.query(AuditLog)
        .filter(
            (AuditLog.transaction_id == tx.id) | (AuditLog.challenge_id == tx.challenge_id)
        )
        .order_by(AuditLog.id.asc())
        .all()
    )

    return {
        "transaction": PaymentService.tx_to_response(db, tx),
        "audit_timeline": [
            AuditLogResponse(
                id=a.id,
                trace_id=a.trace_id,
                event_type=a.event_type,
                agent_id=a.agent_id,
                service_id=a.service_id,
                challenge_id=a.challenge_id,
                transaction_id=a.transaction_id,
                channel_id=a.channel_id,
                status=a.status,
                message=a.message,
                metadata_json=a.metadata_json,
                created_at=a.created_at,
            )
            for a in audits
        ],
    }
