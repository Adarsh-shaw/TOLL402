import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.app.blockchain.algorand_client import AlgorandClient
from backend.app.blockchain.wallet_service import WalletService
from backend.app.config import get_settings
from backend.app.models.models import Agent, PlatformSetting
from backend.app.schemas.schemas import (
    AgentCreateRequest,
    AgentImportWalletRequest,
    AgentPolicyUpdateRequest,
    AgentResponse,
    micro_to_usdc,
    usdc_to_micro,
)


def get_runtime_mode(db: Session) -> str:
    row = db.query(PlatformSetting).filter(PlatformSetting.key == "tollrail_mode").first()
    if row and row.value in ("local_demo", "algorand_testnet"):
        return row.value
    return get_settings().tollrail_mode


def get_merchant_address(db: Session) -> str:
    row = db.query(PlatformSetting).filter(PlatformSetting.key == "merchant_algorand_address").first()
    if row and WalletService.is_valid_address(row.value):
        return row.value
    cfg_addr = get_settings().merchant_algorand_address
    if cfg_addr and WalletService.is_valid_address(cfg_addr):
        return cfg_addr
    # Generate and persist a valid Algorand TestNet recipient address for the demo provider
    _, addr = WalletService.generate_wallet()
    setting = PlatformSetting(key="merchant_algorand_address", value=addr)
    db.merge(setting)
    db.commit()
    return addr


def get_escrow_app_id(db: Session) -> int:
    row = db.query(PlatformSetting).filter(PlatformSetting.key == "escrow_app_id").first()
    if row:
        try:
            return int(row.value)
        except ValueError:
            pass
    return get_settings().escrow_app_id


def get_usdc_asset_id(db: Session) -> int:
    row = db.query(PlatformSetting).filter(PlatformSetting.key == "usdc_asset_id").first()
    if row:
        try:
            return int(row.value)
        except ValueError:
            pass
    return get_settings().usdc_asset_id


class AgentService:
    """Manages autonomous payment agents, encrypted wallet keys, balances, and policies."""

    @staticmethod
    def ensure_daily_reset(db: Session, agent: Agent) -> None:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if agent.daily_reset_date != today_str:
            agent.daily_spent_micro = 0
            agent.daily_reset_date = today_str
            db.flush()

    @staticmethod
    def create_agent(db: Session, req: AgentCreateRequest) -> Agent:
        agent_id = f"agt_{uuid.uuid4().hex[:10]}"
        encrypted_key: str | None = None

        if req.wallet_mode == "import_address":
            if req.imported_mnemonic and req.imported_mnemonic.strip():
                sk, wallet_address = WalletService.import_from_mnemonic(req.imported_mnemonic)
                encrypted_key = WalletService.encrypt_private_key(sk)
            elif req.imported_wallet_address and WalletService.is_valid_address(req.imported_wallet_address):
                wallet_address = req.imported_wallet_address.strip()
            else:
                raise ValueError("Provide a valid Algorand wallet address or 25-word mnemonic to import.")
        else:
            sk, wallet_address = WalletService.generate_wallet()
            encrypted_key = WalletService.encrypt_private_key(sk)

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        agent = Agent(
            id=agent_id,
            name=req.name.strip(),
            description=req.description.strip(),
            wallet_address=wallet_address,
            encrypted_key_material=encrypted_key,
            local_balance_micro_usdc=usdc_to_micro(req.initial_local_balance_usdc),
            per_request_limit_micro=usdc_to_micro(req.per_request_limit_usdc),
            daily_limit_micro=usdc_to_micro(req.daily_limit_usdc),
            daily_spent_micro=0,
            daily_reset_date=today_str,
            allowed_hosts=[h.strip().lower() for h in req.allowed_hosts if h.strip()],
            default_settlement_mode=req.default_settlement_mode,
            is_active=True,
            network=get_settings().algorand_network,
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
        return agent

    @staticmethod
    def import_or_rotate_wallet(db: Session, agent: Agent, req: AgentImportWalletRequest) -> Agent:
        if req.mnemonic and req.mnemonic.strip():
            sk, addr = WalletService.import_from_mnemonic(req.mnemonic)
            agent.wallet_address = addr
            agent.encrypted_key_material = WalletService.encrypt_private_key(sk)
        elif req.wallet_address and WalletService.is_valid_address(req.wallet_address):
            agent.wallet_address = req.wallet_address.strip()
            agent.encrypted_key_material = None
        else:
            sk, addr = WalletService.generate_wallet()
            agent.wallet_address = addr
            agent.encrypted_key_material = WalletService.encrypt_private_key(sk)

        db.commit()
        db.refresh(agent)
        return agent

    @staticmethod
    def update_policy(db: Session, agent: Agent, req: AgentPolicyUpdateRequest) -> Agent:
        agent.per_request_limit_micro = usdc_to_micro(req.per_request_limit_usdc)
        agent.daily_limit_micro = usdc_to_micro(req.daily_limit_usdc)
        agent.allowed_hosts = req.allowed_hosts
        agent.default_settlement_mode = req.default_settlement_mode
        db.commit()
        db.refresh(agent)
        return agent

    @staticmethod
    def toggle_active(db: Session, agent: Agent, is_active: bool) -> Agent:
        agent.is_active = is_active
        db.commit()
        db.refresh(agent)
        return agent

    @staticmethod
    def fund_local_balance(db: Session, agent: Agent, amount_usdc: float) -> Agent:
        agent.local_balance_micro_usdc += usdc_to_micro(amount_usdc)
        db.commit()
        db.refresh(agent)
        return agent

    @staticmethod
    def get_decrypted_signing_key(agent: Agent) -> str:
        if not agent.encrypted_key_material:
            raise ValueError(f"Agent {agent.id} is watch-only and does not hold an encrypted signing key.")
        return WalletService.decrypt_private_key(agent.encrypted_key_material)

    @staticmethod
    def to_response(db: Session, agent: Agent, fetch_testnet: bool = False) -> AgentResponse:
        AgentService.ensure_daily_reset(db, agent)
        live_usdc_micro = None
        live_usdc = None
        live_algo = None
        if fetch_testnet:
            client = AlgorandClient()
            asset_id = get_usdc_asset_id(db)
            bal = client.get_account_balances(agent.wallet_address, asset_id)
            if bal.get("success"):
                live_usdc_micro = bal["usdc_micro"]
                live_usdc = bal["usdc"]
                live_algo = bal["algo"]

        daily_remaining_micro = max(0, agent.daily_limit_micro - agent.daily_spent_micro)
        return AgentResponse(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            wallet_address=agent.wallet_address,
            has_managed_key=bool(agent.encrypted_key_material),
            local_balance_micro_usdc=agent.local_balance_micro_usdc,
            local_balance_usdc=micro_to_usdc(agent.local_balance_micro_usdc),
            live_testnet_usdc_micro=live_usdc_micro,
            live_testnet_usdc=live_usdc,
            live_testnet_algo=live_algo,
            per_request_limit_micro=agent.per_request_limit_micro,
            per_request_limit_usdc=micro_to_usdc(agent.per_request_limit_micro),
            daily_limit_micro=agent.daily_limit_micro,
            daily_limit_usdc=micro_to_usdc(agent.daily_limit_micro),
            daily_spent_micro=agent.daily_spent_micro,
            daily_spent_usdc=micro_to_usdc(agent.daily_spent_micro),
            daily_remaining_usdc=micro_to_usdc(daily_remaining_micro),
            allowed_hosts=list(agent.allowed_hosts or []),
            default_settlement_mode=agent.default_settlement_mode,
            is_active=agent.is_active,
            network=agent.network,
            created_at=agent.created_at,
        )
