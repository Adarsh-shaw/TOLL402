from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.blockchain.escrow_client import EscrowClient
from backend.app.database import get_db
from backend.app.models.models import Agent, PaymentChannel
from backend.app.schemas.schemas import (
    ChannelCloseRequest,
    ChannelCreateRequest,
    ChannelDepositRequest,
    ChannelResponse,
)
from backend.app.services.agent_service import get_escrow_app_id, get_runtime_mode
from backend.app.services.channel_service import ChannelService

router = APIRouter(prefix="/api/channels", tags=["Payment Channels"])


@router.get("/escrow-status")
def get_escrow_status(db: Session = Depends(get_db)):
    mode = get_runtime_mode(db)
    app_id = get_escrow_app_id(db)
    status = EscrowClient().inspect_escrow(app_id, mode)
    return {
        "execution_mode": mode,
        "escrow_app_id": status.escrow_app_id,
        "escrow_address": status.escrow_address,
        "is_onchain_escrow": status.is_onchain_escrow,
        "mode_label": status.mode_label,
        "details": status.details,
    }


@router.get("", response_model=list[ChannelResponse])
def list_channels(agent_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(PaymentChannel)
    if agent_id:
        q = q.filter(PaymentChannel.agent_id == agent_id)
    channels = q.order_by(PaymentChannel.created_at.desc()).all()
    return [ChannelService.to_response(db, c) for c in channels]


@router.post("", response_model=ChannelResponse, status_code=201)
def create_channel(req: ChannelCreateRequest, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == req.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        channel = ChannelService.create_channel(
            db=db,
            agent=agent,
            deposit_usdc=req.deposit_usdc,
            recipient_address=req.recipient_address,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ChannelService.to_response(db, channel)


@router.post("/{channel_id}/deposit", response_model=ChannelResponse)
def deposit_to_channel(channel_id: str, req: ChannelDepositRequest, db: Session = Depends(get_db)):
    channel = db.query(PaymentChannel).filter(PaymentChannel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Payment channel not found")
    try:
        updated = ChannelService.deposit_funds(db, channel, req.amount_usdc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ChannelService.to_response(db, updated)


@router.post("/{channel_id}/batch-settle")
def batch_settle_channel(channel_id: str, db: Session = Depends(get_db)):
    channel = db.query(PaymentChannel).filter(PaymentChannel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Payment channel not found")
    try:
        return ChannelService.batch_settle(db, channel)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{channel_id}/close", response_model=ChannelResponse)
def close_channel(channel_id: str, req: ChannelCloseRequest, db: Session = Depends(get_db)):
    channel = db.query(PaymentChannel).filter(PaymentChannel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Payment channel not found")
    updated = ChannelService.close_channel(db, channel, reason=req.reason)
    return ChannelService.to_response(db, updated)
