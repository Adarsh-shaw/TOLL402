import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.app.blockchain.transaction_verifier import TransactionVerifier
from backend.app.blockchain.wallet_service import WalletService
from backend.app.config import get_settings
from backend.app.models.models import (
    Agent,
    ChannelVoucher,
    PaymentChallenge,
    PaymentChannel,
    PaymentTransaction,
)
from backend.app.schemas.schemas import PaymentSignatureHeaderPayload
from backend.app.services.agent_service import get_runtime_mode


@dataclass
class VerificationResult:
    valid: bool
    reason: str
    payload: PaymentSignatureHeaderPayload | None = None
    challenge: PaymentChallenge | None = None
    agent: Agent | None = None
    channel: PaymentChannel | None = None
    confirmed_round: int | None = None


def parse_payment_signature_header(header_value: str) -> PaymentSignatureHeaderPayload:
    raw = header_value.strip()
    if raw.startswith("{"):
        data = json.loads(raw)
    else:
        # Support Base64-encoded JSON header as standard in x402
        decoded = base64.b64decode(raw).decode("utf-8")
        data = json.loads(decoded)
    return PaymentSignatureHeaderPayload(**data)


def build_exact_signing_dict(
    *,
    protocol_version: str,
    scheme: str,
    network: str,
    asset_id: int,
    challenge_id: str,
    nonce: str,
    agent_id: str,
    payer_address: str,
    recipient_address: str,
    amount_micro_usdc: int,
    timestamp: str,
    blockchain_tx_id: str | None = None,
) -> dict:
    return {
        "protocol_version": protocol_version,
        "scheme": scheme,
        "network": network,
        "asset_id": asset_id,
        "challenge_id": challenge_id,
        "nonce": nonce,
        "agent_id": agent_id,
        "payer_address": payer_address,
        "recipient_address": recipient_address,
        "amount_micro_usdc": amount_micro_usdc,
        "timestamp": timestamp,
        "blockchain_tx_id": blockchain_tx_id or "",
    }


def build_voucher_signing_dict(
    *,
    channel_id: str,
    nonce: int,
    cumulative_amount_micro: int,
    payer_address: str,
    recipient_address: str,
    asset_id: int,
    network: str,
) -> dict:
    return {
        "type": "tollrail402_channel_voucher",
        "channel_id": channel_id,
        "nonce": nonce,
        "cumulative_amount_micro": cumulative_amount_micro,
        "payer_address": payer_address,
        "recipient_address": recipient_address,
        "asset_id": asset_id,
        "network": network,
    }


class VerificationService:
    """Verifies HTTP 402 PAYMENT-SIGNATURE payloads, Ed25519 signatures, replay nonces, and TestNet/voucher proofs."""

    @staticmethod
    def verify(db: Session, header_value: str, expected_resource: str) -> VerificationResult:
        settings = get_settings()
        execution_mode = get_runtime_mode(db)

        try:
            payload = parse_payment_signature_header(header_value)
        except Exception as exc:
            return VerificationResult(False, f"Malformed PAYMENT-SIGNATURE header: {exc}")

        if payload.protocol_version != settings.protocol_version:
            return VerificationResult(False, f"Unsupported protocol version '{payload.protocol_version}'", payload=payload)

        challenge = (
            db.query(PaymentChallenge)
            .filter(PaymentChallenge.challenge_id == payload.challenge_id)
            .first()
        )
        if not challenge:
            return VerificationResult(False, "Payment challenge not found", payload=payload)

        if challenge.resource != expected_resource:
            return VerificationResult(
                False,
                f"Challenge resource mismatch: expected {expected_resource}, got {challenge.resource}",
                payload=payload,
                challenge=challenge,
            )

        if challenge.status != "pending":
            return VerificationResult(
                False,
                f"Challenge already {challenge.status} (replay rejected)",
                payload=payload,
                challenge=challenge,
            )

        # Expiration check
        now = datetime.now(timezone.utc)
        expires_at = challenge.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            challenge.status = "expired"
            db.flush()
            return VerificationResult(False, "Payment challenge has expired", payload=payload, challenge=challenge)

        # Nonce & replay protection
        if payload.nonce != challenge.nonce:
            return VerificationResult(False, "Challenge nonce mismatch", payload=payload, challenge=challenge)

        existing_tx = (
            db.query(PaymentTransaction)
            .filter(
                (PaymentTransaction.challenge_id == challenge.challenge_id)
                | (PaymentTransaction.nonce == payload.nonce)
            )
            .filter(PaymentTransaction.verification_status == "verified")
            .first()
        )
        if existing_tx:
            return VerificationResult(
                False,
                "Duplicate payment / replay detected for challenge or nonce",
                payload=payload,
                challenge=challenge,
            )

        # Validate network, asset, recipient, and amount
        if payload.network != challenge.network:
            return VerificationResult(
                False,
                f"Network mismatch: expected {challenge.network}, got {payload.network}",
                payload=payload,
                challenge=challenge,
            )

        if payload.asset_id != challenge.asset_id:
            return VerificationResult(
                False,
                f"Asset ID mismatch: expected {challenge.asset_id}, got {payload.asset_id}",
                payload=payload,
                challenge=challenge,
            )

        if payload.recipient_address != challenge.recipient_address:
            return VerificationResult(
                False,
                "Recipient wallet address mismatch",
                payload=payload,
                challenge=challenge,
            )

        if payload.amount_micro_usdc < challenge.amount_micro_usdc:
            return VerificationResult(
                False,
                f"Underpayment rejected: required {challenge.amount_micro_usdc} microUSDC, got {payload.amount_micro_usdc}",
                payload=payload,
                challenge=challenge,
            )

        # Verify registered agent & payer address
        agent = db.query(Agent).filter(Agent.id == payload.agent_id).first()
        if not agent:
            return VerificationResult(False, f"Unknown agent '{payload.agent_id}'", payload=payload, challenge=challenge)

        if agent.wallet_address != payload.payer_address:
            return VerificationResult(
                False,
                "Payer address does not match registered agent wallet",
                payload=payload,
                challenge=challenge,
                agent=agent,
            )

        if not agent.is_active:
            return VerificationResult(
                False,
                "Agent is deactivated and not permitted to settle payments",
                payload=payload,
                challenge=challenge,
                agent=agent,
            )

        # Scheme-specific cryptographic & ledger verification
        if payload.scheme == "exact":
            canonical_dict = build_exact_signing_dict(
                protocol_version=payload.protocol_version,
                scheme=payload.scheme,
                network=payload.network,
                asset_id=payload.asset_id,
                challenge_id=payload.challenge_id,
                nonce=payload.nonce,
                agent_id=payload.agent_id,
                payer_address=payload.payer_address,
                recipient_address=payload.recipient_address,
                amount_micro_usdc=payload.amount_micro_usdc,
                timestamp=payload.timestamp,
                blockchain_tx_id=payload.blockchain_tx_id,
            )
            msg = WalletService.canonical_payment_message(canonical_dict)
            if not WalletService.verify_signature(payload.payer_address, msg, payload.signature):
                return VerificationResult(
                    False,
                    "Invalid Ed25519 digital signature for exact payment payload",
                    payload=payload,
                    challenge=challenge,
                    agent=agent,
                )

            if execution_mode == "algorand_testnet":
                if not payload.blockchain_tx_id:
                    return VerificationResult(
                        False,
                        "Algorand TestNet mode requires a confirmed blockchain transaction ID (no silent fallback)",
                        payload=payload,
                        challenge=challenge,
                        agent=agent,
                    )
                verifier = TransactionVerifier()
                onchain = verifier.verify_usdc_transfer_onchain(
                    tx_id=payload.blockchain_tx_id,
                    expected_sender=payload.payer_address,
                    expected_recipient=payload.recipient_address,
                    expected_asset_id=payload.asset_id,
                    min_amount_micro_usdc=challenge.amount_micro_usdc,
                )
                if not onchain.verified:
                    return VerificationResult(
                        False,
                        onchain.reason,
                        payload=payload,
                        challenge=challenge,
                        agent=agent,
                    )
                return VerificationResult(
                    True,
                    onchain.reason,
                    payload=payload,
                    challenge=challenge,
                    agent=agent,
                    confirmed_round=onchain.confirmed_round,
                )
            else:
                # Local Demo Mode: verify local agent demo USDC balance
                if agent.local_balance_micro_usdc < payload.amount_micro_usdc:
                    return VerificationResult(
                        False,
                        f"Insufficient local demo USDC balance (${agent.local_balance_micro_usdc / 1_000_000:.6f})",
                        payload=payload,
                        challenge=challenge,
                        agent=agent,
                    )
                return VerificationResult(
                    True,
                    "Ed25519 signature verified in Local Demo Mode",
                    payload=payload,
                    challenge=challenge,
                    agent=agent,
                )

        elif payload.scheme == "channel":
            if not payload.channel_id or payload.voucher_nonce is None or payload.cumulative_amount_micro is None:
                return VerificationResult(
                    False,
                    "Channel payment missing channel_id, voucher_nonce, or cumulative_amount_micro",
                    payload=payload,
                    challenge=challenge,
                    agent=agent,
                )

            channel = db.query(PaymentChannel).filter(PaymentChannel.id == payload.channel_id).first()
            if not channel:
                return VerificationResult(False, f"Payment channel '{payload.channel_id}' not found", payload=payload, challenge=challenge, agent=agent)
            if channel.status != "open":
                return VerificationResult(False, f"Payment channel '{channel.id}' is {channel.status}", payload=payload, challenge=challenge, agent=agent, channel=channel)
            if channel.agent_id != agent.id or channel.payer_address != payload.payer_address:
                return VerificationResult(False, "Channel payer mismatch", payload=payload, challenge=challenge, agent=agent, channel=channel)
            if channel.recipient_address != payload.recipient_address:
                return VerificationResult(False, "Channel recipient mismatch", payload=payload, challenge=challenge, agent=agent, channel=channel)
            if payload.voucher_nonce <= channel.last_nonce:
                return VerificationResult(
                    False,
                    f"Stale or duplicate voucher nonce {payload.voucher_nonce} (must be > {channel.last_nonce})",
                    payload=payload,
                    challenge=challenge,
                    agent=agent,
                    channel=channel,
                )

            dup_voucher = (
                db.query(ChannelVoucher)
                .filter(ChannelVoucher.channel_id == channel.id, ChannelVoucher.nonce == payload.voucher_nonce)
                .first()
            )
            if dup_voucher:
                return VerificationResult(False, "Duplicate voucher nonce rejected", payload=payload, challenge=challenge, agent=agent, channel=channel)

            expected_cumulative = channel.cumulative_spent_micro + payload.amount_micro_usdc
            if payload.cumulative_amount_micro < expected_cumulative:
                return VerificationResult(
                    False,
                    f"Cumulative voucher amount {payload.cumulative_amount_micro} < required {expected_cumulative}",
                    payload=payload,
                    challenge=challenge,
                    agent=agent,
                    channel=channel,
                )

            if payload.cumulative_amount_micro > channel.deposited_micro_usdc:
                return VerificationResult(
                    False,
                    f"Cumulative voucher amount exceeds channel escrow deposit ({channel.deposited_micro_usdc} microUSDC)",
                    payload=payload,
                    challenge=challenge,
                    agent=agent,
                    channel=channel,
                )

            voucher_dict = build_voucher_signing_dict(
                channel_id=channel.id,
                nonce=payload.voucher_nonce,
                cumulative_amount_micro=payload.cumulative_amount_micro,
                payer_address=payload.payer_address,
                recipient_address=payload.recipient_address,
                asset_id=payload.asset_id,
                network=payload.network,
            )
            msg = WalletService.canonical_payment_message(voucher_dict)
            if not WalletService.verify_signature(payload.payer_address, msg, payload.signature):
                return VerificationResult(
                    False,
                    "Invalid Ed25519 voucher signature",
                    payload=payload,
                    challenge=challenge,
                    agent=agent,
                    channel=channel,
                )

            return VerificationResult(
                True,
                f"Channel voucher #{payload.voucher_nonce} verified locally via Ed25519",
                payload=payload,
                challenge=challenge,
                agent=agent,
                channel=channel,
            )

        return VerificationResult(False, f"Unsupported payment scheme '{payload.scheme}'", payload=payload, challenge=challenge, agent=agent)
