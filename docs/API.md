# TollRail402 REST API Reference

## Protected Paid API Endpoints (HTTP 402 Gated)
| Method | Endpoint | Default Price | Description |
| --- | --- | --- | --- |
| `POST` | `/v1/infer` | `0.005 USDC` | AI Text Generation API |
| `POST` | `/v1/analyze` | `0.008 USDC` | Statistical Data Analysis API |
| `GET` | `/v1/weather` | `0.003 USDC` | Weather Observation API |
| `POST` | `/v1/image-process` | `0.015 USDC` | Image Processing Pipeline API |
| `GET` | `/v1/sensors` | `0.004 USDC` | Industrial IoT Sensor Telemetry API |

## Platform Management Endpoints
- `GET /api/dashboard/overview` — Aggregated KPIs, Chart.js series, TestNet node status
- `GET /api/agents` · `POST /api/agents` — List and register autonomous agents
- `GET /api/agents/{id}/balance` — Local balance + live Algorand TestNet ALGO/USDC query
- `PATCH /api/agents/{id}/policy` — Update per-request cap, daily limit, allowed hosts, settlement mode
- `PATCH /api/agents/{id}/status` — Activate / deactivate agent
- `POST /api/agents/{id}/fund` — Credit local demo USDC balance (Local Demo Mode only)
- `GET /api/marketplace/services` — List registered paid APIs
- `GET /api/payments` · `GET /api/payments/{id}` — Filterable Transaction Explorer + audit timeline
- `GET /api/channels` · `POST /api/channels` — List and open voucher payment channels
- `POST /api/channels/{id}/deposit` — Deposit additional funds into channel
- `POST /api/channels/{id}/batch-settle` — Batch settle pending cumulative vouchers
- `POST /api/channels/{id}/close` — Close channel and refund unspent balance
- `POST /api/policies/evaluate` — Evaluate spending rules for an agent and request amount
- `GET /api/audit` — Query append-only audit ledger
- `POST /api/demo/run` — Execute full end-to-end 11-step HTTP 402 flow via `TollRailAgentClient`
- `GET /api/settings` · `PATCH /api/settings` — Inspect and update execution mode & TestNet configuration
