from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.schemas.schemas import AuditLogResponse
from backend.app.services.audit_service import AuditService

router = APIRouter(prefix="/api/audit", tags=["Audit Ledger"])


@router.get("", response_model=list[AuditLogResponse])
def list_audit_logs(
    trace_id: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
    db: Session = Depends(get_db),
):
    logs = AuditService.list_logs(
        db,
        trace_id=trace_id,
        agent_id=agent_id,
        event_type=event_type,
        status=status,
        limit=limit,
    )
    return [
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
        for a in logs
    ]
