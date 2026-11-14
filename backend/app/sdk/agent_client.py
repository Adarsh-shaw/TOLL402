import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.app.blockchain.transaction_verifier import TransactionVerifier
from backend.app.blockchain.wallet_service import WalletService
from backend.app.models.models import Agent, ApiService, PaymentChannel
from backend.app.schemas.schemas import (
    DemoStepTrace,
    PaymentRequiredHeaderPayload,
    PaymentSignatureHeaderPayload,
)
from backend.app.services.agent_service import AgentService, get_runtime_mode
from backend.app.services.audit_service import AuditService
from backend.app.services.channel_service import ChannelService
from backend.app.services.policy_engine import PolicyEngine
from backend.app.services.verification_service import build_exact_signing_dict


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TollRailAgentClient:
    """
    Autonomous Agent SDK implementing the full 11-step HTTP 402 payment protocol.
    Makes real HTTP requests against the protected API endpoints, inspects HTTP 402 challenges,
    evaluates spending policy, signs Algorand Ed25519 proofs or channel vouchers, and retries.
    """

    def __init__(self, http_client: httpx.Client) -> None:
        self.http_client = http_client

    @staticmethod
    def decode_header_json(header_val: str) -> dict[str, Any]:
        raw = header_val.strip()
        if raw.startswith("{"):
            return json.loads(raw)
        return json.loads(base64.b64decode(raw).decode("utf-8"))

    @staticmethod
    def encode_header_json(data: dict[str, Any]) -> str:
        raw = json.dumps(data, separators=(",", ":"))
        return base64.b64encode(raw.encode("utf-8")).decode("utf-8")

    def execute_paid_request(
        self,
        db: Session,
        *,
        agent: Agent,
        service: ApiService,
        settlement_mode: str | None = None,
        channel_id: str | None = None,
        request_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        trace_id = f"trc_{uuid.uuid4().hex[:12]}"
        steps: list[DemoStepTrace] = []
        mode = get_runtime_mode(db)
        chosen_scheme = settlement_mode or agent.default_settlement_mode or "exact"
        payload_to_send = request_payload if request_payload is not None else (service.sample_payload or {})

        # STEP 1: Unauthenticated request to protected endpoint
        req_headers = {"X-TollRail-Trace-Id": trace_id}
        if service.method.upper() == "GET":
            first_resp = self.http_client.get(service.endpoint, headers=req_headers)
        else:
            first_resp = self.http_client.post(service.endpoint, json=payload_to_send, headers=req_headers)

        steps.append(
            DemoStepTrace(
                step=1,
                title="Agent sends initial API request without payment",
                status="completed",
                timestamp=_now_iso(),
                http_status=first_resp.status_code,
                summary=f"{service.method.upper()} {service.endpoint} sent without PAYMENT-SIGNATURE header.",
                headers=dict(req_headers),
                body=payload_to_send if service.method.upper() != "GET" else None,
            )
        )

        if first_resp.status_code != 402:
            return {
                "trace_id": trace_id,
                "success": first_resp.status_code == 200,
                "settlement_mode": chosen_scheme,
                "execution_mode": mode,
                "final_http_status": first_resp.status_code,
                "steps": steps,
                "api_response": first_resp.json() if first_resp.content else None,
            }

        # STEP 2 & 3: Parse HTTP 402 Payment Required + PAYMENT-REQUIRED header
        pr_header_raw = first_resp.headers.get("PAYMENT-REQUIRED") or first_resp.headers.get("payment-required")
        if not pr_header_raw:
            steps.append(
                DemoStepTrace(
                    step=2,
                    title="HTTP 402 Payment Required missing header",
                    status="failed",
                    timestamp=_now_iso(),
                    http_status=402,
                    summary="Server returned 402 without PAYMENT-REQUIRED header.",
                )
            )
            return {
                "trace_id": trace_id,
                "success": False,
                "settlement_mode": chosen_scheme,
                "execution_mode": mode,
                "final_http_status": 402,
                "steps": steps,
                "api_response": first_resp.json(),
            }

        challenge_data = self.decode_header_json(pr_header_raw)
        challenge_payload = PaymentRequiredHeaderPayload(**challenge_data)

        steps.append(
            DemoStepTrace(
                step=2,
                title="Server responds with HTTP 402 & PAYMENT-REQUIRED challenge",
                status="completed",
                timestamp=_now_iso(),
                http_status=402,
                summary=f"Challenge {challenge_payload.challenge_id} requires {challenge_payload.amount_usdc} USDC on {challenge_payload.network}.",
                headers={"PAYMENT-REQUIRED": pr_header_raw, "X-TollRail-Trace-Id": trace_id},
                body=challenge_payload.model_dump(),
            )
        )

        # Resolve active channel if settlement_mode == 'channel'
        channel: PaymentChannel | None = None
        if chosen_scheme == "channel":
            if channel_id:
                channel = db.query(PaymentChannel).filter(PaymentChannel.id == channel_id).first()
            else:
                channel = (
                    db.query(PaymentChannel)
                    .filter(PaymentChannel.agent_id == agent.id, PaymentChannel.status == "open")
                    .order_by(PaymentChannel.created_at.desc())
                    .first()
                )
            if not channel:
                AuditService.record_event(
                    db,
                    trace_id=trace_id,
                    event_type="POLICY_REJECTED",
                    agent_id=agent.id,
                    service_id=service.id,
                    challenge_id=challenge_payload.challenge_id,
                    status="error",
                    message="No open payment channel available for channel settlement mode.",
                    commit=True,
                )
                steps.append(
                    DemoStepTrace(
                        step=3,
                        title="Spending policy & channel availability check",
                        status="failed",
                        timestamp=_now_iso(),
                        summary="No open payment channel found for this agent. Open a channel first or use Exact mode.",
                    )
                )
                return {
                    "trace_id": trace_id,
                    "success": False,
                    "settlement_mode": chosen_scheme,
                    "execution_mode": mode,
                    "final_http_status": 402,
                    "steps": steps,
                    "api_response": {"error": "No open payment channel available for agent."},
                }

        # STEP 4 & 5: Agent SDK evaluates spending policy
        expires_dt = datetime.fromisoformat(challenge_payload.expires_at)
        policy_res = PolicyEngine.evaluate(
            db=db,
            agent=agent,
            amount_micro_usdc=challenge_payload.amount_micro_usdc,
            target_host=service.host,
            expires_at=expires_dt,
            settlement_mode=chosen_scheme,
            channel=channel,
        )

        if not policy_res.approved:
            AuditService.record_event(
                db,
                trace_id=trace_id,
                event_type="POLICY_REJECTED",
                agent_id=agent.id,
                service_id=service.id,
                challenge_id=challenge_payload.challenge_id,
                status="error",
                message=f"Agent policy rejected payment: {policy_res.reason}",
                metadata={"checks": [c.model_dump() for c in policy_res.checks]},
                commit=True,
            )
            steps.append(
                DemoStepTrace(
                    step=3,
                    title="Agent evaluates spending policy — REJECTED",
                    status="failed",
                    timestamp=_now_iso(),
                    summary=policy_res.reason,
                    body=policy_res.model_dump(),
                )
            )
            return {
                "trace_id": trace_id,
                "success": False,
                "settlement_mode": chosen_scheme,
                "execution_mode": mode,
                "final_http_status": 402,
                "steps": steps,
                "api_response": {"error": "Spending Policy Rejected", "reason": policy_res.reason, "policy": policy_res.model_dump()},
            }

        AuditService.record_event(
            db,
            trace_id=trace_id,
            event_type="POLICY_APPROVED",
            agent_id=agent.id,
            service_id=service.id,
            challenge_id=challenge_payload.challenge_id,
            channel_id=channel.id if channel else None,
            status="success",
            message=f"Agent {agent.name} spending policy approved ${challenge_payload.amount_usdc} USDC ({chosen_scheme} mode)",
            commit=True,
        )
        steps.append(
            DemoStepTrace(
                step=3,
                title="Agent evaluates spending policy — APPROVED",
                status="completed",
                timestamp=_now_iso(),
                summary=f"All 6 policy checks passed (${challenge_payload.amount_usdc} USDC within ${policy_res.per_request_limit_usdc:.4f} limit).",
                body=policy_res.model_dump(),
            )
        )

        # STEP 6: Sign payment & submit on-chain (if TestNet Exact) or generate signed voucher
        try:
            sk = AgentService.get_decrypted_signing_key(agent)
        except Exception as exc:
            steps.append(
                DemoStepTrace(
                    step=4,
                    title="Wallet signing failed",
                    status="failed",
                    timestamp=_now_iso(),
                    summary=str(exc),
                )
            )
            return {
                "trace_id": trace_id,
                "success": False,
                "settlement_mode": chosen_scheme,
                "execution_mode": mode,
                "final_http_status": 402,
                "steps": steps,
                "api_response": {"error": str(exc)},
            }

        sig_ts = _now_iso()
        blockchain_tx_id: str | None = None
        voucher_nonce: int | None = None
        cumulative_micro: int | None = None

        if chosen_scheme == "exact":
            if mode == "algorand_testnet":
                try:
                    verifier = TransactionVerifier()
                    blockchain_tx_id = verifier.submit_usdc_transfer(
                        private_key_b64=sk,
                        sender_address=agent.wallet_address,
                        recipient_address=challenge_payload.recipient_address,
                        amount_micro_usdc=challenge_payload.amount_micro_usdc,
                        asset_id=challenge_payload.asset_id,
                        note_text=f"tollrail402:{challenge_payload.challenge_id}",
                    )
                except Exception as exc:
                    AuditService.record_event(
                        db,
                        trace_id=trace_id,
                        event_type="PAYMENT_FAILED",
                        agent_id=agent.id,
                        service_id=service.id,
                        challenge_id=challenge_payload.challenge_id,
                        status="error",
                        message=f"Algorand TestNet USDC transfer failed: {exc}",
                        commit=True,
                    )
                    steps.append(
                        DemoStepTrace(
                            step=4,
                            title="Algorand TestNet USDC transfer failed",
                            status="failed",
                            timestamp=_now_iso(),
                            summary=str(exc),
                        )
                    )
                    return {
                        "trace_id": trace_id,
                        "success": False,
                        "settlement_mode": chosen_scheme,
                        "execution_mode": mode,
                        "final_http_status": 402,
                        "steps": steps,
                        "api_response": {"error": f"Algorand TestNet submission failed: {exc}"},
                    }

            canonical = build_exact_signing_dict(
                protocol_version=challenge_payload.protocol_version,
                scheme="exact",
                network=challenge_payload.network,
                asset_id=challenge_payload.asset_id,
                challenge_id=challenge_payload.challenge_id,
                nonce=challenge_payload.nonce,
                agent_id=agent.id,
                payer_address=agent.wallet_address,
                recipient_address=challenge_payload.recipient_address,
                amount_micro_usdc=challenge_payload.amount_micro_usdc,
                timestamp=sig_ts,
                blockchain_tx_id=blockchain_tx_id,
            )
            signature_b64 = WalletService.sign_message(sk, WalletService.canonical_payment_message(canonical))
            step4_summary = (
                f"Submitted real Algorand TestNet TX {blockchain_tx_id} & signed Ed25519 proof."
                if blockchain_tx_id
                else f"Signed Ed25519 exact payment authorization for ${challenge_payload.amount_usdc} USDC (Local Demo Mode)."
            )
        else:
            assert channel is not None
            voucher_nonce, cumulative_micro, signature_b64 = ChannelService.sign_next_voucher(
                db=db,
                channel=channel,
                agent=agent,
                delta_micro_usdc=challenge_payload.amount_micro_usdc,
            )
            step4_summary = (
                f"Signed cumulative Ed25519 voucher #{voucher_nonce} on channel {channel.id} "
                f"(cumulative ${cumulative_micro / 1_000_000:.6f} USDC)."
            )

        sig_payload = PaymentSignatureHeaderPayload(
            protocol_version=challenge_payload.protocol_version,
            scheme=chosen_scheme,  # type: ignore[arg-type]
            network=challenge_payload.network,
            asset_id=challenge_payload.asset_id,
            challenge_id=challenge_payload.challenge_id,
            nonce=challenge_payload.nonce,
            agent_id=agent.id,
            payer_address=agent.wallet_address,
            recipient_address=challenge_payload.recipient_address,
            amount_micro_usdc=challenge_payload.amount_micro_usdc,
            timestamp=sig_ts,
            signature=signature_b64,
            blockchain_tx_id=blockchain_tx_id,
            channel_id=channel.id if channel else None,
            voucher_nonce=voucher_nonce,
            cumulative_amount_micro=cumulative_micro,
        )

        AuditService.record_event(
            db,
            trace_id=trace_id,
            event_type="PAYMENT_SUBMITTED",
            agent_id=agent.id,
            service_id=service.id,
            challenge_id=challenge_payload.challenge_id,
            channel_id=channel.id if channel else None,
            status="info",
            message=step4_summary,
            commit=True,
        )

        steps.append(
            DemoStepTrace(
                step=4,
                title="Agent signs & submits payment authorization",
                status="completed",
                timestamp=_now_iso(),
                summary=step4_summary,
                body=sig_payload.model_dump(),
            )
        )

        # STEP 7: Retry original request with PAYMENT-SIGNATURE header
        encoded_sig = self.encode_header_json(sig_payload.model_dump())
        retry_headers = {
            "PAYMENT-SIGNATURE": encoded_sig,
            "X-TollRail-Trace-Id": trace_id,
        }
        if service.method.upper() == "GET":
            retry_resp = self.http_client.get(service.endpoint, headers=retry_headers)
        else:
            retry_resp = self.http_client.post(service.endpoint, json=payload_to_send, headers=retry_headers)

        retry_body = retry_resp.json() if retry_resp.content else None
        payment_resp_raw = retry_resp.headers.get("PAYMENT-RESPONSE") or retry_resp.headers.get("payment-response")
        decoded_payment_resp = self.decode_header_json(payment_resp_raw) if payment_resp_raw else None

        steps.append(
            DemoStepTrace(
                step=5,
                title="Agent retries request with PAYMENT-SIGNATURE; middleware verifies & settles",
                status="completed" if retry_resp.status_code == 200 else "failed",
                timestamp=_now_iso(),
                http_status=retry_resp.status_code,
                summary=(
                    f"HTTP {retry_resp.status_code} received with PAYMENT-RESPONSE receipt."
                    if retry_resp.status_code == 200
                    else f"Middleware rejected payment with HTTP {retry_resp.status_code}."
                ),
                headers={"PAYMENT-RESPONSE": payment_resp_raw, "X-TollRail-Trace-Id": trace_id} if payment_resp_raw else dict(retry_resp.headers),
                body=decoded_payment_resp or retry_body,
            )
        )

        if retry_resp.status_code == 200:
            steps.append(
                DemoStepTrace(
                    step=6,
                    title="Protected API resource delivered & audit ledger settled",
                    status="completed",
                    timestamp=_now_iso(),
                    http_status=200,
                    summary=f"Protected resource {service.endpoint} returned live output.",
                    body=retry_body,
                )
            )

        return {
            "trace_id": trace_id,
            "success": retry_resp.status_code == 200,
            "settlement_mode": chosen_scheme,
            "execution_mode": mode,
            "final_http_status": retry_resp.status_code,
            "steps": steps,
            "api_response": retry_body,
            "payment_response": decoded_payment_resp,
        }
