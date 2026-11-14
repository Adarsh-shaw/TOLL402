from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.models import Agent, ApiService, AuditLog, PaymentTransaction
from backend.app.schemas.schemas import AuditLogResponse, DemoRunRequest, DemoRunResponse
from backend.app.sdk.agent_client import TollRailAgentClient
from backend.app.services.payment_service import PaymentService

router = APIRouter(prefix="/api/demo", tags=["Interactive HTTP 402 Demo"])


@router.post("/run", response_model=DemoRunResponse)
def run_interactive_demo(req: DemoRunRequest, request: Request, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == req.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Selected agent not found")

    service = db.query(ApiService).filter(ApiService.id == req.service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Selected API service not found")

    client = TestClient(request.app, base_url="http://api.tollrail402.local")
    sdk = TollRailAgentClient(client)
    result = sdk.execute_paid_request(
        db=db,
        agent=agent,
        service=service,
        settlement_mode=req.settlement_mode,
        channel_id=req.channel_id,
        request_payload=req.payload,
    )

    trace_id = result["trace_id"]
    tx_resp = None
    payment_resp = result.get("payment_response")
    if payment_resp and payment_resp.get("transaction_id"):
        tx = db.query(PaymentTransaction).filter(PaymentTransaction.id == payment_resp["transaction_id"]).first()
        if tx:
            tx_resp = PaymentService.tx_to_response(db, tx)

    audits = (
        db.query(AuditLog)
        .filter(AuditLog.trace_id == trace_id)
        .order_by(AuditLog.id.asc())
        .all()
    )
    audit_responses = [
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
    ]

    return DemoRunResponse(
        trace_id=trace_id,
        success=result["success"],
        agent_id=agent.id,
        service_id=service.id,
        settlement_mode=result["settlement_mode"],
        execution_mode=result["execution_mode"],
        final_http_status=result["final_http_status"],
        steps=result["steps"],
        payment_transaction=tx_resp,
        api_response=result.get("api_response"),
        audit_events=audit_responses,
    )
