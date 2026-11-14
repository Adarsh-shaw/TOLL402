from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.blockchain.algorand_client import AlgorandClient
from backend.app.database import get_db
from backend.app.models.models import (
    Agent,
    AuditLog,
    ChannelVoucher,
    PaymentChannel,
    PaymentTransaction,
)
from backend.app.schemas.schemas import (
    AuditLogResponse,
    DashboardOverviewResponse,
    TopAgentSpend,
    micro_to_usdc,
)
from backend.app.services.agent_service import (
    get_merchant_address,
    get_runtime_mode,
    get_usdc_asset_id,
)
from backend.app.services.payment_service import PaymentService

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


def _initials(name: str) -> str:
    parts = [p for p in name.strip().split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return (name[:2] if name else "AG").upper()


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(
    days: int = Query(default=7, ge=0, le=365),
    db: Session = Depends(get_db),
):
    mode = get_runtime_mode(db)
    usdc_asset_id = get_usdc_asset_id(db)
    merchant_addr = get_merchant_address(db)

    tx_q = db.query(PaymentTransaction)
    audit_reject_q = db.query(func.count(AuditLog.id)).filter(AuditLog.event_type == "POLICY_REJECTED")

    if days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        tx_q = tx_q.filter(PaymentTransaction.created_at >= cutoff)
        audit_reject_q = audit_reject_q.filter(AuditLog.created_at >= cutoff)

    all_txs = tx_q.order_by(PaymentTransaction.created_at.desc()).all()
    verified_txs = [t for t in all_txs if t.verification_status == "verified"]
    failed_txs = [t for t in all_txs if t.verification_status == "failed"]
    policy_rejections = audit_reject_q.scalar() or 0

    total_spent_micro = sum(t.amount_micro_usdc for t in verified_txs)
    avg_verif_ms = (
        round(sum(t.verification_time_ms for t in all_txs) / len(all_txs), 2)
        if all_txs
        else 0.0
    )

    total_agents = db.query(func.count(Agent.id)).scalar() or 0
    active_agents = db.query(func.count(Agent.id)).filter(Agent.is_active == True).scalar() or 0  # noqa: E712
    active_channels = db.query(func.count(PaymentChannel.id)).filter(PaymentChannel.status == "open").scalar() or 0
    channel_vouchers_count = db.query(func.count(ChannelVoucher.id)).scalar() or 0

    exact_txs = [t for t in verified_txs if t.settlement_mode == "exact"]
    channel_txs = [t for t in verified_txs if t.settlement_mode == "channel"]

    exact_vs_channel = {
        "exact_count": len(exact_txs),
        "exact_usdc": micro_to_usdc(sum(t.amount_micro_usdc for t in exact_txs)),
        "channel_count": len(channel_txs),
        "channel_usdc": micro_to_usdc(sum(t.amount_micro_usdc for t in channel_txs)),
    }

    # Build chronological activity buckets (supports line chart: successful vs failed + volume)
    buckets: dict[str, dict] = defaultdict(
        lambda: {
            "label": "",
            "successful": 0,
            "failed": 0,
            "exact_usdc": 0.0,
            "channel_usdc": 0.0,
            "requests": 0,
        }
    )
    for t in reversed(all_txs):
        dt = t.created_at
        label = dt.strftime("%b %d %H:%M") if dt else "unknown"
        b = buckets[label]
        b["label"] = label
        b["requests"] += 1
        if t.verification_status == "verified":
            b["successful"] += 1
            amt = micro_to_usdc(t.amount_micro_usdc)
            if t.settlement_mode == "channel":
                b["channel_usdc"] = round(b["channel_usdc"] + amt, 6)
            else:
                b["exact_usdc"] = round(b["exact_usdc"] + amt, 6)
        else:
            b["failed"] += 1

    activity_series = list(buckets.values())[-14:]

    # Top agents by spending from real verified transactions
    agent_spend_micro: dict[str, int] = defaultdict(int)
    agent_tx_count: dict[str, int] = defaultdict(int)
    for t in verified_txs:
        agent_spend_micro[t.agent_id] += t.amount_micro_usdc
        agent_tx_count[t.agent_id] += 1

    all_agents = {a.id: a for a in db.query(Agent).all()}
    top_agents_list: list[TopAgentSpend] = []
    for ag_id, ag in all_agents.items():
        spent_m = agent_spend_micro.get(ag_id, 0)
        top_agents_list.append(
            TopAgentSpend(
                agent_id=ag_id,
                agent_name=ag.name,
                initials=_initials(ag.name),
                total_spent_usdc=micro_to_usdc(spent_m),
                tx_count=agent_tx_count.get(ag_id, 0),
            )
        )
    top_agents_list.sort(key=lambda x: (-x.total_spent_usdc, -x.tx_count, x.agent_name))

    recent_tx_responses = [PaymentService.tx_to_response(db, t) for t in all_txs[:10]]
    recent_audits = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(12).all()
    recent_audit_responses = [
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
        for a in recent_audits
    ]

    algo_status = AlgorandClient().get_network_status()

    return DashboardOverviewResponse(
        total_requests=len(all_txs) + policy_rejections,
        successful_paid_requests=len(verified_txs),
        failed_payment_attempts=len(failed_txs) + policy_rejections,
        total_usdc_spent=micro_to_usdc(total_spent_micro),
        active_agents=active_agents,
        total_agents=total_agents,
        active_channels=active_channels,
        avg_verification_time_ms=avg_verif_ms,
        execution_mode=mode,
        algorand_network=algo_status.get("network", "algorand:testnet"),
        algorand_connected=bool(algo_status.get("connected")),
        algorand_last_round=algo_status.get("last_round"),
        usdc_asset_id=usdc_asset_id,
        merchant_address=merchant_addr,
        exact_vs_channel=exact_vs_channel,
        channel_vouchers_count=channel_vouchers_count,
        activity_series=activity_series,
        top_agents=top_agents_list[:5],
        recent_transactions=recent_tx_responses,
        recent_audit_events=recent_audit_responses,
    )
