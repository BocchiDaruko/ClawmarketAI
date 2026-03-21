"""
ClawmarketAI — Buyer Agent
agent.py · Main Buyer Agent Orchestrator

Runs the autonomous decision loop:
  Observe → Evaluate → Execute → Reinvest → Repeat
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from pathlib import Path

import aiohttp
from web3 import AsyncWeb3
from web3.middleware import async_geth_poa_middleware

from .config import BuyerAgentConfig
from .executor import PurchaseStatus, TransactionExecutor
from .scanner import MarketScanner
from .state import StateManager
from .strategy import StrategyEngine

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("buyer_agent")


# ─── Buyer Agent ──────────────────────────────────────────────────────────────

class BuyerAgent:
    """
    Autonomous Buyer Agent for ClawmarketAI.

    Decision loop (every scan_interval_seconds):
      1. Scan REST API + Base on-chain events for new listings
      2. Strategy Engine scores and filters candidates
      3. Execute top purchase candidate if score > 0
      4. Update state, log result
      5. Trigger reinvestment hook if applicable
      6. Sleep and repeat

    Gracefully handles SIGINT/SIGTERM for safe shutdown.
    """

    def __init__(self, config: BuyerAgentConfig):
        self.config   = config
        self._running = False

        # Components (initialized on start())
        self._scanner:  MarketScanner | None = None
        self._strategy: StrategyEngine | None = None
        self._executor: TransactionExecutor | None = None
        self._state:    StateManager | None = None
        self._w3:       AsyncWeb3 | None = None
        self._session:  aiohttp.ClientSession | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self):
        """Initialize all components and start the decision loop."""
        logger.info("Starting BuyerAgent '%s' (strategy=%s, budget=%.2f USDC)",
                    self.config.agent_id, self.config.strategy, self.config.budget_usdc)

        # Web3
        self._w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.config.rpc_url))
        self._w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)

        # HTTP session (shared by scanner + executor)
        self._session = aiohttp.ClientSession(
            base_url=self.config.api_base_url,
            headers={
                "Authorization": f"Bearer {self.config.get_api_key()}",
                "Content-Type": "application/json",
            },
        )

        # Components
        self._scanner  = MarketScanner(self.config)
        self._strategy = StrategyEngine(self.config)
        self._executor = TransactionExecutor(self.config, self._w3, self._session)
        self._state    = StateManager(self.config)

        await self._scanner.start()

        # Graceful shutdown hooks
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        self._running = True
        logger.info("BuyerAgent running. Scan interval: %ds", self.config.scan_interval_seconds)
        await self._run_loop()

    async def stop(self):
        """Graceful shutdown."""
        logger.info("Shutting down BuyerAgent '%s'…", self.config.agent_id)
        self._running = False
        if self._scanner:
            await self._scanner.stop()
        if self._session:
            await self._session.close()
        logger.info("Final state:\n%s",
                    json.dumps(self._state.summary(), indent=2) if self._state else "{}")

    # ── Decision loop ─────────────────────────────────────────────────────────

    async def _run_loop(self):
        """Main autonomous loop."""
        while self._running:
            try:
                await self._tick()
            except Exception as exc:
                logger.error("Unhandled error in decision loop: %s", exc, exc_info=True)

            # Log periodic summary every 10 ticks (configurable)
            if self._state.state.total_purchases % 10 == 0 and self._state.state.total_purchases > 0:
                logger.info("Summary: %s", json.dumps(self._state.summary()))

            await asyncio.sleep(self.config.scan_interval_seconds)

    async def _tick(self):
        """Single iteration of the decision loop."""

        # 1. Budget exhausted?
        if self._state.remaining_budget <= 0:
            logger.info(
                "Budget exhausted (spent=%.2f / %.2f USDC). Waiting for reinvestment.",
                self._state.state.spent_usdc, self.config.budget_usdc,
            )
            return

        # 2. Scan for new listings
        listings = await self._scanner.fetch_listings()
        if not listings:
            logger.debug("No new listings this tick.")
            return

        # 3. Evaluate via strategy engine
        candidates = self._strategy.evaluate(
            listings, spent_usdc=self._state.state.spent_usdc
        )
        if not candidates:
            logger.debug("No candidates passed strategy evaluation.")
            return

        # 4. Reject negative-scored candidates (e.g. overpriced in lowest-price mode)
        top = candidates[0]
        if top.score <= 0:
            logger.debug(
                "Top candidate score=%.3f ≤ 0 — skipping. Reason: %s",
                top.score, top.reason,
            )
            return

        logger.info(
            "Best candidate: listing=%s score=%.3f reason='%s'",
            top.listing.listing_id, top.score, top.reason,
        )

        # 5. Execute purchase
        result = await self._executor.execute_purchase(top)

        # 6. Update state
        self._state.record_purchase(
            result=result,
            strategy=self.config.strategy,
            score=top.score,
            reason=top.reason,
        )

        if result.status == PurchaseStatus.SUCCESS:
            logger.info(
                "✓ Purchased listing %s for %.2f USDC | tx: %s",
                result.listing_id, result.price_usdc, result.tx_hash,
            )
        elif result.status == PurchaseStatus.SKIPPED:
            logger.info("Listing %s was already purchased — skipped.", result.listing_id)
        else:
            logger.warning(
                "✗ Purchase failed: listing=%s status=%s error=%s",
                result.listing_id, result.status, result.error,
            )


# ─── Entry point ─────────────────────────────────────────────────────────────

def run_from_config_file(config_path: str):
    """Load agent config from JSON and start the agent."""
    data   = json.loads(Path(config_path).read_text())
    config = BuyerAgentConfig(**data)
    agent  = BuyerAgent(config)
    asyncio.run(agent.start())


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m agents.buyer-agent.agent <config.json>")
        sys.exit(1)
    run_from_config_file(sys.argv[1])
