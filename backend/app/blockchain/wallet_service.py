import base64
import hashlib
import json
from typing import Any

from algosdk import account, encoding, mnemonic, util
from cryptography.fernet import Fernet, InvalidToken
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from backend.app.config import get_settings


def _get_fernet() -> Fernet:
    secret = get_settings().tollrail_key_encryption_secret.encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


class WalletService:
    """Manages Algorand Ed25519 wallets, encrypted key storage, and canonical payload signing."""

    @staticmethod
    def generate_wallet() -> tuple[str, str]:
        """Returns (private_key_b64, algorand_address)."""
        private_key, address = account.generate_account()
        return private_key, address

    @staticmethod
    def import_from_mnemonic(mnemonic_phrase: str) -> tuple[str, str]:
        private_key = mnemonic.to_private_key(mnemonic_phrase.strip())
        address = account.address_from_private_key(private_key)
        return private_key, address

    @staticmethod
    def is_valid_address(address: str) -> bool:
        try:
            return bool(address and encoding.is_valid_address(address.strip()))
        except Exception:
            return False

    @staticmethod
    def encrypt_private_key(private_key: str) -> str:
        f = _get_fernet()
        return f.encrypt(private_key.encode("utf-8")).decode("utf-8")

    @staticmethod
    def decrypt_private_key(encrypted_material: str) -> str:
        f = _get_fernet()
        try:
            return f.decrypt(encrypted_material.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt agent key material; check TOLLRAIL_KEY_ENCRYPTION_SECRET") from exc

    @staticmethod
    def canonical_payment_message(payload: dict[str, Any]) -> bytes:
        """Deterministic canonical JSON serialization for Ed25519 payment & voucher signing."""
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return canonical.encode("utf-8")

    @staticmethod
    def sign_message(private_key_b64: str, message: bytes) -> str:
        """Signs arbitrary bytes with Algorand Ed25519 keypair and returns base64 signature."""
        sk_bytes = base64.b64decode(private_key_b64)
        # Algorand SDK stores 64-byte key (32-byte seed + 32-byte pubkey)
        signing_key = SigningKey(sk_bytes[:32])
        signed = signing_key.sign(message)
        return base64.b64encode(signed.signature).decode("utf-8")

    @staticmethod
    def verify_signature(algorand_address: str, message: bytes, signature_b64: str) -> bool:
        """Verifies Ed25519 signature against the 32-byte public key encoded in the Algorand address."""
        try:
            if not WalletService.is_valid_address(algorand_address):
                return False
            pub_bytes = encoding.decode_address(algorand_address)
            sig_bytes = base64.b64decode(signature_b64)
            if len(sig_bytes) != 64:
                return False
            verify_key = VerifyKey(pub_bytes)
            verify_key.verify(message, sig_bytes)
            return True
        except (BadSignatureError, ValueError, Exception):
            return False

    @staticmethod
    def sign_algorand_txn(private_key_b64: str, txn) -> Any:
        return txn.sign(private_key_b64)

    @staticmethod
    def address_from_private_key(private_key_b64: str) -> str:
        return account.address_from_private_key(private_key_b64)

    @staticmethod
    def sign_bytes_sdk(private_key_b64: str, data: bytes) -> str:
        return util.sign_bytes(data, private_key_b64)
