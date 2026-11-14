# TollRail402 Protocol & System Architecture

## 1. HTTP 402 Request Lifecycle
1. Agent issues an HTTP request to a protected endpoint (e.g. `POST /v1/infer`) without payment authorization.
2. `payment_middleware.py` intercepts the request, logs `REQUEST_RECEIVED`, creates a `PaymentChallenge` with a unique `nonce` and expiration timestamp, and returns **HTTP 402 Payment Required** with Base64-encoded JSON in the `PAYMENT-REQUIRED` header.
3. The Agent SDK (`TollRailAgentClient`) decodes `PAYMENT-REQUIRED` and evaluates `PolicyEngine`:
   - Agent active status
   - Challenge expiration timestamp
   - Allowed API host matching
   - Per-request spending cap
   - Daily UTC spending cap
   - Available balance (local demo ledger, Algorand TestNet USDC + ALGO fee, or open channel deposit)
4. If approved (`POLICY_APPROVED`), the agent signs either:
   - **Exact Mode**: canonical JSON payment authorization with its Ed25519 key (and submits an on-chain Algorand TestNet `AssetTransferTxn` for USDC ASA `10458941` when `TOLLRAIL_MODE=algorand_testnet`).
   - **Channel Mode**: cumulative Ed25519 voucher `(channel_id, nonce, cumulative_amount_micro)`.
5. Agent retries the original HTTP request with the `PAYMENT-SIGNATURE` header.
6. Middleware verifies protocol version, challenge status, expiration, nonce uniqueness, asset ID, network, recipient, amount, Ed25519 signature, and on-chain/voucher validity.
7. Settlement runs atomically inside SQLAlchemy (`SettlementService`), records `PAYMENT_VERIFIED`, `SERVICE_DELIVERED`, and `SETTLED` in the append-only `AuditLog`, and returns **HTTP 200 OK** with the `PAYMENT-RESPONSE` receipt header.

## 2. Mode Isolation (Local Demo vs Algorand TestNet)
- `local_demo`: Real HTTP 402 challenges, real Ed25519 cryptographic signing/verification, real spending policy checks, and local SQLite/PostgreSQL balance settlement. Simulated settlements are marked `is_simulated=true` with `blockchain_tx_id=null`—no fake TXIDs are ever generated.
- `algorand_testnet`: Connects to Algorand TestNet Algod/Indexer, reads real ALGO & USDC balances, submits real USDC ASA transfers, verifies on-chain confirmations, and refuses to silently fall back to local simulation if a TestNet transaction is missing or unconfirmed.
