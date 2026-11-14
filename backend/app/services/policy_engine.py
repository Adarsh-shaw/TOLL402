from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.app.blockchain.algorand_client import AlgorandClient
from backend.app.models.models import Agent, PaymentChannel
from backend.app.schemas.schemas import PolicyCheckResponse, PolicyRuleResult, micro_to_usdc
from backend.app.services.agent_service import AgentService, get_runtime_mode, get_usdc_asset_id


class PolicyEngine:
    """Evaluates autonomous agent spending policies prior to signing or submitting payments."""

    @staticmethod
    def evaluate(
        db: Session,
        agent: Agent,
        amount_micro_usdc: int,
        target_host: str,
        expires_at: datetime | None = None,
        settlement_mode: str = "exact",
        channel: PaymentChannel | None = None,
    ) -> PolicyCheckResponse:
        AgentService.ensure_daily_reset(db, agent)
        checks: list[PolicyRuleResult] = []
        mode = get_runtime_mode(db)

        # 1. Agent active status
        active_ok = bool(agent.is_active)
        checks.append(
            PolicyRuleResult(
                rule="agent_active",
                passed=active_ok,
                detail="Agent is active and authorized to transact" if active_ok else "Agent is deactivated",
            )
        )

        # 2. Challenge expiration
        expiry_ok = True
        expiry_detail = "No expiration constraint"
        if expires_at is not None:
            now = datetime.now(timezone.utc)
            exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
            expiry_ok = now <= exp
            expiry_detail = (
                f"Challenge valid until {exp.isoformat()}"
                if expiry_ok
                else f"Challenge expired at {exp.isoformat()}"
            )
        checks.append(PolicyRuleResult(rule="challenge_expiration", passed=expiry_ok, detail=expiry_detail))

        # 3. Allowed API host check
        normalized_host = target_host.strip().lower()
        allowed = [h.strip().lower() for h in (agent.allowed_hosts or [])]
        host_ok = "*" in allowed or normalized_host in allowed or any(
            normalized_host.endswith(f".{h}") for h in allowed if h
        )
        checks.append(
            PolicyRuleResult(
                rule="allowed_api_host",
                passed=host_ok,
                detail=(
                    f"Host '{normalized_host}' is in allowed_hosts"
                    if host_ok
                    else f"Host '{normalized_host}' is not permitted (allowed: {', '.join(allowed) or 'none'})"
                ),
            )
        )

        # 4. Per-request spending limit
        req_limit_ok = amount_micro_usdc <= agent.per_request_limit_micro
        checks.append(
            PolicyRuleResult(
                rule="per_request_limit",
                passed=req_limit_ok,
                detail=(
                    f"Requested ${micro_to_usdc(amount_micro_usdc):.6f} <= limit ${micro_to_usdc(agent.per_request_limit_micro):.6f}"
                    if req_limit_ok
                    else f"Requested ${micro_to_usdc(amount_micro_usdc):.6f} exceeds per-request limit ${micro_to_usdc(agent.per_request_limit_micro):.6f}"
                ),
            )
        )

        # 5. Daily spending limit
        projected_daily = agent.daily_spent_micro + amount_micro_usdc
        daily_ok = projected_daily <= agent.daily_limit_micro
        checks.append(
            PolicyRuleResult(
                rule="daily_spending_limit",
                passed=daily_ok,
                detail=(
                    f"Projected daily spend ${micro_to_usdc(projected_daily):.6f} <= daily limit ${micro_to_usdc(agent.daily_limit_micro):.6f}"
                    if daily_ok
                    else f"Projected daily spend ${micro_to_usdc(projected_daily):.6f} exceeds daily limit ${micro_to_usdc(agent.daily_limit_micro):.6f}"
                ),
            )
        )

        # 6. Available balance check (channel escrow vs TestNet vs local_demo)
        available_micro = agent.local_balance_micro_usdc
        if settlement_mode == "channel" and channel is not None:
            remaining_channel = max(0, channel.deposited_micro_usdc - channel.cumulative_spent_micro)
            available_micro = remaining_channel
            bal_ok = channel.status == "open" and remaining_channel >= amount_micro_usdc
            bal_detail = (
                f"Channel {channel.id} remaining ${micro_to_usdc(remaining_channel):.6f} covers ${micro_to_usdc(amount_micro_usdc):.6f}"
                if bal_ok
                else f"Channel {channel.id} insufficient remaining deposit (${micro_to_usdc(remaining_channel):.6f} < ${micro_to_usdc(amount_micro_usdc):.6f})"
            )
        elif mode == "algorand_testnet":
            algod_client = AlgorandClient()
            bal = algod_client.get_account_balances(agent.wallet_address, get_usdc_asset_id(db))
            if not bal.get("success"):
                bal_ok = False
                available_micro = 0
                bal_detail = f"Failed to verify Algorand TestNet balance: {bal.get('error')}"
            else:
                available_micro = int(bal.get("usdc_micro") or 0)
                algo_micro = int(bal.get("algo_micro") or 0)
                opted_in = bool(bal.get("usdc_opted_in"))
                bal_ok = opted_in and available_micro >= amount_micro_usdc and algo_micro >= 1000
                if not opted_in:
                    bal_detail = "Agent Algorand TestNet wallet is not opted into USDC ASA"
                elif algo_micro < 1000:
                    bal_detail = "Agent Algorand TestNet wallet lacks minimum 0.001 ALGO for transaction fee"
                elif available_micro < amount_micro_usdc:
                    bal_detail = f"TestNet USDC balance ${micro_to_usdc(available_micro):.6f} < ${micro_to_usdc(amount_micro_usdc):.6f}"
                else:
                    bal_detail = f"TestNet USDC balance ${micro_to_usdc(available_micro):.6f} covers request"
        else:
            bal_ok = agent.local_balance_micro_usdc >= amount_micro_usdc
            bal_detail = (
                f"Available balance ${micro_to_usdc(agent.local_balance_micro_usdc):.6f} covers ${micro_to_usdc(amount_micro_usdc):.6f}"
                if bal_ok
                else f"Insufficient balance: ${micro_to_usdc(agent.local_balance_micro_usdc):.6f} < ${micro_to_usdc(amount_micro_usdc):.6f}"
            )

        checks.append(PolicyRuleResult(rule="available_balance", passed=bal_ok, detail=bal_detail))

        failed_checks = [c for c in checks if not c.passed]
        approved = len(failed_checks) == 0
        reason = "All spending policy checks passed." if approved else failed_checks[0].detail

        return PolicyCheckResponse(
            approved=approved,
            agent_id=agent.id,
            reason=reason,
            requested_amount_usdc=micro_to_usdc(amount_micro_usdc),
            per_request_limit_usdc=micro_to_usdc(agent.per_request_limit_micro),
            daily_limit_usdc=micro_to_usdc(agent.daily_limit_micro),
            daily_spent_usdc=micro_to_usdc(agent.daily_spent_micro),
            available_balance_usdc=micro_to_usdc(available_micro),
            target_host=normalized_host,
            checks=checks,
        )
