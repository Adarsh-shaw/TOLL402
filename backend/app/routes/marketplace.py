import math
import statistics
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.middleware.payment_middleware import require_x402_payment
from backend.app.models.models import ApiService
from backend.app.schemas.schemas import ApiServiceResponse, micro_to_usdc

router = APIRouter(tags=["Marketplace & Paid APIs"])


@router.get("/api/marketplace/services", response_model=list[ApiServiceResponse])
def list_marketplace_services(db: Session = Depends(get_db)):
    services = db.query(ApiService).order_by(ApiService.price_micro_usdc.asc()).all()
    return [
        ApiServiceResponse(
            id=s.id,
            name=s.name,
            category=s.category,
            description=s.description,
            endpoint=s.endpoint,
            method=s.method,
            host=s.host,
            price_micro_usdc=s.price_micro_usdc,
            price_usdc=micro_to_usdc(s.price_micro_usdc),
            asset_id=s.asset_id,
            asset_symbol=s.asset_symbol,
            network=s.network,
            provider_name=s.provider_name,
            recipient_address=s.recipient_address,
            is_available=s.is_available,
            sample_payload=s.sample_payload,
        )
        for s in services
    ]


# ---- Genuine HTTP 402 Protected API Endpoints ----

@router.post("/v1/infer")
def protected_ai_inference(
    payload: dict[str, Any] = Body(default={"prompt": "Summarize agentic payment rails on Algorand", "max_tokens": 120}),
    payment_ctx: dict = Depends(require_x402_payment("/v1/infer")),
):
    prompt = str(payload.get("prompt") or "Summarize agentic payment rails on Algorand")
    max_tokens = int(payload.get("max_tokens") or 120)
    tx = payment_ctx["transaction"]
    word_count = len(prompt.split())

    completion = (
        f"Inference report for query ({word_count} words): Autonomous agents settle micro-invoices "
        f"using HTTP 402 challenges, Ed25519 signature proofs, and Algorand USDC (ASA {tx.asset_id}). "
        f"Sub-4s finality allows per-call settlement without human approval bottlenecks."
    )
    return {
        "status": "delivered",
        "service": "AI Text Generation API",
        "model": "tollrail-text-v1",
        "input_prompt": prompt,
        "output": completion[: max(80, max_tokens * 4)],
        "usage": {
            "prompt_tokens": max(8, word_count * 2),
            "completion_tokens": min(max_tokens, 42),
        },
        "payment_receipt": payment_ctx["payment_response"].model_dump(),
        "delivered_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/v1/analyze")
def protected_data_analysis(
    payload: dict[str, Any] = Body(default={"series": [12.4, 15.1, 14.8, 18.2, 21.0, 19.7], "metric": "throughput_rps"}),
    payment_ctx: dict = Depends(require_x402_payment("/v1/analyze")),
):
    raw_series = payload.get("series") or [12.4, 15.1, 14.8, 18.2, 21.0, 19.7]
    values = [float(x) for x in raw_series if isinstance(x, (int, float))]
    if not values:
        values = [1.0, 2.0, 3.0]

    mean_val = round(statistics.mean(values), 4)
    median_val = round(statistics.median(values), 4)
    stdev_val = round(statistics.stdev(values), 4) if len(values) > 1 else 0.0
    trend_pct = round(((values[-1] - values[0]) / abs(values[0])) * 100, 2) if len(values) > 1 and values[0] != 0 else 0.0

    return {
        "status": "delivered",
        "service": "Data Analysis API",
        "metric": payload.get("metric", "series"),
        "statistics": {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": mean_val,
            "median": median_val,
            "std_dev": stdev_val,
            "trend_percent": trend_pct,
        },
        "payment_receipt": payment_ctx["payment_response"].model_dump(),
        "delivered_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/v1/weather")
def protected_weather_info(
    city: str = Query(default="Zurich"),
    payment_ctx: dict = Depends(require_x402_payment("/v1/weather")),
):
    seed = sum(ord(c) for c in city.lower())
    temp_c = round(11.0 + (seed % 18) + 0.4, 1)
    humidity = 45 + (seed % 38)
    wind_kph = round(6.5 + (seed % 19) * 0.8, 1)
    conditions = ["Clear Sky", "Partly Cloudy", "Light Breeze", "Overcast"][seed % 4]

    return {
        "status": "delivered",
        "service": "Weather Information API",
        "location": city,
        "observation": {
            "temperature_c": temp_c,
            "humidity_percent": humidity,
            "wind_kph": wind_kph,
            "condition": conditions,
            "pressure_hpa": 1008 + (seed % 18),
        },
        "payment_receipt": payment_ctx["payment_response"].model_dump(),
        "delivered_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/v1/image-process")
def protected_image_processing(
    payload: dict[str, Any] = Body(default={"width": 1920, "height": 1080, "operation": "edge_detect", "format": "png"}),
    payment_ctx: dict = Depends(require_x402_payment("/v1/image-process")),
):
    width = int(payload.get("width") or 1920)
    height = int(payload.get("height") or 1080)
    operation = str(payload.get("operation") or "edge_detect")
    megapixels = round((width * height) / 1_000_000, 2)

    return {
        "status": "delivered",
        "service": "Image Processing API",
        "pipeline": {
            "operation": operation,
            "input_dimensions": f"{width}x{height}",
            "megapixels": megapixels,
            "output_format": payload.get("format", "png"),
            "checksum_sha256_prefix": f"img_{int(math.fabs(width * height)) % 999999:06d}",
        },
        "payment_receipt": payment_ctx["payment_response"].model_dump(),
        "delivered_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/v1/sensors")
def protected_sensor_data(
    zone: str = Query(default="grid-sector-a"),
    payment_ctx: dict = Depends(require_x402_payment("/v1/sensors")),
):
    now = datetime.now(timezone.utc)
    sec = now.second
    return {
        "status": "delivered",
        "service": "Sensor Data API",
        "zone": zone,
        "readings": [
            {"sensor_id": "node-temp-01", "metric": "celsius", "value": round(22.1 + (sec % 7) * 0.2, 2)},
            {"sensor_id": "node-volt-02", "metric": "volts", "value": round(230.4 + (sec % 5) * 0.1, 2)},
            {"sensor_id": "node-flow-03", "metric": "l_min", "value": round(14.8 + (sec % 9) * 0.15, 2)},
        ],
        "payment_receipt": payment_ctx["payment_response"].model_dump(),
        "delivered_at": now.isoformat(),
    }
