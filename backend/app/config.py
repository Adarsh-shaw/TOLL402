import os
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
_DEFAULT_SQLITE_PATH = (
    Path("/tmp/tollrail402.db")
    if (os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))
    else (ROOT_DIR / "tollrail402.db")
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Operating Mode: "local_demo" or "algorand_testnet"
    tollrail_mode: str = "local_demo"

    # Database URL (PostgreSQL preferred, SQLite fallback)
    database_url: str = f"sqlite:///{_DEFAULT_SQLITE_PATH}"

    # Key encryption secret (used to encrypt agent private keys at rest)
    tollrail_key_encryption_secret: str = "tollrail402-local-dev-secret-key-change-me"

    # Algorand TestNet configuration
    algod_address: str = "https://testnet-api.algonode.cloud"
    algod_token: str = ""
    indexer_address: str = "https://testnet-idx.algonode.cloud"
    indexer_token: str = ""
    algorand_network: str = "algorand:testnet"

    # Circle TestNet USDC ASA ID
    usdc_asset_id: int = 10458941

    # Merchant / API provider wallet address
    merchant_algorand_address: str = ""

    # Optional deployed escrow smart contract App ID
    escrow_app_id: int = 0

    # Protocol & security defaults
    protocol_version: str = "x402/1.0"
    challenge_ttl_seconds: int = 120
    rate_limit_requests_per_minute: int = 120

    host: str = "0.0.0.0"
    port: int = 3000


@lru_cache
def get_settings() -> Settings:
    return Settings()
