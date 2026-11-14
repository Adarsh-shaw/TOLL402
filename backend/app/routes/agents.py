from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.blockchain.algorand_client import AlgorandClient
from backend.app.database import get_db
from backend.app.models.models import Agent, AuditLog, PaymentTransaction
from backend.app.schemas.schemas import (
    AgentCreateRequest,
    AgentFundRequest,
    AgentImportWalletRequest,
    AgentPolicyUpdateRequest,
    AgentResponse,
    AgentToggleRequest,
    AuditLogResponse,
)
from backend.app.services.agent_service import AgentService, get_runtime_mode, get_usdc_asset_id
from backend.app.services.audit_service import AuditService
from backend.app.services.payment_service import PaymentService

router = APIRouter(prefix="/api/agents", tags=["Agents"])


@router.get("", response_model=list[AgentResponse])
def list_agents(fetch_testnet: bool = Query(default=False), db: Session = Depends(get_db)):
    agents = db.query(Agent).order_by(Agent.created_at.desc()).all()
    return [AgentService.to_response(db, a, fetch_testnet=fetch_testnet) for a in agents]


@router.post("", response_model=AgentResponse, status_code=201)
def create_agent(req: AgentCreateRequest, db: Session = Depends(get_db)):
    try:
        agent = AgentService.create_agent(db, req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    AuditService.record_event(
        db,
        trace_id=f"trace_{agent.id}",
        event_type="AGENT_REGISTERED",
        agent_id=agent.id,
        status="success",
        message=f"Registered agent '{agent.name}' with Algorand wallet {agent.wallet_address}",
        commit=True,
    )
    return AgentService.to_response(db, agent)


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: str, fetch_testnet: bool = Query(default=True), db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentService.to_response(db, agent, fetch_testnet=fetch_testnet)


@router.get("/{agent_id}/balance")
def get_agent_balance(agent_id: str, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    client = AlgorandClient()
    asset_id = get_usdc_asset_id(db)
    testnet_bal = client.get_account_balances(agent.wallet_address, asset_id)
    mode = get_runtime_mode(db)

    return {
        "agent_id": agent.id,
        "wallet_address": agent.wallet_address,
        "execution_mode": mode,
        "local_demo_balance_usdc": round(agent.local_balance_micro_usdc / 1_000_000, 6),
        "testnet": testnet_bal,
        "explorer_url": client.get_explorer_address_url(agent.wallet_address),
    }


@router.post("/{agent_id}/wallet", response_model=AgentResponse)
def update_agent_wallet(agent_id: str, req: AgentImportWalletRequest, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        updated = AgentService.import_or_rotate_wallet(db, agent, req)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid wallet import parameters: {exc}")

    AuditService.record_event(
        db,
        trace_id=f"trace_{agent.id}",
        event_type="AGENT_WALLET_UPDATED",
        agent_id=agent.id,
        status="info",
        message=f"Updated wallet address for agent '{agent.name}' to {updated.wallet_address}",
        commit=True,
    )
    return AgentService.to_response(db, updated)


@router.patch("/{agent_id}/policy", response_model=AgentResponse)
def update_agent_policy(agent_id: str, req: AgentPolicyUpdateRequest, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    updated = AgentService.update_policy(db, agent, req)
    AuditService.record_event(
        db,
        trace_id=f"trace_{agent.id}",
        event_type="POLICY_UPDATED",
        agent_id=agent.id,
        status="info",
        message=f"Updated spending policy for {agent.name}: max ${req.per_request_limit_usdc:.4f}/req, ${req.daily_limit_usdc:.2f}/day",
        commit=True,
    )
    return AgentService.to_response(db, updated)


@router.patch("/{agent_id}/status", response_model=AgentResponse)
def toggle_agent_status(agent_id: str, req: AgentToggleRequest, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    updated = AgentService.toggle_active(db, agent, req.is_active)
    AuditService.record_event(
        db,
        trace_id=f"trace_{agent.id}",
        event_type="AGENT_STATUS_CHANGED",
        agent_id=agent.id,
        status="info",
        message=f"Agent '{agent.name}' {'activated' if req.is_active else 'deactivated'}",
        commit=True,
    )
    return AgentService.to_response(db, updated)


@router.post("/{agent_id}/fund", response_model=AgentResponse)
def fund_local_demo_balance(agent_id: str, req: AgentFundRequest, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    updated = AgentService.fund_local_balance(db, agent, req.amount_usdc)
    AuditService.record_event(
        db,
        trace_id=f"trace_{agent.id}",
        event_type="LOCAL_DEMO_FUNDED",
        agent_id=agent.id,
        status="info",
        message=f"Credited ${req.amount_usdc:.4f} local demo USDC to {agent.name} (Local Demo Mode ledger)",
        commit=True,
    )
    return AgentService.to_response(db, updated)


@router.get("/{agent_id}/activity")
def get_agent_activity(agent_id: str, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    txs = (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.agent_id == agent_id)
        .order_by(PaymentTransaction.created_at.desc())
        .limit(50)
        .all()
    )
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.agent_id == agent_id)
        .order_by(AuditLog.id.desc())
        .limit(50)
        .all()
    )
    return {
        "agent": AgentService.to_response(db, agent),
        "transactions": [PaymentService.tx_to_response(db, t) for t in txs],
        "audit_logs": [
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
        ],
    }
