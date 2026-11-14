from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.models import Agent, ApiService
from backend.app.schemas.schemas import PolicyCheckRequest, PolicyCheckResponse, usdc_to_micro
from backend.app.services.policy_engine import PolicyEngine

router = APIRouter(prefix="/api/policies", tags=["Spending Policies"])


@router.post("/evaluate", response_model=PolicyCheckResponse)
def evaluate_spending_policy(req: PolicyCheckRequest, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == req.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    target_host = req.target_host or "api.tollrail402.local"
    amount_micro = usdc_to_micro(req.amount_usdc) if req.amount_usdc is not None else 5000

    if req.service_id:
        svc = db.query(ApiService).filter(ApiService.id == req.service_id).first()
        if not svc:
            raise HTTPException(status_code=404, detail="API service not found")
        amount_micro = svc.price_micro_usdc
        target_host = svc.host

    return PolicyEngine.evaluate(
        db=db,
        agent=agent,
        amount_micro_usdc=amount_micro,
        target_host=target_host,
        settlement_mode=agent.default_settlement_mode,
    )
