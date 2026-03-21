"""
ClawmarketAI — Buyer Agent
state.py · Agent State Manager
Tracks session budget, purchase history, and reinvestment hooks.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import BuyerAgentConfig
from .executor import PurchaseResult, PurchaseStatus

logger = logging.getLogger("buyer_agent.state")


# ─── Purchase Record ──────────────────────────────────────────────────────────

@dataclass
class PurchaseRecord:
    listing_id: str
    price_usdc: float
    tx_hash: Optional[str]
    timestamp: str
    strategy: str
    score: float
    reason: str


# ─── Agent State ──────────────────────────────────────────────────────────────

@dataclass
class AgentState:
    agent_id: str
    budget_usdc: float
    spent_usdc: float = 0.0
    earned_usdc: float = 0.0           # from reinvestment returns (future)
    total_purchases: int = 0
    failed_attempts: int = 0
    purchases: list[PurchaseRecord] = field(default_factory=list)
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def remaining_budget(self) -> float:
        return self.budget_usdc - self.spent_usdc

    @property
    def success_rate(self) -> float:
        total = self.total_purchases + self.failed_attempts
        return self.total_purchases / total if total > 0 else 0.0

    @property
    def reinvestment_amount(self) -> float:
        """USDC available for reinvestment from earned profits."""
        return self.earned_usdc  # set externally by reinvestment hook


class StateManager:
    """
    Manages agent session state: budget tracking, purchase history,
    persistence to disk, and reinvestment calculation.
    """

    def __init__(self, config: BuyerAgentConfig, state_dir: str = "./state"):
        self.config = config
        self._state_path = Path(state_dir) / f"{config.agent_id}_state.json"
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load_or_create()

    # ── Public interface ──────────────────────────────────────────────────────

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def remaining_budget(self) -> float:
        return self._state.remaining_budget

    def record_purchase(
        self,
        result: PurchaseResult,
        strategy: str,
        score: float,
        reason: str,
    ):
        """Record a successful purchase and update budget."""
        if result.status != PurchaseStatus.SUCCESS:
            self._state.failed_attempts += 1
            self._save()
            return

        self._state.spent_usdc      += result.price_usdc
        self._state.total_purchases += 1
        self._state.purchases.append(
            PurchaseRecord(
                listing_id=result.listing_id,
                price_usdc=result.price_usdc,
                tx_hash=result.tx_hash,
                timestamp=datetime.now(timezone.utc).isoformat(),
                strategy=strategy,
                score=score,
                reason=reason,
            )
        )
        logger.info(
            "State updated → spent=%.2f remaining=%.2f purchases=%d",
            self._state.spent_usdc,
            self._state.remaining_budget,
            self._state.total_purchases,
        )
        self._save()

    def record_failure(self):
        self._state.failed_attempts += 1
        self._save()

    def apply_reinvestment(self, returned_usdc: float):
        """
        Called when a purchased item generates returns.
        Adds reinvest_ratio × returned_usdc back to the budget.
        """
        reinvest_amount = returned_usdc * self.config.reinvest_ratio
        self._state.budget_usdc += reinvest_amount
        self._state.earned_usdc += returned_usdc
        logger.info(
            "Reinvestment: +%.2f USDC (%.0f%% of %.2f earned)",
            reinvest_amount, self.config.reinvest_ratio * 100, returned_usdc,
        )
        self._save()

    def summary(self) -> dict:
        s = self._state
        return {
            "agent_id":       s.agent_id,
            "strategy":       self.config.strategy,
            "budget_usdc":    s.budget_usdc,
            "spent_usdc":     round(s.spent_usdc, 4),
            "remaining_usdc": round(s.remaining_budget, 4),
            "earned_usdc":    round(s.earned_usdc, 4),
            "total_purchases":s.total_purchases,
            "failed_attempts":s.failed_attempts,
            "success_rate":   f"{s.success_rate*100:.1f}%",
            "started_at":     s.started_at,
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_or_create(self) -> AgentState:
        if self._state_path.exists():
            try:
                data = json.loads(self._state_path.read_text())
                # Reconstruct nested PurchaseRecord list
                data["purchases"] = [
                    PurchaseRecord(**p) for p in data.get("purchases", [])
                ]
                state = AgentState(**data)
                logger.info("Loaded existing state from %s", self._state_path)
                return state
            except Exception as exc:
                logger.warning("Could not load state file, starting fresh: %s", exc)

        state = AgentState(
            agent_id=self.config.agent_id,
            budget_usdc=self.config.budget_usdc,
        )
        logger.info("Created fresh agent state for '%s'", self.config.agent_id)
        return state

    def _save(self):
        data = asdict(self._state)
        self._state_path.write_text(json.dumps(data, indent=2))
