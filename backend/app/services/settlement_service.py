import uuid
from sqlalchemy.orm import Session

from backend.app.models.models import (
    ChannelVoucher,
    PaymentTransaction,
    utc_now,
)
from backend.app.services.agent_service import AgentService, get_runtime_mode
from backend.app.services.verification_service import VerificationResult


class SettlementService:
    """Atomically settles verified HTTP 402 payments in either Exact or Channel mode."""

    @staticmethod
    def settle_verified_payment(
        db: Session,
        verification: VerificationResult,
        service_id: str,
        endpoint: str,
        verification_time_ms: float,
    ) -> PaymentTransaction:
        payload = verification.payload
        challenge = verification.challenge
        agent = verification.agent
        assert payload and challenge and agent

        execution_mode = get_runtime_mode(db)
        AgentService.ensure_daily_reset(db, agent)

        tx_id = f"txr_{uuid.uuid4().hex[:12]}"
        voucher_id: str | None = None
        is_simulated = execution_mode != "algorand_testnet"
        blockchain_tx_id: str | None = payload.blockchain_tx_id if execution_mode == "algorand_testnet" else None
        local_receipt_ref: str | None = f"sim_{uuid.uuid4().hex[:10]}" if is_simulated else None

        if payload.scheme == "exact":
            if execution_mode == "local_demo":
                if agent.local_balance_micro_usdc < payload.amount_micro_usdc:
                    raise ValueError("Insufficient agent local USDC balance during atomic settlement.")
                agent.local_balance_micro_usdc -= payload.amount_micro_usdc
            agent.daily_spent_micro += payload.amount_micro_usdc

        elif payload.scheme == "channel":
            channel = verification.channel
            assert channel is not None and payload.voucher_nonce is not None and payload.cumulative_amount_micro is not None
            voucher_id = f"vch_{uuid.uuid4().hex[:10]}"
            delta_micro = payload.cumulative_amount_micro - channel.cumulative_spent_micro
            voucher = ChannelVoucher(
                id=voucher_id,
                channel_id=channel.id,
                nonce=payload.voucher_nonce,
                cumulative_amount_micro=payload.cumulative_amount_micro,
                delta_amount_micro=delta_micro,
                signature=payload.signature,
                challenge_id=challenge.challenge_id,
                settled=False,
            )
            db.add(voucher)
            channel.last_nonce = payload.voucher_nonce
            channel.cumulative_spent_micro = payload.cumulative_amount_micro
            agent.daily_spent_micro += delta_micro
            is_simulated = not channel.is_onchain_escrow
            local_receipt_ref = voucher_id

        challenge.status = "consumed"
        challenge.consumed_at = utc_now()

        tx_record = PaymentTransaction(
            id=tx_id,
            challenge_id=challenge.challenge_id,
            nonce=challenge.nonce,
            agent_id=agent.id,
            service_id=service_id,
            endpoint=endpoint,
            payer_address=payload.payer_address,
            recipient_address=payload.recipient_address,
            amount_micro_usdc=payload.amount_micro_usdc,
            asset_id=payload.asset_id,
            network=payload.network,
            settlement_mode=payload.scheme,
            execution_mode=execution_mode,
            is_simulated=is_simulated,
            blockchain_tx_id=blockchain_tx_id,
            local_receipt_ref=local_receipt_ref,
            voucher_id=voucher_id,
            channel_id=payload.channel_id,
            signature=payload.signature,
            verification_status="verified",
            failure_reason=None,
            verification_time_ms=round(verification_time_ms, 2),
            created_at=utc_now(),
        )
        db.add(tx_record)
        db.flush()
        return tx_record
