from dataclasses import dataclass
from algosdk import transaction

from backend.app.blockchain.algorand_client import AlgorandClient


@dataclass
class OnChainVerificationResult:
    verified: bool
    tx_id: str | None
    confirmed_round: int | None
    reason: str


class TransactionVerifier:
    """Submits and verifies real USDC ASA payments on Algorand TestNet."""

    def __init__(self, client: AlgorandClient | None = None) -> None:
        self.client = client or AlgorandClient()

    def submit_usdc_transfer(
        self,
        private_key_b64: str,
        sender_address: str,
        recipient_address: str,
        amount_micro_usdc: int,
        asset_id: int,
        note_text: str,
    ) -> str:
        """Builds, signs, submits, and waits for confirmation of an Algorand TestNet USDC ASA transfer."""
        sp = self.client.algod.suggested_params()
        txn = transaction.AssetTransferTxn(
            sender=sender_address,
            sp=sp,
            receiver=recipient_address,
            amt=amount_micro_usdc,
            index=asset_id,
            note=note_text.encode("utf-8"),
        )
        signed_txn = txn.sign(private_key_b64)
        tx_id = self.client.algod.send_transaction(signed_txn)
        transaction.wait_for_confirmation(self.client.algod, tx_id, 6)
        return tx_id

    def verify_usdc_transfer_onchain(
        self,
        tx_id: str,
        expected_sender: str,
        expected_recipient: str,
        expected_asset_id: int,
        min_amount_micro_usdc: int,
    ) -> OnChainVerificationResult:
        """Queries Algorand TestNet (Indexer / Algod pending) to verify a confirmed ASA transfer."""
        if not tx_id:
            return OnChainVerificationResult(False, None, None, "Missing blockchain transaction ID for Algorand TestNet verification")

        try:
            # First check algod pending/transaction info, then indexer
            tx_info = None
            try:
                pending = self.client.algod.pending_transaction_info(tx_id)
                if pending and pending.get("confirmed-round", 0) > 0:
                    tx_info = self._normalize_algod_pending(tx_id, pending)
            except Exception:
                tx_info = None

            if tx_info is None:
                res = self.client.indexer.transaction(tx_id)
                tx_info = res.get("transaction")

            if not tx_info:
                return OnChainVerificationResult(False, tx_id, None, "Transaction not found on Algorand TestNet")

            confirmed_round = tx_info.get("confirmed-round", 0)
            if not confirmed_round or confirmed_round <= 0:
                return OnChainVerificationResult(False, tx_id, None, "Transaction is not yet confirmed on Algorand TestNet")

            if tx_info.get("tx-type") != "axfer":
                return OnChainVerificationResult(False, tx_id, confirmed_round, "Transaction is not an Algorand Standard Asset transfer (axfer)")

            sender = tx_info.get("sender")
            axfer = tx_info.get("asset-transfer-transaction", {})
            receiver = axfer.get("receiver")
            asset_id = axfer.get("asset-id")
            amount = int(axfer.get("amount", 0))

            if sender != expected_sender:
                return OnChainVerificationResult(False, tx_id, confirmed_round, f"Sender mismatch: expected {expected_sender}, got {sender}")
            if receiver != expected_recipient:
                return OnChainVerificationResult(False, tx_id, confirmed_round, f"Recipient mismatch: expected {expected_recipient}, got {receiver}")
            if asset_id != expected_asset_id:
                return OnChainVerificationResult(False, tx_id, confirmed_round, f"Asset ID mismatch: expected {expected_asset_id}, got {asset_id}")
            if amount < min_amount_micro_usdc:
                return OnChainVerificationResult(False, tx_id, confirmed_round, f"Insufficient payment amount: expected {min_amount_micro_usdc} microUSDC, got {amount}")

            return OnChainVerificationResult(
                True,
                tx_id,
                confirmed_round,
                f"Confirmed on Algorand TestNet at round {confirmed_round}",
            )
        except Exception as exc:
            return OnChainVerificationResult(False, tx_id, None, f"Algorand TestNet verification error: {exc}")

    @staticmethod
    def _normalize_algod_pending(tx_id: str, pending: dict) -> dict:
        txn = pending.get("txn", {}).get("txn", {})
        return {
            "id": tx_id,
            "confirmed-round": pending.get("confirmed-round", 0),
            "tx-type": txn.get("type"),
            "sender": txn.get("snd"),
            "asset-transfer-transaction": {
                "receiver": txn.get("arcv"),
                "asset-id": txn.get("xaid"),
                "amount": txn.get("aamt", 0),
            },
        }
