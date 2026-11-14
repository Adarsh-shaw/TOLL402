from typing import Any
from sqlalchemy.orm import Session

from backend.app.models.models import AuditLog, utc_now


class AuditService:
    """Append-only audit ledger service. Records are never updated or deleted."""

    @staticmethod
    def record_event(
        db: Session,
        *,
        trace_id: str,
        event_type: str,
        message: str,
        status: str = "info",
        agent_id: str | None = None,
        service_id: str | None = None,
        challenge_id: str | None = None,
        transaction_id: str | None = None,
        channel_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        commit: bool = False,
    ) -> AuditLog:
        entry = AuditLog(
            trace_id=trace_id,
            event_type=event_type,
            agent_id=agent_id,
            service_id=service_id,
            challenge_id=challenge_id,
            transaction_id=transaction_id,
            channel_id=channel_id,
            status=status,
            message=message,
            metadata_json=metadata or {},
            created_at=utc_now(),
        )
        db.add(entry)
        if commit:
            db.commit()
            db.refresh(entry)
        else:
            db.flush()
        return entry

    @staticmethod
    def list_logs(
        db: Session,
        *,
        trace_id: str | None = None,
        agent_id: str | None = None,
        event_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        q = db.query(AuditLog)
        if trace_id:
            q = q.filter(AuditLog.trace_id == trace_id)
        if agent_id:
            q = q.filter(AuditLog.agent_id == agent_id)
        if event_type:
            q = q.filter(AuditLog.event_type == event_type)
        if status:
            q = q.filter(AuditLog.status == status)
        return q.order_by(AuditLog.id.desc()).limit(limit).all()
