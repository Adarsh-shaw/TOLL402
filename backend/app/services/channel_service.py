import uuid
from sqlalchemy.orm import Session

from backend.app.blockchain.escrow_client import EscrowClient
from backend.app.blockchain.wallet_service import WalletService
from backend.app.models.models import Agent, ChannelVoucher, PaymentChannel, utc_now
from backend.app.schemas.schemas import (
    ChannelResponse,
    ChannelVoucherResponse,
    micro_to_usdc,
    usdc_to_micro,
)
from backend.app.services.agent_service import (
    AgentService,
    get_escrow_app_id,
    get_merchant_address,
    get_runtime_mode,
    get_usdc_asset_id,
)
from backend.app.services.audit_service import AuditService
from backend.app.services.verification_service import build_voucher_signing_dict


class ChannelService:
    """Manages voucher-based payment channels, escrow state, cumulative vouchers, batch settlement, and closure."""

    @staticmethod
    def create_channel(
        db: Session,
        agent: Agent,
        deposit_usdc: float,
        recipient_address: str | None = None,
    ) -> PaymentChannel:
        deposit_micro = usdc_to_micro(deposit_usdc)
        mode = get_runtime_mode(db)
        escrow_app_id = get_escrow_app_id(db)
        escrow = EscrowClient().inspect_escrow(escrow_app_id, mode)
        recipient = recipient_address or get_merchant_address(db)
        asset_id = get_usdc_asset_id(db)

        if mode == "local_demo":
            if agent.local_balance_micro_usdc < deposit_micro:
                raise ValueError(
                    f"Insufficient agent local USDC balance (${micro_to_usdc(agent.local_balance_micro_usdc):.6f}) for channel deposit ${deposit_usdc:.6f}"
                )
            agent.local_balance_micro_usdc -= deposit_micro
        elif not escrow.is_onchain_escrow:
            raise ValueError(
                "Algorand TestNet mode requires a deployed ESCROW_APP_ID to open an on-chain escrow channel. Switch to Local Demo Mode or deploy contracts/payment_escrow.py."
            )

        channel = PaymentChannel(
            id=f"chn_{uuid.uuid4().hex[:10]}",
            agent_id=agent.id,
            payer_address=agent.wallet_address,
            recipient_address=recipient,
            asset_id=asset_id,
            network=agent.network,
            escrow_app_id=escrow.escrow_app_id,
            escrow_address=escrow.escrow_address,
            is_onchain_escrow=escrow.is_onchain_escrow,
            deposited_micro_usdc=deposit_micro,
            cumulative_spent_micro=0,
            settled_micro_usdc=0,
            last_nonce=0,
            status="open",
        )
        db.add(channel)
        db.flush()

        AuditService.record_event(
            db,
            trace_id=f"trace_{channel.id}",
            event_type="CHANNEL_OPENED",
            agent_id=agent.id,
            channel_id=channel.id,
            status="success",
            message=f"Opened payment channel {channel.id} with ${deposit_usdc:.6f} USDC ({escrow.mode_label})",
            metadata={"escrow_app_id": escrow.escrow_app_id, "is_onchain_escrow": escrow.is_onchain_escrow},
        )
        db.commit()
        db.refresh(channel)
        return channel

    @staticmethod
    def deposit_funds(db: Session, channel: PaymentChannel, amount_usdc: float) -> PaymentChannel:
        if channel.status != "open":
            raise ValueError("Cannot deposit into a closed payment channel.")
        amount_micro = usdc_to_micro(amount_usdc)
        agent = db.query(Agent).filter(Agent.id == channel.agent_id).first()
        if not agent:
            raise ValueError("Channel agent not found.")

        mode = get_runtime_mode(db)
        if mode == "local_demo":
            if agent.local_balance_micro_usdc < amount_micro:
                raise ValueError("Insufficient agent local USDC balance for top-up deposit.")
            agent.local_balance_micro_usdc -= amount_micro

        channel.deposited_micro_usdc += amount_micro
        AuditService.record_event(
            db,
            trace_id=f"trace_{channel.id}",
            event_type="CHANNEL_DEPOSITED",
            agent_id=agent.id,
            channel_id=channel.id,
            status="success",
            message=f"Added ${amount_usdc:.6f} USDC to channel {channel.id}",
        )
        db.commit()
        db.refresh(channel)
        return channel

    @staticmethod
    def sign_next_voucher(
        db: Session,
        channel: PaymentChannel,
        agent: Agent,
        delta_micro_usdc: int,
    ) -> tuple[int, int, str]:
        """Signs a cumulative payment voucher using the agent's Ed25519 key."""
        if channel.status != "open":
            raise ValueError(f"Channel {channel.id} is {channel.status}")
        next_nonce = channel.last_nonce + 1
        cumulative = channel.cumulative_spent_micro + delta_micro_usdc
        if cumulative > channel.deposited_micro_usdc:
            raise ValueError(
                f"Channel {channel.id} deposit exhausted: needs {cumulative} microUSDC, deposited {channel.deposited_micro_usdc}"
            )
        sk = AgentService.get_decrypted_signing_key(agent)
        voucher_dict = build_voucher_signing_dict(
            channel_id=channel.id,
            nonce=next_nonce,
            cumulative_amount_micro=cumulative,
            payer_address=channel.payer_address,
            recipient_address=channel.recipient_address,
            asset_id=channel.asset_id,
            network=channel.network,
        )
        msg = WalletService.canonical_payment_message(voucher_dict)
        signature = WalletService.sign_message(sk, msg)
        return next_nonce, cumulative, signature

    @staticmethod
    def batch_settle(db: Session, channel: PaymentChannel) -> dict:
        if channel.status != "open":
            raise ValueError("Channel is already closed.")

        unsettled = (
            db.query(ChannelVoucher)
            .filter(ChannelVoucher.channel_id == channel.id, ChannelVoucher.settled == False)  # noqa: E712
            .order_by(ChannelVoucher.nonce.asc())
            .all()
        )
        if not unsettled:
            return {
                "channel_id": channel.id,
                "settled_vouchers": 0,
                "settled_amount_usdc": 0.0,
                "settlement_ref": None,
                "message": "No unsettled vouchers in channel.",
            }

        highest_voucher = unsettled[-1]
        newly_settled_micro = highest_voucher.cumulative_amount_micro - channel.settled_micro_usdc
        settlement_ref = f"batch_{uuid.uuid4().hex[:12]}"

        for v in unsettled:
            v.settled = True
            v.settlement_tx_id = settlement_ref

        channel.settled_micro_usdc = highest_voucher.cumulative_amount_micro

        AuditService.record_event(
            db,
            trace_id=f"trace_{channel.id}",
            event_type="CHANNEL_BATCH_SETTLED",
            agent_id=channel.agent_id,
            channel_id=channel.id,
            status="success",
            message=f"Batch settled {len(unsettled)} vouchers totaling ${micro_to_usdc(newly_settled_micro):.6f} USDC (cumulative ${micro_to_usdc(channel.settled_micro_usdc):.6f})",
            metadata={"settlement_ref": settlement_ref, "voucher_count": len(unsettled)},
        )
        db.commit()
        return {
            "channel_id": channel.id,
            "settled_vouchers": len(unsettled),
            "settled_amount_usdc": micro_to_usdc(newly_settled_micro),
            "settlement_ref": settlement_ref,
            "message": f"Batch settled {len(unsettled)} cumulative vouchers.",
        }

    @staticmethod
    def close_channel(db: Session, channel: PaymentChannel, reason: str = "User closed channel") -> PaymentChannel:
        if channel.status == "closed":
            return channel

        # Settle any pending vouchers first
        unsettled = (
            db.query(ChannelVoucher)
            .filter(ChannelVoucher.channel_id == channel.id, ChannelVoucher.settled == False)  # noqa: E712
            .all()
        )
        close_ref = f"close_{uuid.uuid4().hex[:12]}"
        for v in unsettled:
            v.settled = True
            v.settlement_tx_id = close_ref

        channel.settled_micro_usdc = channel.cumulative_spent_micro
        unspent_micro = max(0, channel.deposited_micro_usdc - channel.cumulative_spent_micro)

        # Return unspent local escrow funds back to agent local balance
        agent = db.query(Agent).filter(Agent.id == channel.agent_id).first()
        if agent and not channel.is_onchain_escrow:
            agent.local_balance_micro_usdc += unspent_micro

        channel.status = "closed"
        channel.close_tx_id = close_ref if channel.is_onchain_escrow else None
        channel.closed_at = utc_now()

        AuditService.record_event(
            db,
            trace_id=f"trace_{channel.id}",
            event_type="CHANNEL_CLOSED",
            agent_id=channel.agent_id,
            channel_id=channel.id,
            status="success",
            message=f"Closed channel {channel.id}. Settled ${micro_to_usdc(channel.settled_micro_usdc):.6f}, refunded ${micro_to_usdc(unspent_micro):.6f} USDC. Reason: {reason}",
        )
        db.commit()
        db.refresh(channel)
        return channel

    @staticmethod
    def to_response(db: Session, channel: PaymentChannel) -> ChannelResponse:
        agent = db.query(Agent).filter(Agent.id == channel.agent_id).first()
        vouchers = [
            ChannelVoucherResponse(
                id=v.id,
                channel_id=v.channel_id,
                nonce=v.nonce,
                cumulative_amount_micro=v.cumulative_amount_micro,
                cumulative_amount_usdc=micro_to_usdc(v.cumulative_amount_micro),
                delta_amount_micro=v.delta_amount_micro,
                delta_amount_usdc=micro_to_usdc(v.delta_amount_micro),
                signature=v.signature,
                challenge_id=v.challenge_id,
                settled=v.settled,
                settlement_tx_id=v.settlement_tx_id,
                created_at=v.created_at,
            )
            for v in channel.vouchers
        ]
        remaining = max(0, channel.deposited_micro_usdc - channel.cumulative_spent_micro)
        label = (
            f"Algorand TestNet Smart Contract Escrow (App {channel.escrow_app_id})"
            if channel.is_onchain_escrow
            else "Local Development Mode (off-chain Ed25519 vouchers)"
        )
        return ChannelResponse(
            id=channel.id,
            agent_id=channel.agent_id,
            agent_name=agent.name if agent else None,
            payer_address=channel.payer_address,
            recipient_address=channel.recipient_address,
            asset_id=channel.asset_id,
            network=channel.network,
            escrow_app_id=channel.escrow_app_id,
            escrow_address=channel.escrow_address,
            is_onchain_escrow=channel.is_onchain_escrow,
            escrow_mode_label=label,
            deposited_micro_usdc=channel.deposited_micro_usdc,
            deposited_usdc=micro_to_usdc(channel.deposited_micro_usdc),
            cumulative_spent_micro=channel.cumulative_spent_micro,
            cumulative_spent_usdc=micro_to_usdc(channel.cumulative_spent_micro),
            remaining_micro_usdc=remaining,
            remaining_usdc=micro_to_usdc(remaining),
            settled_micro_usdc=channel.settled_micro_usdc,
            settled_usdc=micro_to_usdc(channel.settled_micro_usdc),
            last_nonce=channel.last_nonce,
            status=channel.status,
            open_tx_id=channel.open_tx_id,
            close_tx_id=channel.close_tx_id,
            created_at=channel.created_at,
            closed_at=channel.closed_at,
            vouchers=vouchers,
        )
