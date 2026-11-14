"""
Helper script to inspect Algorand TestNet deployment readiness for TollRailPaymentEscrow.

Usage:
    python contracts/deploy_escrow.py
"""

import os
from algosdk import account, mnemonic
from algosdk.v2client import algod


def main() -> None:
    algod_url = os.getenv("ALGOD_ADDRESS", "https://testnet-api.algonode.cloud")
    algod_token = os.getenv("ALGOD_TOKEN", "")
    client = algod.AlgodClient(algod_token, algod_url)

    status = client.status()
    print(f"Connected to Algorand TestNet (last round: {status.get('last-round')})")

    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    if not deployer_mnemonic:
        print(
            "DEPLOYER_MNEMONIC is not set. To deploy contracts/payment_escrow.py to Algorand TestNet:\n"
            "  1. Install Puya: pip install algorand-python puyapy\n"
            "  2. Compile: puyapy contracts/payment_escrow.py --out-dir contracts/build\n"
            "  3. Fund a TestNet deployer address via https://bank.testnet.algorand.network/\n"
            "  4. Export DEPLOYER_MNEMONIC and run your deployment transaction, then set ESCROW_APP_ID in .env."
        )
        return

    sk = mnemonic.to_private_key(deployer_mnemonic)
    addr = account.address_from_private_key(sk)
    info = client.account_info(addr)
    print(f"Deployer address: {addr} | ALGO balance: {info.get('amount', 0) / 1_000_000:.6f} ALGO")


if __name__ == "__main__":
    main()
