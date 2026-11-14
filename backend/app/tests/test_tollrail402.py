import base64
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

# Configure isolated SQLite DB for tests before importing app modules
_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_TEST_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["TOLLRAIL_MODE"] = "local_demo"

from backend.app.blockchain.wallet_service import WalletService  # noqa: E402
from backend.app.database import Base, SessionLocal, engine  # noqa: E402
from backend.app import main as main_module  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.models.models import Agent, ApiService, AuditLog, PaymentChallenge, PlatformSetting  # noqa: E402
from backend.app.sdk.agent_client import TollRailAgentClient  # noqa: E402
from backend.app.seed import seed_initial_data  # noqa: E402
from backend.app.services.agent_service import AgentService  # noqa: E402
from backend.app.services.channel_service import ChannelService  # noqa: E402
from backend.app.services.verification_service import build_exact_signing_dict  # noqa: E402


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_initial_data(db)
    finally:
        db.close()
    main_module._initialized = True
    yield


def _decode_header(val: str) -> dict:
    return json.loads(base64.b64decode(val).decode("utf-8"))


def _encode_header(data: dict) -> str:
    return base64.b64encode(json.dumps(data, separators=(",", ":")).encode("utf-8")).decode("utf-8")


def _sign_challenge_for_agent(db, agent: Agent, challenge_data: dict, override: dict | None = None) -> str:
    sk = AgentService.get_decrypted_signing_key(agent)
    ts = datetime.now(timezone.utc).isoformat()
    amount = challenge_data["amount_micro_usdc"]
    recipient = challenge_data["recipient_address"]
    asset_id = challenge_data["asset_id"]
    network = challenge_data["network"]
    if override:
        amount = override.get("amount_micro_usdc", amount)
        recipient = override.get("recipient_address", recipient)
        asset_id = override.get("asset_id", asset_id)
        network = override.get("network", network)

    canonical = build_exact_signing_dict(
        protocol_version=challenge_data["protocol_version"],
        scheme="exact",
        network=network,
        asset_id=asset_id,
        challenge_id=challenge_data["challenge_id"],
        nonce=challenge_data["nonce"],
        agent_id=agent.id,
        payer_address=agent.wallet_address,
        recipient_address=recipient,
        amount_micro_usdc=amount,
        timestamp=ts,
        blockchain_tx_id=None,
    )
    sig = WalletService.sign_message(sk, WalletService.canonical_payment_message(canonical))
    if override and "signature" in override:
        sig = override["signature"]

    payload = {
        **canonical,
        "signature": sig,
    }
    return _encode_header(payload)


def test_01_http_402_challenge_generation():
    client = TestClient(app)
    resp = client.post("/v1/infer", json={"prompt": "test prompt"})
    assert resp.status_code == 402
    assert "PAYMENT-REQUIRED" in resp.headers
    pr = _decode_header(resp.headers["PAYMENT-REQUIRED"])
    assert pr["protocol_version"] == "x402/1.0"
    assert pr["network"] == "algorand:testnet"
    assert pr["asset_id"] == 10458941
    assert pr["amount_micro_usdc"] == 5000
    assert pr["resource"] == "/v1/infer"
    assert pr["challenge_id"].startswith("chl_")
    assert len(pr["nonce"]) >= 16


def test_02_correct_payment_verification_and_delivery():
    client = TestClient(app)
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == "agt_research_01").first()
        service = db.query(ApiService).filter(ApiService.id == "svc_infer").first()
        start_bal = agent.local_balance_micro_usdc

        hc = TestClient(app, base_url="http://api.tollrail402.local")
        sdk = TollRailAgentClient(hc)
        trace = sdk.execute_paid_request(db, agent=agent, service=service, settlement_mode="exact")

        assert trace["success"] is True
        assert trace["final_http_status"] == 200
        assert trace["api_response"]["status"] == "delivered"
        assert trace["payment_response"]["success"] is True

        db.refresh(agent)
        assert agent.local_balance_micro_usdc == start_bal - service.price_micro_usdc
    finally:
        db.close()


def test_03_incorrect_payment_amount_rejected():
    client = TestClient(app)
    r1 = client.post("/v1/infer", json={"prompt": "test"})
    assert r1.status_code == 402
    pr = _decode_header(r1.headers["PAYMENT-REQUIRED"])

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == "agt_research_01").first()
        bad_sig_header = _sign_challenge_for_agent(db, agent, pr, override={"amount_micro_usdc": 100})
    finally:
        db.close()

    r2 = client.post("/v1/infer", json={"prompt": "test"}, headers={"PAYMENT-SIGNATURE": bad_sig_header})
    assert r2.status_code == 402
    assert "Underpayment rejected" in r2.json()["detail"]["reason"]


def test_04_invalid_ed25519_signature_rejected():
    client = TestClient(app)
    r1 = client.post("/v1/infer", json={"prompt": "test"})
    pr = _decode_header(r1.headers["PAYMENT-REQUIRED"])

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == "agt_research_01").first()
        fake_sig = base64.b64encode(b"0" * 64).decode("utf-8")
        bad_header = _sign_challenge_for_agent(db, agent, pr, override={"signature": fake_sig})
    finally:
        db.close()

    r2 = client.post("/v1/infer", json={"prompt": "test"}, headers={"PAYMENT-SIGNATURE": bad_header})
    assert r2.status_code == 402
    assert "Invalid Ed25519 digital signature" in r2.json()["detail"]["reason"]


def test_05_expired_challenge_rejected():
    client = TestClient(app)
    r1 = client.post("/v1/infer", json={"prompt": "test"})
    pr = _decode_header(r1.headers["PAYMENT-REQUIRED"])

    db = SessionLocal()
    try:
        ch = db.query(PaymentChallenge).filter(PaymentChallenge.challenge_id == pr["challenge_id"]).first()
        ch.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.commit()
        agent = db.query(Agent).filter(Agent.id == "agt_research_01").first()
        sig_header = _sign_challenge_for_agent(db, agent, pr)
    finally:
        db.close()

    r2 = client.post("/v1/infer", json={"prompt": "test"}, headers={"PAYMENT-SIGNATURE": sig_header})
    assert r2.status_code == 402
    assert "expired" in r2.json()["detail"]["reason"].lower()


def test_06_duplicate_replay_request_rejected():
    client = TestClient(app)
    r1 = client.post("/v1/infer", json={"prompt": "test"})
    pr = _decode_header(r1.headers["PAYMENT-REQUIRED"])

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == "agt_research_01").first()
        sig_header = _sign_challenge_for_agent(db, agent, pr)
    finally:
        db.close()

    r2 = client.post("/v1/infer", json={"prompt": "test"}, headers={"PAYMENT-SIGNATURE": sig_header})
    assert r2.status_code == 200

    # Replay exact same PAYMENT-SIGNATURE header
    r3 = client.post("/v1/infer", json={"prompt": "test"}, headers={"PAYMENT-SIGNATURE": sig_header})
    assert r3.status_code == 402
    assert "replay" in r3.json()["detail"]["reason"].lower()


def test_07_spending_policy_violations():
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == "agt_research_01").first()
        # svc_image costs $0.015 > agt_research_01 limit ($0.01)
        svc_image = db.query(ApiService).filter(ApiService.id == "svc_image").first()

        hc = TestClient(app, base_url="http://api.tollrail402.local")
        sdk = TollRailAgentClient(hc)
        trace = sdk.execute_paid_request(db, agent=agent, service=svc_image, settlement_mode="exact")

        assert trace["success"] is False
        assert trace["final_http_status"] == 402
        assert "exceeds per-request limit" in trace["api_response"]["reason"]
    finally:
        db.close()


def test_08_insufficient_funds_rejected():
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == "agt_research_01").first()
        agent.local_balance_micro_usdc = 100  # $0.0001
        db.commit()
        svc_infer = db.query(ApiService).filter(ApiService.id == "svc_infer").first()

        hc = TestClient(app, base_url="http://api.tollrail402.local")
        sdk = TollRailAgentClient(hc)
        trace = sdk.execute_paid_request(db, agent=agent, service=svc_infer, settlement_mode="exact")

        assert trace["success"] is False
        assert "Insufficient balance" in trace["api_response"]["reason"]
    finally:
        db.close()


def test_09_channel_voucher_verification_batch_settle_and_close():
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == "agt_telemetry_02").first()
        svc_weather = db.query(ApiService).filter(ApiService.id == "svc_weather").first()  # $0.003

        hc = TestClient(app, base_url="http://api.tollrail402.local")
        sdk = TollRailAgentClient(hc)
        t1 = sdk.execute_paid_request(db, agent=agent, service=svc_weather, settlement_mode="channel")
        t2 = sdk.execute_paid_request(db, agent=agent, service=svc_weather, settlement_mode="channel")

        assert t1["success"] is True
        assert t2["success"] is True

        # Check cumulative voucher state & batch settle
        channel = agent.channels[0]
        db.refresh(channel)
        assert channel.last_nonce == 2
        assert channel.cumulative_spent_micro == 6000

        settle_res = ChannelService.batch_settle(db, channel)
        assert settle_res["settled_vouchers"] == 2
        assert settle_res["settled_amount_usdc"] == 0.006

        closed = ChannelService.close_channel(db, channel, "Test closure")
        assert closed.status == "closed"
    finally:
        db.close()


def test_10_audit_record_generation_and_no_silent_testnet_fallback():
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == "agt_research_01").first()
        svc = db.query(ApiService).filter(ApiService.id == "svc_infer").first()

        hc = TestClient(app, base_url="http://api.tollrail402.local")
        sdk = TollRailAgentClient(hc)
        trace = sdk.execute_paid_request(db, agent=agent, service=svc, settlement_mode="exact")

        events = [
            a.event_type
            for a in db.query(AuditLog).filter(AuditLog.trace_id == trace["trace_id"]).order_by(AuditLog.id.asc()).all()
        ]
        for required in ["REQUEST_RECEIVED", "PAYMENT_REQUIRED", "POLICY_APPROVED", "PAYMENT_SUBMITTED", "PAYMENT_VERIFIED", "SERVICE_DELIVERED", "SETTLED"]:
            assert required in events

        # Verify TestNet mode refuses to accept a payment without a confirmed blockchain tx ID
        db.merge(PlatformSetting(key="tollrail_mode", value="algorand_testnet"))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    r1 = client.post("/v1/infer", json={"prompt": "testnet"})
    pr = _decode_header(r1.headers["PAYMENT-REQUIRED"])
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == "agt_research_01").first()
        sig_header = _sign_challenge_for_agent(db, agent, pr)
    finally:
        db.close()

    r2 = client.post("/v1/infer", json={"prompt": "testnet"}, headers={"PAYMENT-SIGNATURE": sig_header})
    assert r2.status_code == 402
    assert "no silent fallback" in r2.json()["detail"]["reason"].lower()
