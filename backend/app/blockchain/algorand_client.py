from typing import Any
from algosdk.v2client import algod, indexer

from backend.app.config import get_settings


class AlgorandClient:
    """Wrapper around official Algorand Python SDK Algod and Indexer clients."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._algod = algod.AlgodClient(
            algod_token=self.settings.algod_token,
            algod_address=self.settings.algod_address,
            headers={"User-Agent": "TollRail402/1.0"} if not self.settings.algod_token else None,
        )
        self._indexer = indexer.IndexerClient(
            indexer_token=self.settings.indexer_token,
            indexer_address=self.settings.indexer_address,
            headers={"User-Agent": "TollRail402/1.0"} if not self.settings.indexer_token else None,
        )

    @property
    def algod(self) -> algod.AlgodClient:
        return self._algod

    @property
    def indexer(self) -> indexer.IndexerClient:
        return self._indexer

    def get_network_status(self) -> dict[str, Any]:
        try:
            status = self._algod.status()
            return {
                "connected": True,
                "network": self.settings.algorand_network,
                "algod_address": self.settings.algod_address,
                "last_round": status.get("last-round"),
                "time_since_last_round_ms": round(status.get("time-since-last-round", 0) / 1_000_000, 2),
                "catchup_time": status.get("catchup-time", 0),
                "error": None,
            }
        except Exception as exc:
            return {
                "connected": False,
                "network": self.settings.algorand_network,
                "algod_address": self.settings.algod_address,
                "last_round": None,
                "error": str(exc),
            }

    def get_account_balances(self, address: str, usdc_asset_id: int | None = None) -> dict[str, Any]:
        asset_id = usdc_asset_id or self.settings.usdc_asset_id
        try:
            info = self._algod.account_info(address)
            algo_micro = info.get("amount", 0)
            usdc_micro = 0
            usdc_opted_in = False
            for asset in info.get("assets", []):
                if asset.get("asset-id") == asset_id:
                    usdc_opted_in = True
                    usdc_micro = int(asset.get("amount", 0))
                    break
            return {
                "success": True,
                "address": address,
                "algo_micro": algo_micro,
                "algo": round(algo_micro / 1_000_000, 6),
                "usdc_asset_id": asset_id,
                "usdc_opted_in": usdc_opted_in,
                "usdc_micro": usdc_micro,
                "usdc": round(usdc_micro / 1_000_000, 6),
                "error": None,
            }
        except Exception as exc:
            return {
                "success": False,
                "address": address,
                "algo_micro": None,
                "algo": None,
                "usdc_asset_id": asset_id,
                "usdc_opted_in": False,
                "usdc_micro": None,
                "usdc": None,
                "error": str(exc),
            }

    def get_asset_details(self, asset_id: int | None = None) -> dict[str, Any]:
        aid = asset_id or self.settings.usdc_asset_id
        try:
            data = self._algod.asset_info(aid)
            params = data.get("params", {})
            return {
                "found": True,
                "asset_id": aid,
                "name": params.get("name", "USDC"),
                "unit_name": params.get("unit-name", "USDC"),
                "decimals": params.get("decimals", 6),
                "creator": params.get("creator"),
            }
        except Exception as exc:
            return {
                "found": False,
                "asset_id": aid,
                "error": str(exc),
            }

    def get_explorer_tx_url(self, tx_id: str | None) -> str | None:
        if not tx_id:
            return None
        return f"https://lora.algokit.io/testnet/transaction/{tx_id}"

    def get_explorer_address_url(self, address: str | None) -> str | None:
        if not address:
            return None
        return f"https://lora.algokit.io/testnet/account/{address}"
