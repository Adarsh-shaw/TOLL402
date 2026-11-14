"""
TollRail402 Payment Channel Escrow Smart Contract (Algorand Python / Puya)

This contract implements a unidirectional USDC (ASA) payment channel escrow on Algorand:
1. Agent opens channel and funds the contract's escrow with USDC via an AssetTransferTxn.
2. Agent signs off-chain cumulative Ed25519 vouchers: (channel_id, nonce, cumulative_amount_micro).
3. API Provider (recipient) can settle the highest cumulative voucher at any time using Algorand's
   native `op.ed25519verify_bare` opcode to verify the agent's signature on-chain.
4. Once settled or after expiration round, remaining unspent USDC is returned to the agent.

To compile with Puya (`algopy`):
    pip install algorand-python puyapy
    puyapy contracts/payment_escrow.py --out-dir contracts/build
"""

try:
    from algopy import (
        ARC4Contract,
        Asset,
        Bytes,
        Global,
        Txn,
        UInt64,
        arc4,
        gtxn,
        itxn,
        op,
    )

    class TollRailPaymentEscrow(ARC4Contract):
        """On-chain Algorand USDC payment channel escrow for TollRail402."""

        def __init__(self) -> None:
            self.payer = Global.zero_address
            self.recipient = Global.zero_address
            self.asset_id = UInt64(0)
            self.deposited_amount = UInt64(0)
            self.settled_amount = UInt64(0)
            self.last_nonce = UInt64(0)
            self.expiry_round = UInt64(0)
            self.channel_open = UInt64(0)

        @arc4.abimethod(create="require")
        def initialize_channel(
            self,
            recipient: arc4.Address,
            usdc_asset: Asset,
            duration_rounds: UInt64,
        ) -> None:
            self.payer = Txn.sender
            self.recipient = recipient.native
            self.asset_id = usdc_asset.id
            self.expiry_round = Global.round + duration_rounds
            self.channel_open = UInt64(1)

        @arc4.abimethod
        def opt_in_asset(self, usdc_asset: Asset) -> None:
            assert Txn.sender == self.payer, "Only channel payer may trigger asset opt-in"
            assert usdc_asset.id == self.asset_id, "Asset ID mismatch"
            itxn.AssetTransfer(
                xfer_asset=usdc_asset,
                asset_receiver=Global.current_application_address,
                asset_amount=0,
                fee=0,
            ).submit()

        @arc4.abimethod
        def deposit(self, axfer: gtxn.AssetTransferTransaction) -> None:
            assert self.channel_open == UInt64(1), "Channel is closed"
            assert axfer.sender == self.payer, "Deposit must come from payer"
            assert axfer.asset_receiver == Global.current_application_address, "Must fund contract escrow"
            assert axfer.xfer_asset.id == self.asset_id, "Invalid ASA asset"
            assert axfer.asset_amount > UInt64(0), "Deposit must be positive"
            self.deposited_amount += axfer.asset_amount

        @arc4.abimethod
        def settle_voucher(
            self,
            nonce: UInt64,
            cumulative_amount: UInt64,
            voucher_message: Bytes,
            ed25519_signature: Bytes,
        ) -> None:
            assert self.channel_open == UInt64(1), "Channel is closed"
            assert Txn.sender == self.recipient, "Only recipient may claim voucher"
            assert nonce > self.last_nonce, "Stale or duplicate voucher nonce"
            assert cumulative_amount > self.settled_amount, "No new funds to settle"
            assert cumulative_amount <= self.deposited_amount, "Voucher exceeds escrow deposit"

            # Native AVM Ed25519 signature verification against payer's 32-byte public key
            assert op.ed25519verify_bare(
                voucher_message,
                ed25519_signature,
                self.payer.bytes,
            ), "Invalid Ed25519 voucher signature"

            payout = cumulative_amount - self.settled_amount
            self.settled_amount = cumulative_amount
            self.last_nonce = nonce

            itxn.AssetTransfer(
                xfer_asset=Asset(self.asset_id),
                asset_receiver=self.recipient,
                asset_amount=payout,
                fee=0,
            ).submit()

        @arc4.abimethod
        def close_and_refund(self) -> None:
            assert self.channel_open == UInt64(1), "Channel already closed"
            is_recipient = Txn.sender == self.recipient
            is_expired_payer = (Txn.sender == self.payer) and (Global.round >= self.expiry_round)
            assert is_recipient or is_expired_payer, "Only recipient or expired payer may close"

            unspent = self.deposited_amount - self.settled_amount
            self.channel_open = UInt64(0)
            if unspent > UInt64(0):
                itxn.AssetTransfer(
                    xfer_asset=Asset(self.asset_id),
                    asset_receiver=self.payer,
                    asset_amount=unspent,
                    fee=0,
                ).submit()

except ImportError:
    # Allows inspecting contract source in environments where puya/algopy compiler is not installed
    TollRailPaymentEscrow = None  # type: ignore
