import uuid
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.models import ApiService
from backend.app.services.audit_service import AuditService
from backend.app.services.payment_service import PaymentService


def require_x402_payment(endpoint_path: str):
    """
    FastAPI dependency implementing the HTTP 402 Payment Required protocol gate.
    - Step 1/2/3: Without PAYMENT-SIGNATURE, issues a fresh challenge and responds HTTP 402 + PAYMENT-REQUIRED header.
    - Step 8/9/10: With PAYMENT-SIGNATURE, verifies Ed25519 signature, replay nonce, expiry, and settlement proof,
      then attaches PAYMENT-RESPONSE metadata to request.state and response headers.
    """

    def _dependency(request: Request, response: Response, db: Session = Depends(get_db)):
        trace_id = request.headers.get("X-TollRail-Trace-Id") or f"trc_{uuid.uuid4().hex[:12]}"
        request.state.trace_id = trace_id

        service = db.query(ApiService).filter(ApiService.endpoint == endpoint_path).first()
        if not service:
            raise HTTPException(status_code=404, detail=f"Protected service '{endpoint_path}' not registered.")
        if not service.is_available:
            raise HTTPException(status_code=503, detail=f"Service '{service.name}' is currently unavailable.")

        payment_sig = request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("payment-signature")

        if not payment_sig:
            AuditService.record_event(
                db,
                trace_id=trace_id,
                event_type="REQUEST_RECEIVED",
                service_id=service.id,
                status="info",
                message=f"Incoming {request.method} {endpoint_path} without PAYMENT-SIGNATURE header",
                metadata={"client": request.client.host if request.client else "unknown"},
            )
            challenge, header_payload = PaymentService.create_challenge(db, service, trace_id)
            encoded_header = PaymentService.encode_header(header_payload)
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Payment Required",
                    "message": f"Access to {service.name} requires {header_payload.amount_usdc} USDC on {service.network}.",
                    "payment_required": header_payload.model_dump(),
                },
                headers={
                    "PAYMENT-REQUIRED": encoded_header,
                    "X-TollRail-Trace-Id": trace_id,
                    "WWW-Authenticate": f'x402 protocol="{header_payload.protocol_version}", network="{header_payload.network}"',
                },
            )

        # Retry received with PAYMENT-SIGNATURE
        AuditService.record_event(
            db,
            trace_id=trace_id,
            event_type="REQUEST_RECEIVED",
            service_id=service.id,
            status="info",
            message=f"Authenticated retry {request.method} {endpoint_path} with PAYMENT-SIGNATURE header",
            commit=True,
        )

        ok, verification, tx_record, payment_response_header = PaymentService.verify_and_settle(
            db=db,
            payment_signature_header=payment_sig,
            service=service,
            trace_id=trace_id,
        )

        if not ok or not tx_record or not payment_response_header:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Payment Verification Failed",
                    "reason": verification.reason,
                    "challenge_id": verification.challenge.challenge_id if verification.challenge else None,
                },
                headers={
                    "X-Payment-Error": verification.reason,
                    "X-TollRail-Trace-Id": trace_id,
                },
            )

        encoded_resp_header = PaymentService.encode_header(payment_response_header)
        response.headers["PAYMENT-RESPONSE"] = encoded_resp_header
        response.headers["X-TollRail-Trace-Id"] = trace_id

        request.state.x402_tx = tx_record
        request.state.x402_response_header = payment_response_header
        return {
            "trace_id": trace_id,
            "service": service,
            "transaction": tx_record,
            "payment_response": payment_response_header,
        }

    return _dependency
