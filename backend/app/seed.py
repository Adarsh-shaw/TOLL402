from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.app.blockchain.wallet_service import WalletService
from backend.app.config import get_settings
from backend.app.models.models import Agent, ApiService, PlatformSetting
from backend.app.services.agent_service import get_merchant_address, get_usdc_asset_id
from backend.app.services.audit_service import AuditService
from backend.app.services.channel_service import ChannelService


def seed_initial_data(db: Session) -> None:
    """Seeds initial marketplace services, demo agents, and a demo payment channel if the database is empty."""
    settings = get_settings()

    # Ensure mode setting exists
    if not db.query(PlatformSetting).filter(PlatformSetting.key == "tollrail_mode").first():
        db.add(PlatformSetting(key="tollrail_mode", value=settings.tollrail_mode))
        db.commit()

    merchant_addr = get_merchant_address(db)
    usdc_asset_id = get_usdc_asset_id(db)

    if db.query(ApiService).count() == 0:
        services = [
            ApiService(
                id="svc_infer",
                name="AI Text Generation API",
                category="Inference",
                description="Low-latency structured text completion and synthesis endpoint billed per call.",
                endpoint="/v1/infer",
                method="POST",
                host="api.tollrail402.local",
                price_micro_usdc=5_000,  # $0.005
                asset_id=usdc_asset_id,
                asset_symbol="USDC",
                network=settings.algorand_network,
                provider_name="TollRail Compute Node",
                recipient_address=merchant_addr,
                is_available=True,
                sample_payload={
                    "prompt": "Explain how autonomous agents settle API invoices on Algorand using HTTP 402.",
                    "max_tokens": 120,
                },
            ),
            ApiService(
                id="svc_analyze",
                name="Data Analysis API",
                category="Analytics",
                description="Computes descriptive statistics, variance, and directional trend metrics over numeric vectors.",
                endpoint="/v1/analyze",
                method="POST",
                host="api.tollrail402.local",
                price_micro_usdc=8_000,  # $0.008
                asset_id=usdc_asset_id,
                asset_symbol="USDC",
                network=settings.algorand_network,
                provider_name="QuantMesh Labs",
                recipient_address=merchant_addr,
                is_available=True,
                sample_payload={
                    "metric": "settlement_latency_ms",
                    "series": [340, 312, 298, 305, 289, 275],
                },
            ),
            ApiService(
                id="svc_weather",
                name="Weather Information API",
                category="Geospatial",
                description="Real-time meteorological station readings including temperature, pressure, and wind speed.",
                endpoint="/v1/weather",
                method="GET",
                host="api.tollrail402.local",
                price_micro_usdc=3_000,  # $0.003
                asset_id=usdc_asset_id,
                asset_symbol="USDC",
                network=settings.algorand_network,
                provider_name="Alpine Meteo Feeds",
                recipient_address=merchant_addr,
                is_available=True,
                sample_payload={"city": "Zurich"},
            ),
            ApiService(
                id="svc_image",
                name="Image Processing API",
                category="Vision",
                description="High-throughput raster transformation and feature extraction pipeline for media payloads.",
                endpoint="/v1/image-process",
                method="POST",
                host="api.tollrail402.local",
                price_micro_usdc=15_000,  # $0.015 (exceeds default $0.01 policy limit for testing!)
                asset_id=usdc_asset_id,
                asset_symbol="USDC",
                network=settings.algorand_network,
                provider_name="PixelRail Infrastructure",
                recipient_address=merchant_addr,
                is_available=True,
                sample_payload={
                    "width": 1920,
                    "height": 1080,
                    "operation": "edge_detect",
                    "format": "png",
                },
            ),
            ApiService(
                id="svc_sensors",
                name="Sensor Data API",
                category="IoT Telemetry",
                description="Aggregated industrial telemetry stream from distributed voltage, thermal, and flow nodes.",
                endpoint="/v1/sensors",
                method="GET",
                host="api.tollrail402.local",
                price_micro_usdc=4_000,  # $0.004
                asset_id=usdc_asset_id,
                asset_symbol="USDC",
                network=settings.algorand_network,
                provider_name="GridPulse Telemetry",
                recipient_address=merchant_addr,
                is_available=True,
                sample_payload={"zone": "grid-sector-a"},
            ),
        ]
        db.add_all(services)
        db.commit()

    if db.query(Agent).count() == 0:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        sk1, addr1 = WalletService.generate_wallet()
        sk2, addr2 = WalletService.generate_wallet()
        sk3, addr3 = WalletService.generate_wallet()

        agent1 = Agent(
            id="agt_research_01",
            name="Research Summarizer Agent",
            description="Autonomous retrieval & synthesis agent configured with strict $0.01 per-call cap.",
            wallet_address=addr1,
            encrypted_key_material=WalletService.encrypt_private_key(sk1),
            local_balance_micro_usdc=2_000_000,  # $2.00
            per_request_limit_micro=10_000,      # $0.01
            daily_limit_micro=5_000_000,         # $5.00
            daily_spent_micro=0,
            daily_reset_date=today_str,
            allowed_hosts=["api.tollrail402.local", "localhost", "127.0.0.1"],
            default_settlement_mode="exact",
            is_active=True,
            network=settings.algorand_network,
        )
        agent2 = Agent(
            id="agt_telemetry_02",
            name="High-Frequency Telemetry Agent",
            description="Streams weather and IoT sensor feeds over cumulative Ed25519 payment channels.",
            wallet_address=addr2,
            encrypted_key_material=WalletService.encrypt_private_key(sk2),
            local_balance_micro_usdc=3_500_000,  # $3.50
            per_request_limit_micro=10_000,      # $0.01
            daily_limit_micro=10_000_000,        # $10.00
            daily_spent_micro=0,
            daily_reset_date=today_str,
            allowed_hosts=["api.tollrail402.local", "localhost", "127.0.0.1"],
            default_settlement_mode="channel",
            is_active=True,
            network=settings.algorand_network,
        )
        agent3 = Agent(
            id="agt_vision_03",
            name="Vision Pipeline Agent",
            description="Authorized for higher-cost image processing endpoints up to $0.025 per call.",
            wallet_address=addr3,
            encrypted_key_material=WalletService.encrypt_private_key(sk3),
            local_balance_micro_usdc=4_000_000,  # $4.00
            per_request_limit_micro=25_000,      # $0.025
            daily_limit_micro=15_000_000,        # $15.00
            daily_spent_micro=0,
            daily_reset_date=today_str,
            allowed_hosts=["api.tollrail402.local", "localhost", "127.0.0.1"],
            default_settlement_mode="exact",
            is_active=True,
            network=settings.algorand_network,
        )
        db.add_all([agent1, agent2, agent3])
        db.commit()

        AuditService.record_event(
            db,
            trace_id="trace_bootstrap",
            event_type="PLATFORM_INITIALIZED",
            status="info",
            message="Initialized TollRail402 marketplace services and 3 autonomous demo agents.",
            commit=True,
        )

        # Open a default voucher channel for agent2 in Local Demo Mode
        ChannelService.create_channel(db, agent2, deposit_usdc=1.0, recipient_address=merchant_addr)


def execute_bootstrap_transactions(app) -> None:
    """
    Runs 2 genuine HTTP 402 SDK calls on first boot if zero transactions exist,
    so the Overview Dashboard and Transaction Explorer reflect real executed protocol traces.
    """
    from fastapi.testclient import TestClient
    from backend.app.database import SessionLocal
    from backend.app.models.models import PaymentTransaction
    from backend.app.sdk.agent_client import TollRailAgentClient

    db = SessionLocal()
    try:
        if db.query(PaymentTransaction).count() > 0:
            return
        agent1 = db.query(Agent).filter(Agent.id == "agt_research_01").first()
        agent2 = db.query(Agent).filter(Agent.id == "agt_telemetry_02").first()
        svc_infer = db.query(ApiService).filter(ApiService.id == "svc_infer").first()
        svc_weather = db.query(ApiService).filter(ApiService.id == "svc_weather").first()

        if not (agent1 and agent2 and svc_infer and svc_weather):
            return

        client = TestClient(
            app,
            base_url="http://api.tollrail402.local",
            headers={"X-TollRail-Bootstrap": "1"},
        )
        sdk = TollRailAgentClient(client)
        sdk.execute_paid_request(db, agent=agent1, service=svc_infer, settlement_mode="exact")
        sdk.execute_paid_request(db, agent=agent2, service=svc_weather, settlement_mode="channel")
    finally:
        db.close()
