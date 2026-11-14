from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


def micro_to_usdc(micro: int) -> float:
    return round(micro / 1_000_000, 6)


def usdc_to_micro(usdc: float) -> int:
    return int(round(usdc * 1_000_000))


# ---- HTTP 402 Protocol Header Schemas ----

class PaymentRequiredHeaderPayload(BaseModel):
    protocol_version: str = "x402/1.0"
    schemes: list[str] = ["exact", "channel"]
    network: str = "algorand:testnet"
    asset_id: int
    asset_symbol: str = "USDC"
    amount_micro_usdc: int
    amount_usdc: str
    recipient_address: str
    resource: str
    challenge_id: str
    nonce: str
    expires_at: str


class PaymentSignatureHeaderPayload(BaseModel):
    protocol_version: str = "x402/1.0"
    scheme: Literal["exact", "channel"] = "exact"
    network: str = "algorand:testnet"
    asset_id: int
    challenge_id: str
    nonce: str
    agent_id: str
    payer_address: str
    recipient_address: str
    amount_micro_usdc: int
    timestamp: str
    signature: str  # Base64 Ed25519 signature over canonical payload
    blockchain_tx_id: str | None = None
    channel_id: str | None = None
    voucher_nonce: int | None = None
    cumulative_amount_micro: int | None = None


class PaymentResponseHeaderPayload(BaseModel):
    success: bool
    payment_reference: str
    transaction_id: str | None = None
    voucher_id: str | None = None
    settlement_mode: str
    execution_mode: str
    is_simulated: bool
    amount_micro_usdc: int
    amount_usdc: str
    timestamp: str


# ---- Agent Schemas (NEVER include private keys or mnemonics) ----

class AgentCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=280)
    per_request_limit_usdc: float = Field(default=0.01, gt=0, le=1000)
    daily_limit_usdc: float = Field(default=5.0, gt=0, le=100000)
    allowed_hosts: list[str] = Field(default_factory=lambda: ["api.tollrail402.local", "localhost", "127.0.0.1"])
    initial_local_balance_usdc: float = Field(default=2.0, ge=0, le=10000)
    default_settlement_mode: Literal["exact", "channel"] = "exact"
    wallet_mode: Literal["generate", "import_address"] = "generate"
    imported_wallet_address: str | None = None
    imported_mnemonic: str | None = None  # Stored encrypted only if explicitly imported for demo signing; never returned


class AgentImportWalletRequest(BaseModel):
    wallet_address: str | None = None
    mnemonic: str | None = None


class AgentPolicyUpdateRequest(BaseModel):
    per_request_limit_usdc: float = Field(gt=0, le=1000)
    daily_limit_usdc: float = Field(gt=0, le=100000)
    allowed_hosts: list[str]
    default_settlement_mode: Literal["exact", "channel"] = "exact"

    @field_validator("allowed_hosts")
    @classmethod
    def validate_hosts(cls, v: list[str]) -> list[str]:
        cleaned = [h.strip().lower() for h in v if h and h.strip()]
        return cleaned


class AgentToggleRequest(BaseModel):
    is_active: bool


class AgentFundRequest(BaseModel):
    amount_usdc: float = Field(gt=0, le=10000)


class AgentResponse(BaseModel):
    id: str
    name: str
    description: str
    wallet_address: str
    has_managed_key: bool
    local_balance_micro_usdc: int
    local_balance_usdc: float
    live_testnet_usdc_micro: int | None = None
    live_testnet_usdc: float | None = None
    live_testnet_algo: float | None = None
    per_request_limit_micro: int
    per_request_limit_usdc: float
    daily_limit_micro: int
    daily_limit_usdc: float
    daily_spent_micro: int
    daily_spent_usdc: float
    daily_remaining_usdc: float
    allowed_hosts: list[str]
    default_settlement_mode: str
    is_active: bool
    network: str
    created_at: datetime


# ---- Marketplace Schemas ----

class ApiServiceResponse(BaseModel):
    id: str
    name: str
    category: str
    description: str
    endpoint: str
    method: str
    host: str
    price_micro_usdc: int
    price_usdc: float
    asset_id: int
    asset_symbol: str
    network: str
    provider_name: str
    recipient_address: str
    is_available: bool
    sample_payload: dict[str, Any]


# ---- Policy Schemas ----

class PolicyCheckRequest(BaseModel):
    agent_id: str
    service_id: str | None = None
    amount_usdc: float | None = Field(default=None, gt=0)
    target_host: str | None = None


class PolicyRuleResult(BaseModel):
    rule: str
    passed: bool
    detail: str


class PolicyCheckResponse(BaseModel):
    approved: bool
    agent_id: str
    reason: str
    requested_amount_usdc: float
    per_request_limit_usdc: float
    daily_limit_usdc: float
    daily_spent_usdc: float
    available_balance_usdc: float
    target_host: str
    checks: list[PolicyRuleResult]


# ---- Payment Transactions ----

class PaymentTransactionResponse(BaseModel):
    id: str
    challenge_id: str
    nonce: str
    agent_id: str
    agent_name: str | None = None
    service_id: str
    service_name: str | None = None
    endpoint: str
    payer_address: str
    recipient_address: str
    amount_micro_usdc: int
    amount_usdc: float
    asset_id: int
    network: str
    settlement_mode: str
    execution_mode: str
    is_simulated: bool
    blockchain_tx_id: str | None = None
    explorer_url: str | None = None
    local_receipt_ref: str | None = None
    voucher_id: str | None = None
    channel_id: str | None = None
    verification_status: str
    failure_reason: str | None = None
    verification_time_ms: float
    created_at: datetime


# ---- Payment Channels & Vouchers ----

class ChannelCreateRequest(BaseModel):
    agent_id: str
    recipient_address: str | None = None
    deposit_usdc: float = Field(gt=0, le=10000)


class ChannelDepositRequest(BaseModel):
    amount_usdc: float = Field(gt=0, le=10000)


class ChannelBatchSettleRequest(BaseModel):
    channel_id: str | None = None


class ChannelCloseRequest(BaseModel):
    reason: str = "Agent requested channel closure"


class ChannelVoucherResponse(BaseModel):
    id: str
    channel_id: str
    nonce: int
    cumulative_amount_micro: int
    cumulative_amount_usdc: float
    delta_amount_micro: int
    delta_amount_usdc: float
    signature: str
    challenge_id: str | None = None
    settled: bool
    settlement_tx_id: str | None = None
    created_at: datetime


class ChannelResponse(BaseModel):
    id: str
    agent_id: str
    agent_name: str | None = None
    payer_address: str
    recipient_address: str
    asset_id: int
    network: str
    escrow_app_id: int
    escrow_address: str
    is_onchain_escrow: bool
    escrow_mode_label: str
    deposited_micro_usdc: int
    deposited_usdc: float
    cumulative_spent_micro: int
    cumulative_spent_usdc: float
    remaining_micro_usdc: int
    remaining_usdc: float
    settled_micro_usdc: int
    settled_usdc: float
    last_nonce: int
    status: str
    open_tx_id: str | None = None
    close_tx_id: str | None = None
    created_at: datetime
    closed_at: datetime | None = None
    vouchers: list[ChannelVoucherResponse] = []


# ---- Audit Log ----

class AuditLogResponse(BaseModel):
    id: int
    trace_id: str
    event_type: str
    agent_id: str | None = None
    service_id: str | None = None
    challenge_id: str | None = None
    transaction_id: str | None = None
    channel_id: str | None = None
    status: str
    message: str
    metadata_json: dict[str, Any]
    created_at: datetime


# ---- Dashboard ----

class TopAgentSpend(BaseModel):
    agent_id: str
    agent_name: str
    initials: str
    total_spent_usdc: float
    tx_count: int


class DashboardOverviewResponse(BaseModel):
    total_requests: int
    successful_paid_requests: int
    failed_payment_attempts: int
    total_usdc_spent: float
    active_agents: int
    total_agents: int
    active_channels: int
    avg_verification_time_ms: float
    execution_mode: str
    algorand_network: str
    algorand_connected: bool
    algorand_last_round: int | None = None
    usdc_asset_id: int
    merchant_address: str = ""
    exact_vs_channel: dict[str, Any]
    channel_vouchers_count: int = 0
    activity_series: list[dict[str, Any]]
    top_agents: list[TopAgentSpend] = []
    recent_transactions: list[PaymentTransactionResponse]
    recent_audit_events: list[AuditLogResponse]


# ---- Interactive E2E Demo ----

class DemoRunRequest(BaseModel):
    agent_id: str
    service_id: str
    settlement_mode: Literal["exact", "channel"] | None = None
    channel_id: str | None = None
    payload: dict[str, Any] | None = None


class DemoStepTrace(BaseModel):
    step: int
    title: str
    status: str  # completed | failed | skipped
    timestamp: str
    http_status: int | None = None
    summary: str
    headers: dict[str, Any] | None = None
    body: dict[str, Any] | None = None


class DemoRunResponse(BaseModel):
    trace_id: str
    success: bool
    agent_id: str
    service_id: str
    settlement_mode: str
    execution_mode: str
    final_http_status: int
    steps: list[DemoStepTrace]
    payment_transaction: PaymentTransactionResponse | None = None
    api_response: dict[str, Any] | None = None
    audit_events: list[AuditLogResponse] = []


# ---- Settings ----

class SettingsResponse(BaseModel):
    tollrail_mode: Literal["local_demo", "algorand_testnet"]
    algorand_network: str
    algod_address: str
    indexer_address: str
    usdc_asset_id: int
    merchant_algorand_address: str
    escrow_app_id: int
    escrow_deployed: bool
    database_dialect: str
    algorand_node_status: dict[str, Any]


class SettingsUpdateRequest(BaseModel):
    tollrail_mode: Literal["local_demo", "algorand_testnet"] | None = None
    merchant_algorand_address: str | None = None
    escrow_app_id: int | None = Field(default=None, ge=0)
    usdc_asset_id: int | None = Field(default=None, gt=0)
