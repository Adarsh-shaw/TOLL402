import threading
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.config import ROOT_DIR
from backend.app.database import SessionLocal, init_db
from backend.app.routes import (
    agents,
    audit,
    channels,
    dashboard,
    demo,
    marketplace,
    payments,
    policies,
    settings,
)
from backend.app.seed import execute_bootstrap_transactions, seed_initial_data
from backend.app.services.rate_limiter import SlidingWindowRateLimiter


_init_lock = threading.Lock()
_initialized = False


def ensure_app_initialized(fastapi_app: FastAPI) -> None:
    """Thread-safe one-time initialization for both ASGI lifespan and serverless cold starts."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        init_db()
        db = SessionLocal()
        try:
            seed_initial_data(db)
        finally:
            db.close()
        execute_bootstrap_transactions(fastapi_app)
        _initialized = True


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    ensure_app_initialized(fastapi_app)
    yield


app = FastAPI(
    title="TollRail402 — Agentic Payment Rails on Algorand",
    description="Autonomous API micro-payments using HTTP 402, Ed25519 signatures, and Algorand TestNet USDC.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def lazy_init_middleware(request: Request, call_next):
    if not _initialized and request.headers.get("x-tollrail-bootstrap") != "1":
        ensure_app_initialized(request.app)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["PAYMENT-REQUIRED", "PAYMENT-RESPONSE", "X-TollRail-Trace-Id", "X-Payment-Error"],
)
app.add_middleware(SlidingWindowRateLimiter)

# Register API & Protected Service Routers
app.include_router(dashboard.router)
app.include_router(agents.router)
app.include_router(marketplace.router)
app.include_router(payments.router)
app.include_router(channels.router)
app.include_router(policies.router)
app.include_router(audit.router)
app.include_router(demo.router)
app.include_router(settings.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "TollRail402"}


# Serve Vanilla HTML/CSS/JS Frontend
FRONTEND_DIR = ROOT_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
    assets_dir = FRONTEND_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


@app.get("/", include_in_schema=False)
def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/{full_path:path}", include_in_schema=False)
def serve_spa_fallback(full_path: str):
    # Only serve index.html for non-API routes
    candidate = FRONTEND_DIR / full_path
    if candidate.is_file():
        return FileResponse(str(candidate))
    return FileResponse(str(FRONTEND_DIR / "index.html"))
