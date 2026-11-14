from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.blockchain.algorand_client import AlgorandClient
from backend.app.blockchain.wallet_service import WalletService
from backend.app.config import get_settings
from backend.app.database import engine, get_db
from backend.app.models.models import ApiService, PlatformSetting, utc_now
from backend.app.schemas.schemas import SettingsResponse, SettingsUpdateRequest
from backend.app.services.agent_service import (
    get_escrow_app_id,
    get_merchant_address,
    get_runtime_mode,
    get_usdc_asset_id,
)
from backend.app.services.audit_service import AuditService

router = APIRouter(prefix="/api/settings", tags=["Settings"])


@router.get("", response_model=SettingsResponse)
def get_platform_settings(db: Session = Depends(get_db)):
    cfg = get_settings()
    mode = get_runtime_mode(db)
    merchant_addr = get_merchant_address(db)
    escrow_app_id = get_escrow_app_id(db)
    usdc_asset_id = get_usdc_asset_id(db)
    node_status = AlgorandClient().get_network_status()

    return SettingsResponse(
        tollrail_mode=mode,  # type: ignore[arg-type]
        algorand_network=cfg.algorand_network,
        algod_address=cfg.algod_address,
        indexer_address=cfg.indexer_address,
        usdc_asset_id=usdc_asset_id,
        merchant_algorand_address=merchant_addr,
        escrow_app_id=escrow_app_id,
        escrow_deployed=escrow_app_id > 0,
        database_dialect=engine.dialect.name,
        algorand_node_status=node_status,
    )


@router.patch("", response_model=SettingsResponse)
def update_platform_settings(req: SettingsUpdateRequest, db: Session = Depends(get_db)):
    if req.tollrail_mode is not None:
        db.merge(PlatformSetting(key="tollrail_mode", value=req.tollrail_mode, updated_at=utc_now()))

    if req.merchant_algorand_address is not None:
        addr = req.merchant_algorand_address.strip()
        if not WalletService.is_valid_address(addr):
            raise HTTPException(status_code=400, detail="Invalid Algorand merchant address")
        db.merge(PlatformSetting(key="merchant_algorand_address", value=addr, updated_at=utc_now()))
        # Propagate updated recipient address to marketplace services
        for svc in db.query(ApiService).all():
            svc.recipient_address = addr

    if req.escrow_app_id is not None:
        db.merge(PlatformSetting(key="escrow_app_id", value=str(req.escrow_app_id), updated_at=utc_now()))

    if req.usdc_asset_id is not None:
        db.merge(PlatformSetting(key="usdc_asset_id", value=str(req.usdc_asset_id), updated_at=utc_now()))
        for svc in db.query(ApiService).all():
            svc.asset_id = req.usdc_asset_id

    AuditService.record_event(
        db,
        trace_id="trace_settings",
        event_type="SETTINGS_UPDATED",
        status="info",
        message=f"Platform settings updated (mode={req.tollrail_mode or get_runtime_mode(db)})",
    )
    db.commit()
    return get_platform_settings(db)
