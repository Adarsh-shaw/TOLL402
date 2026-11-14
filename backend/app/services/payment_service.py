import base64
import json
import time
import uuid
from datetime import timedelta
from sqlalchemy.orm import Session

from backend.app.blockchain.algorand_client import AlgorandClient
from backend.app.config import get_settings
from backend.app.models.models import (
    Agent,
    ApiService,
    PaymentChallenge,
    PaymentTransaction,
    utc_now,
)
from backend.app.schemas.schemas import (
    PaymentRequiredHeaderPayload,
    PaymentResponseHeaderPayload,
    PaymentTransactionResponse,
    micro_to_usdc,
)
from backend.app.services.agent_service import get_runtime_mode
from backend.app.services.audit_service import AuditService
from backend.app.services.settlement_service import SettlementService
from backend.app.services.verification_service import VerificationResult, VerificationService


class PaymentService:
    """Orchestrates HTTP 402 challenges, payment verification, settlement, and receipt headers."""

    @staticmethod
    def create_challenge(db: Session, service: ApiService, trace_id: str) -> tuple[PaymentChallenge, PaymentRequiredHeaderPayload]:
        settings = get_settings()
        now = utc_now()
        expires_at = now + timedelta(seconds=settings.challenge_ttl_seconds)
        challenge_id = f"chl_{uuid.uuid4().hex[:14]}"
        nonce = uuid.uuid4().hex

        challenge = PaymentChallenge(
            challenge_id=challenge_id,
            nonce=nonce,
            service_id=service.id,
            resource=service.endpoint,
            amount_micro_usdc=service.price_micro_usdc,
            asset_id=service.asset_id,
            network=service.network,
            recipient_address=service.recipient_address,
            supported_schemes=["exact", "channel"],
            status="pending",
            expires_at=expires_at,
            created_at=now,
        )
        db.add(challenge)

        AuditService.record_event(
            db,
            trace_id=trace_id,
            event_type="PAYMENT_REQUIRED",
            service_id=service.id,
            challenge_id=challenge_id,
            status="warning",
            message=f"Issued HTTP 402 challenge {challenge_id} for ${micro_to_usdc(service.price_micro_usdc):.6f} {service.asset_symbol} on {service.network}",
            metadata={"nonce": nonce, "expires_at": expires_at.isoformat()},
        )
        db.commit()
        db.refresh(challenge)

        header_payload = PaymentRequiredHeaderPayload(
            protocol_version=settings.protocol_version,
            schemes=["exact", "channel"],
            network=service.network,
            asset_id=service.asset_id,
            asset_symbol=service.asset_symbol,
            amount_micro_usdc=service.price_micro_usdc,
            amount_usdc=f"{micro_to_usdc(service.price_micro_usdc):.6f}",
            recipient_address=service.recipient_address,
            resource=service.endpoint,
            challenge_id=challenge_id,
            nonce=nonce,
            expires_at=expires_at.isoformat(),
        )
        return challenge, header_payload

    @staticmethod
    def encode_header(model) -> str:
        raw = json.dumps(model.model_dump(), separators=(",", ":"))
        return base64.b64encode(raw.encode("utf-8")).decode("utf-8")

    @staticmethod
    def verify_and_settle(
        db: Session,
        *,
        payment_signature_header: str,
        service: ApiService,
        trace_id: str,
    ) -> tuple[bool, VerificationResult, PaymentTransaction | None, PaymentResponseHeaderPayload | None]:
        t0 = time.perf_counter()
        verification = VerificationService.verify(db, payment_signature_header, service.endpoint)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        agent_id = verification.payload.agent_id if verification.payload else None
        challenge_id = verification.payload.challenge_id if verification.payload else None

        if not verification.valid:
            # Record failed payment attempt atomically if challenge exists & not already recorded
            AuditService.record_event(
                db,
                trace_id=trace_id,
                event_type="PAYMENT_FAILED",
                agent_id=agent_id,
                service_id=service.id,
                challenge_id=challenge_id,
                status="error",
                message=f"Payment verification failed: {verification.reason}",
                metadata={"verification_time_ms": round(elapsed_ms, 2)},
            )
            if verification.challenge and verification.payload and verification.agent:
                # Store failed transaction record for visibility in Explorer (with unique nonce suffix so challenge isn't locked if retry needed, or only if distinct)
                existing_for_challenge = (
                    db.query(PaymentTransaction)
                    .filter(PaymentTransaction.challenge_id == verification.challenge.challenge_id)
                    .first()
                )
                if not existing_for_challenge:
                    failed_tx = PaymentTransaction(
                        id=f"txr_{uuid.uuid4().hex[:12]}",
                        challenge_id=verification.challenge.challenge_id,
                        nonce=f"fail_{uuid.uuid4().hex[:16]}",
                        agent_id=verification.agent.id,
                        service_id=service.id,
                        endpoint=service.endpoint,
                        payer_address=verification.payload.payer_address,
                        recipient_address=verification.payload.recipient_address,
                        amount_micro_usdc=verification.payload.amount_micro_usdc,
                        asset_id=verification.payload.asset_id,
                        network=verification.payload.network,
                        settlement_mode=verification.payload.scheme,
                        execution_mode=get_runtime_mode(db),
                        is_simulated=get_runtime_mode(db) != "algorand_testnet",
                        blockchain_tx_id=None,
                        local_receipt_ref=None,
                        voucher_id=None,
                        channel_id=verification.payload.channel_id,
                        signature=verification.payload.signature,
                        verification_status="failed",
                        failure_reason=verification.reason,
                        verification_time_ms=round(elapsed_ms, 2),
                    )
                    db.add(failed_tx)
                    if verification.challenge.status == "pending":
                        verification.challenge.status = "failed"
            db.commit()
            return False, verification, None, None

        assert verification.payload and verification.challenge and verification.agent
        AuditService.record_event(
            db,
            trace_id=trace_id,
            event_type="PAYMENT_VERIFIED",
            agent_id=verification.agent.id,
            service_id=service.id,
            challenge_id=verification.challenge.challenge_id,
            channel_id=verification.payload.channel_id,
            status="success",
            message=verification.reason,
            metadata={"verification_time_ms": round(elapsed_ms, 2), "scheme": verification.payload.scheme},
        )

        try:
            tx_record = SettlementService.settle_verified_payment(
                db=db,
                verification=verification,
                service_id=service.id,
                endpoint=service.endpoint,
                verification_time_ms=elapsed_ms,
            )
            AuditService.record_event(
                db,
                trace_id=trace_id,
                event_type="SERVICE_DELIVERED",
                agent_id=verification.agent.id,
                service_id=service.id,
                challenge_id=verification.challenge.challenge_id,
                transaction_id=tx_record.id,
                channel_id=tx_record.channel_id,
                status="success",
                message=f"Released protected resource {service.endpoint}",
            )
            AuditService.record_event(
                db,
                trace_id=trace_id,
                event_type="SETTLED",
                agent_id=verification.agent.id,
                service_id=service.id,
                challenge_id=verification.challenge.challenge_id,
                transaction_id=tx_record.id,
                channel_id=tx_record.channel_id,
                status="success",
                message=(
                    f"Settled ${micro_to_usdc(tx_record.amount_micro_usdc):.6f} USDC via {tx_record.settlement_mode} mode"
                    + (f" (TestNet TX: {tx_record.blockchain_tx_id})" if tx_record.blockchain_tx_id else f" (Ref: {tx_record.local_receipt_ref})")
                ),
            )
            db.commit()
            db.refresh(tx_record)
        except Exception as exc:
            db.rollback()
            AuditService.record_event(
                db,
                trace_id=trace_id,
                event_type="PAYMENT_FAILED",
                agent_id=verification.agent.id,
                service_id=service.id,
                challenge_id=verification.challenge.challenge_id,
                status="error",
                message=f"Atomic settlement aborted: {exc}",
                commit=True,
            )
            return False, VerificationResult(False, f"Settlement error: {exc}"), None, None

        response_header = PaymentResponseHeaderPayload(
            success=True,
            payment_reference=tx_record.blockchain_tx_id or tx_record.local_receipt_ref or tx_record.id,
            transaction_id=tx_record.id,
            voucher_id=tx_record.voucher_id,
            settlement_mode=tx_record.settlement_mode,
            execution_mode=tx_record.execution_mode,
            is_simulated=tx_record.is_simulated,
            amount_micro_usdc=tx_record.amount_micro_usdc,
            amount_usdc=f"{micro_to_usdc(tx_record.amount_micro_usdc):.6f}",
            timestamp=tx_record.created_at.isoformat(),
        )
        return True, verification, tx_record, response_header

    @staticmethod
    def tx_to_response(db: Session, tx: PaymentTransaction) -> PaymentTransactionResponse:
        agent = db.query(Agent).filter(Agent.id == tx.agent_id).first()
        svc = db.query(ApiService).filter(ApiService.id == tx.service_id).first()
        explorer_url = AlgorandClient().get_explorer_tx_url(tx.blockchain_tx_id) if tx.blockchain_tx_id else None
        return PaymentTransactionResponse(
            id=tx.id,
            challenge_id=tx.challenge_id,
            nonce=tx.nonce,
            agent_id=tx.agent_id,
            agent_name=agent.name if agent else None,
            service_id=tx.service_id,
            service_name=svc.name if svc else None,
            endpoint=tx.endpoint,
            payer_address=tx.payer_address,
            recipient_address=tx.recipient_address,
            amount_micro_usdc=tx.amount_micro_usdc,
            amount_usdc=micro_to_usdc(tx.amount_micro_usdc),
            asset_id=tx.asset_id,
            network=tx.network,
            settlement_mode=tx.settlement_mode,
            execution_mode=tx.execution_mode,
            is_simulated=tx.is_simulated,
            blockchain_tx_id=tx.blockchain_tx_id,
            explorer_url=explorer_url,
            local_receipt_ref=tx.local_receipt_ref,
            voucher_id=tx.voucher_id,
            channel_id=tx.channel_id,
            verification_status=tx.verification_status,
            failure_reason=tx.failure_reason,
            verification_time_ms=tx.verification_time_ms,
            created_at=tx.created_at,
        )
