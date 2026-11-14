from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(280), default="", nullable=False)
    wallet_address: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Encrypted private key material (Fernet/AES). NEVER returned in API responses or logs.
    encrypted_key_material: Mapped[str | None] = mapped_column(Text, nullable=True)

    # All monetary balances stored in integer micro-USDC (1 USDC = 1,000,000 microUSDC)
    local_balance_micro_usdc: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    per_request_limit_micro: Mapped[int] = mapped_column(BigInteger, default=10_000, nullable=False)  # $0.01
    daily_limit_micro: Mapped[int] = mapped_column(BigInteger, default=5_000_000, nullable=False)   # $5.00
    daily_spent_micro: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    daily_reset_date: Mapped[str] = mapped_column(String(16), default="", nullable=False)

    allowed_hosts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    default_settlement_mode: Mapped[str] = mapped_column(String(16), default="exact", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    network: Mapped[str] = mapped_column(String(32), default="algorand:testnet", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    transactions: Mapped[list["PaymentTransaction"]] = relationship(back_populates="agent")
    channels: Mapped[list["PaymentChannel"]] = relationship(back_populates="agent")


class ApiService(Base):
    __tablename__ = "api_services"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    method: Mapped[str] = mapped_column(String(10), default="POST", nullable=False)
    host: Mapped[str] = mapped_column(String(120), default="api.tollrail402.local", nullable=False)
    price_micro_usdc: Mapped[int] = mapped_column(BigInteger, nullable=False)
    asset_id: Mapped[int] = mapped_column(BigInteger, default=10458941, nullable=False)
    asset_symbol: Mapped[str] = mapped_column(String(16), default="USDC", nullable=False)
    network: Mapped[str] = mapped_column(String(32), default="algorand:testnet", nullable=False)
    provider_name: Mapped[str] = mapped_column(String(120), nullable=False)
    recipient_address: Mapped[str] = mapped_column(String(64), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sample_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class PaymentChallenge(Base):
    __tablename__ = "payment_challenges"

    challenge_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    service_id: Mapped[str] = mapped_column(ForeignKey("api_services.id"), nullable=False)
    resource: Mapped[str] = mapped_column(String(160), nullable=False)
    amount_micro_usdc: Mapped[int] = mapped_column(BigInteger, nullable=False)
    asset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    network: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient_address: Mapped[str] = mapped_column(String(64), nullable=False)
    supported_schemes: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["exact", "channel"], nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)  # pending, consumed, expired, failed
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    challenge_id: Mapped[str] = mapped_column(ForeignKey("payment_challenges.challenge_id"), unique=True, nullable=False)
    nonce: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    service_id: Mapped[str] = mapped_column(ForeignKey("api_services.id"), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(160), nullable=False)
    payer_address: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_address: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_micro_usdc: Mapped[int] = mapped_column(BigInteger, nullable=False)
    asset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    network: Mapped[str] = mapped_column(String(32), nullable=False)
    settlement_mode: Mapped[str] = mapped_column(String(16), nullable=False)  # exact | channel
    execution_mode: Mapped[str] = mapped_column(String(24), nullable=False)   # local_demo | algorand_testnet
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    blockchain_tx_id: Mapped[str | None] = mapped_column(String(96), unique=True, nullable=True)
    local_receipt_ref: Mapped[str | None] = mapped_column(String(96), nullable=True)
    voucher_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(24), nullable=False)  # verified | failed
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_time_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    agent: Mapped["Agent"] = relationship(back_populates="transactions")


class PaymentChannel(Base):
    __tablename__ = "payment_channels"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    payer_address: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_address: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    network: Mapped[str] = mapped_column(String(32), default="algorand:testnet", nullable=False)
    escrow_app_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    escrow_address: Mapped[str] = mapped_column(String(96), nullable=False)
    is_onchain_escrow: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deposited_micro_usdc: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    cumulative_spent_micro: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    settled_micro_usdc: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_nonce: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)  # open | closed
    open_tx_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    close_tx_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    agent: Mapped["Agent"] = relationship(back_populates="channels")
    vouchers: Mapped[list["ChannelVoucher"]] = relationship(back_populates="channel", order_by="ChannelVoucher.nonce")


class ChannelVoucher(Base):
    __tablename__ = "channel_vouchers"
    __table_args__ = (
        UniqueConstraint("channel_id", "nonce", name="uq_channel_voucher_nonce"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("payment_channels.id"), nullable=False, index=True)
    nonce: Mapped[int] = mapped_column(Integer, nullable=False)
    cumulative_amount_micro: Mapped[int] = mapped_column(BigInteger, nullable=False)
    delta_amount_micro: Mapped[int] = mapped_column(BigInteger, nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    challenge_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    settled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    settlement_tx_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    channel: Mapped["PaymentChannel"] = relationship(back_populates="vouchers")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    service_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    challenge_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="info", nullable=False)  # info | success | warning | error
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
