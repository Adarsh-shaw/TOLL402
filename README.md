# TollRail402 — Agentic Payment Rails on Algorand

TollRail402 is a functional payment infrastructure platform demonstrating how autonomous AI agents pay for API requests automatically using the **HTTP 402 Payment Required** protocol, **Ed25519 digital signatures**, and **USDC on Algorand TestNet**.

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy
- **Frontend**: HTML5, CSS3, Vanilla JavaScript, Chart.js
- **Database**: PostgreSQL (preferred) or SQLite (local fallback)
- **Blockchain**: Algorand TestNet (`py-algorand-sdk`, Algorand Python `contracts/payment_escrow.py`, USDC ASA `10458941`, Ed25519 via PyNaCl)

## Quick Start

### 1. Python Environment & Dependencies
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Configuration
```bash
cp .env.example .env
```
Key settings in `.env`:
- `TOLLRAIL_MODE`: `local_demo` (default) or `algorand_testnet`
- `DATABASE_URL`: SQLite (`sqlite:///./tollrail402.db`) or PostgreSQL (`postgresql+psycopg2://user:pass@localhost:5432/tollrail402`)
- `USDC_ASSET_ID`: `10458941` (Circle TestNet USDC)
- `TOLLRAIL_KEY_ENCRYPTION_SECRET`: Server secret used to encrypt agent private keys at rest

### 3. Database Setup
Tables and initial demo entities (5 paid APIs, 3 autonomous agents, 1 open payment channel, and 2 bootstrap HTTP 402 traces) are initialized automatically on server startup via SQLAlchemy.
For PostgreSQL:
```bash
createdb tollrail402
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/tollrail402"
```

### 4. Start the Application (Backend + Frontend on Port 3000)
```bash
python run.py --port 3000 --host 0.0.0.0
```
Open `http://localhost:3000` in your browser.

## Sample Demo Agents (Pre-seeded on First Boot)
| Agent ID | Name | Per-Req Cap | Daily Cap | Default Mode |
| --- | --- | --- | --- | --- |
| `agt_research_01` | Research Summarizer Agent | `$0.0100` | `$5.00` | `exact` |
| `agt_telemetry_02` | High-Frequency Telemetry Agent | `$0.0100` | `$10.00` | `channel` |
| `agt_vision_03` | Vision Pipeline Agent | `$0.0250` | `$15.00` | `exact` |

> **Demo Tip**: Run `POST /v1/infer` (`$0.005`) with `agt_research_01` to see an approved HTTP 402 settlement. Then run `POST /v1/image-process` (`$0.015`) with `agt_research_01` to watch the Policy Engine reject the transaction before any payment is signed.

## Algorand TestNet Setup Guide
1. Switch `TOLLRAIL_MODE=algorand_testnet` in `.env` or via the **Settings** page.
2. Fund your agent's Algorand TestNet address with TestNet ALGO (for transaction fees) and TestNet USDC (ASA `10458941`) and opt the agent and merchant accounts into ASA `10458941`.
3. Note: TestNet mode strictly verifies on-chain confirmations via Algod/Indexer and **never** silently falls back to local simulated payments.
4. To deploy the payment channel escrow contract (`contracts/payment_escrow.py`), compile with `puyapy`, deploy to TestNet, and configure `ESCROW_APP_ID` in `.env` or Settings.

## Running Backend Tests
```bash
.venv/bin/pytest -v backend/app/tests/test_tollrail402.py
```

## Troubleshooting
- **Port 3000 in use**: Pass `--port 3001` to `run.py` or stop the conflicting process.
- **TestNet mode returns HTTP 402 missing tx/insufficient ALGO**: Ensure the agent wallet is funded on TestNet and opted into USDC ASA `10458941`, or switch back to `local_demo` in Settings for offline demonstrations.
- **Database lock or schema reset**: Delete `tollrail402.db` in Local Demo Mode and restart `run.py` to re-initialize cleanly.
