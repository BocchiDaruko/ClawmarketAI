"""
ClawmarketAI — Arbitrage Agent
agent.py · Main Arbitrage Agent Orchestrator

Autonomous arbitrage loop:
  1. Price Scanner detects clusters + subvalued listings
  2. Opportunity Evaluator ranks by net profit, risk, speed
  3. Flash Executor buys best opportunity + relists immediately
  4. Position Monitor tracks open resells → marks sold or cancels on timeout
  5. Sleep and repeat
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from web3 import AsyncWeb3
from web3.middleware import async_geth_poa_middleware

from .config import ArbitrageAgentConfig
from .evaluator import OpportunityEvaluator
from .executor import ArbitragePosition, FlashExecutor, PositionStatus
from .scanner import PriceScanner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("arbitrage_agent")


# ─── Session Stats ────────────────────────────────────────────────────────────

@dataclass
class ArbitrageStats:
    agent_id: str
    trades_executed: int = 0
    trades_sold: int = 0
    trades_cancelled: int = 0
    trades_failed: int = 0
    total_profit_usdc: float = 0.0
    total_volume_usdc: float = 0.0
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def win_rate(self) -> float:
        closed = self.trades_sold + self.trades_cancelled
        return self.trades_sold / closed if closed > 0 else 0.0

    def summary(self) -> dict:
        return {
            "agent_id":         self.agent_id,
            "trades_executed":  self.trades_executed,
            "trades_sold":      self.trades_sold,
            "trades_cancelled": self.trades_cancelled,
            "trades_failed":    self.trades_failed,
            "win_rate":         f"{self.win_rate*100:.1f}%",
            "total_profit_usdc":round(self.total_profit_usdc, 4),
            "total_volume_usdc":round(self.total_volume_usdc, 4),
            "started_at":       self.started_at,
        }


# ─── Arbitrage Agent ──────────────────────────────────────────────────────────

class ArbitrageAgent:
    """
    Autonomous Arbitrage Agent for ClawmarketAI (Base Mainnet).

    Per tick:
      - Scans all active listings for price differentials
      - Evaluates and ranks opportunities by net profit / risk / speed
      - Executes the top opportunity if profit threshold is met
      - Monitors all open resell positions, closes stale ones
    """

    def __init__(self, config: ArbitrageAgentConfig):
        self.config   = config
        self._running = False
        self._stats   = ArbitrageStats(agent_id=config.agent_id)
        self._state_path = Path(f"./state/{config.agent_id}_stats.json")
        self._state_path.parent.mkdir(parents=True, exist_ok=True)

        self._w3:       AsyncWeb3 | None          = None
        self._session:  aiohttp.ClientSession | None = None
        self._scanner:  PriceScanner | None        = None
        self._evaluator: OpportunityEvaluator | None = None
        self._executor: FlashExecutor | None       = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        logger.info(
            "Starting ArbitrageAgent '%s' | capital=%.2f USDC | "
            "min_profit=%.2f USDC (%.0f%%) | scan=%ds",
            self.config.agent_id,
            self.config.capital_usdc,
            self.config.min_profit_usdc,
            self.config.min_profit_pct * 100,
            self.config.scan_interval_seconds,
        )

        self._w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.config.rpc_url))
        self._w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)
        if not await self._w3.is_connected():
            raise ConnectionError(f"Cannot connect to Base RPC: {self.config.rpc_url}")

        self._session = aiohttp.ClientSession(
            base_url=self.config.api_base_url,
            headers={
                "Authorization": f"Bearer {self.config.get_api_key()}",
                "Content-Type":  "application/json",
            },
        )

        self._scanner   = PriceScanner(self.config, self._w3, self._session)
        self._evaluator = OpportunityEvaluator(self.config)
        self._executor  = FlashExecutor(self.config, self._w3, self._session)

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        self._running = True
        logger.info("ArbitrageAgent running.")
        await self._run_loop()

    async def stop(self):
        logger.info("Shutting down ArbitrageAgent '%s'…", self.config.agent_id)
        self._running = False
        if self._session:
            await self._session.close()
        self._save_stats()
        logger.info("Final stats:\n%s", json.dumps(self._stats.summary(), indent=2))

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def _run_loop(self):
        tick = 0
        while self._running:
            try:
                await self._tick()
            except Exception as exc:
                logger.error("Unhandled error: %s", exc, exc_info=True)

            tick += 1
            if tick % 10 == 0:
                logger.info("Stats: %s", json.dumps(self._stats.summary()))
                self._save_stats()

            await asyncio.sleep(self.config.scan_interval_seconds)

    async def _tick(self):
        # 1. Monitor open positions (check if sold or timed out)
        await self._executor.monitor_positions()
        self._sync_closed_positions()

        # 2. Check concurrent position limit
        open_count = len(self._executor.open_positions)
        if open_count >= self.config.max_concurrent_positions:
            logger.debug(
                "At position limit (%d/%d) — skipping scan",
                open_count, self.config.max_concurrent_positions,
            )
            return

        # 3. Scan market
        clusters, subvalued = await self._scanner.scan()
        if not clusters and not subvalued:
            logger.debug("No opportunities found this tick.")
            return

        # 4. Evaluate opportunities
        opportunities = self._evaluator.evaluate(
            clusters, subvalued,
            deployed_capital=self._executor.deployed_capital,
        )
        if not opportunities:
            logger.debug("No opportunities passed evaluation filters.")
            return

        best = opportunities[0]
        logger.info(
            "Best opportunity: %s listing=%s buy=%.4f resell=%.4f "
            "net=%.4f USDC (%.1f%%) score=%.3f | %s",
            best.opp_type,
            best.buy_listing.listing_id,
            best.buy_price_usdc,
            best.resell_price_usdc,
            best.net_profit_usdc,
            best.net_profit_pct * 100,
            best.final_score,
            best.rationale,
        )

        # 5. Execute
        result = await self._executor.execute(best)
        if result.success:
            self._stats.trades_executed += 1
            self._stats.total_volume_usdc += best.buy_price_usdc
        else:
            self._stats.trades_failed += 1
            logger.warning("Execution failed: %s", result.error)

    def _sync_closed_positions(self):
        """Update stats from positions that closed since last tick."""
        for pos in self._executor._positions.values():
            if pos.status == PositionStatus.SOLD and pos.actual_profit_usdc is not None:
                # Avoid double-counting
                if not getattr(pos, "_counted", False):
                    self._stats.trades_sold += 1
                    self._stats.total_profit_usdc += pos.actual_profit_usdc
                    pos._counted = True  # type: ignore[attr-defined]
            elif pos.status == PositionStatus.CANCELLED:
                if not getattr(pos, "_counted", False):
                    self._stats.trades_cancelled += 1
                    pos._counted = True  # type: ignore[attr-defined]

    def _save_stats(self):
        try:
            self._state_path.write_text(
                json.dumps(asdict(self._stats), indent=2)
            )
        except Exception as exc:
            logger.warning("Stats save failed: %s", exc)


# ─── Entry point ──────────────────────────────────────────────────────────────

def run_from_config_file(config_path: str):
    data   = json.loads(Path(config_path).read_text())
    config = ArbitrageAgentConfig(**data)
    agent  = ArbitrageAgent(config)
    asyncio.run(agent.start())


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m agents.arbitrage-agent.agent <config.json>")
        sys.exit(1)
    run_from_config_file(sys.argv[1])
