from dataclasses import dataclass
from algosdk import logic

from backend.app.blockchain.algorand_client import AlgorandClient


@dataclass
class EscrowStatus:
    escrow_app_id: int
    escrow_address: str
    is_onchain_escrow: bool
    mode_label: str
    details: str


class EscrowClient:
    """
    Interfaces with the TollRail402 Algorand payment channel escrow smart contract.
    Clearly distinguishes deployed on-chain TestNet smart contract escrow from Local Development Mode.
    """

    def __init__(self, client: AlgorandClient | None = None) -> None:
        self.client = client or AlgorandClient()

    def inspect_escrow(self, escrow_app_id: int, execution_mode: str) -> EscrowStatus:
        if execution_mode == "algorand_testnet" and escrow_app_id > 0:
            try:
                app_info = self.client.algod.application_info(escrow_app_id)
                app_address = logic.get_application_address(escrow_app_id)
                creator = app_info.get("params", {}).get("creator", "unknown")
                return EscrowStatus(
                    escrow_app_id=escrow_app_id,
                    escrow_address=app_address,
                    is_onchain_escrow=True,
                    mode_label="Algorand TestNet Smart Contract Escrow",
                    details=f"Verified deployed App ID {escrow_app_id} (creator {creator[:8]}...)",
                )
            except Exception as exc:
                return EscrowStatus(
                    escrow_app_id=escrow_app_id,
                    escrow_address=logic.get_application_address(escrow_app_id),
                    is_onchain_escrow=False,
                    mode_label="Escrow Contract Unreachable on TestNet",
                    details=f"Configured App ID {escrow_app_id} could not be queried: {exc}",
                )

        return EscrowStatus(
            escrow_app_id=0,
            escrow_address="local-dev-channel-ledger",
            is_onchain_escrow=False,
            mode_label="Local Development Channel Mode (off-chain Ed25519 vouchers; contract not deployed)",
            details="Vouchers are cryptographically signed with Ed25519 and tracked locally. Deploy contracts/payment_escrow.py to TestNet for on-chain escrow.",
        )
