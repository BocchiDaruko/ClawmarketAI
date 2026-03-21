"""
ClawmarketAI — Seller Agent
agent.py · Main Seller Agent Orchestrator

Autonomous loop:
  1. Publish listings for goods below max_concurrent threshold
  2. Reprice stale active listings via Dynamic Pricing Engine
  3. Poll for new orders and fulfill them (on-chain + API)
  4. Log summary periodically
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

from .config import SellerAgentConfig
from .fulfiller import OrderFulfiller
from .inventory import InventoryManager
from .listing_manager import ListingManager
from .pricing import DynamicPricingEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("seller_agent")


class SellerAgent:
    """
    Autonomous Seller Agent for ClawmarketAI (Base Mainnet).

    Per tick:
      - Publishes new listings for goods with open slots
      - Reprices stale listings using the 4-mode pricing engine
      - Fulfills incoming orders via Escrow + API delivery
    """

    def __init__(self, config: SellerAgentConfig):
        self.config   = config
        self._running = False
        self._tick_count = 0

        self._w3:        AsyncWeb3 | None          = None
        self._session:   aiohttp.ClientSession | None = None
        self._inventory: InventoryManager | None   = None
        self._pricing:   DynamicPricingEngine | None = None
        self._lister:    ListingManager | None     = None
        self._fulfiller: OrderFulfiller | None     = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        logger.info(
            "Starting SellerAgent '%s' | goods=%d | pricing_modes=%s",
            self.config.agent_id,
            len(self.config.goods),
            self.config.pricing_modes,
        )

        self._w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.config.rpc_url))
        self._w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)

        if not await self._w3.is_connected():
            raise ConnectionError(f"Cannot connect to Base RPC at {self.config.rpc_url}")
        logger.info("Connected to Base (chain_id=%s)", self.config.chain_id)

        self._session = aiohttp.ClientSession(
            base_url=self.config.api_base_url,
            headers={
                "Authorization": f"Bearer {self.config.get_api_key()}",
                "Content-Type":  "application/json",
            },
        )

        self._inventory = InventoryManager(self.config)
        self._pricing   = DynamicPricingEngine(self.config, self._session)
        self._lister    = ListingManager(
            self.config, self._w3, self._session, self._inventory, self._pricing
        )
        self._fulfiller = OrderFulfiller(
            self.config, self._w3, self._session, self._inventory
        )

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        self._running = True
        logger.info("SellerAgent running. Scan interval: %ds",
                    self.config.scan_interval_seconds)
        await self._run_loop()

    async def stop(self):
        logger.info("Shutting down SellerAgent '%s'…", self.config.agent_id)
        self._running = False
        if self._session:
            await self._session.close()
        if self._inventory:
            logger.info("Final summary:\n%s",
                        json.dumps(self._inventory.summary(), indent=2))

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def _run_loop(self):
        while self._running:
            try:
                await self._tick()
            except Exception as exc:
                logger.error("Unhandled error in loop: %s", exc, exc_info=True)

            self._tick_count += 1
            if self._tick_count % 20 == 0:
                logger.info("Summary: %s", json.dumps(self._inventory.summary()))

            await asyncio.sleep(self.config.scan_interval_seconds)

    async def _tick(self):
        """Single autonomous iteration."""

        # 1. Publish new listings for under-stocked goods
        await self._publish_needed_listings()

        # 2. Reprice stale listings
        await self._reprice_stale_listings()

        # 3. Fulfill pending orders
        await self._fulfiller.poll_and_fulfill()

    # ── Sub-tasks ─────────────────────────────────────────────────────────────

    async def _publish_needed_listings(self):
        """For each good that has open listing slots, publish a new listing."""
        for good in self.config.goods:
            if self._inventory.needs_relisting(good):
                current = self._inventory.count_active_by_type(good.good_type)
                slots   = good.max_concurrent_listings - current
                logger.info(
                    "Publishing %d new listing(s) for '%s' (%d/%d active)",
                    slots, good.good_type, current, good.max_concurrent_listings,
                )
                for _ in range(slots):
                    listing = await self._lister.publish_listing(good)
                    if not listing:
                        break   # avoid hammering on repeated failures

    async def _reprice_stale_listings(self):
        """
        Reprice listings that haven't been updated in at least 30 minutes.
        Uses relist_after_minutes as the staleness threshold.
        """
        stale = self._inventory.stale_listings(
            min_age_hours=self.config.relist_after_minutes / 60
        )
        if not stale:
            return

        logger.debug("Repricing %d stale listing(s)…", len(stale))
        for listing in stale:
            await self._lister.reprice_listing(listing)


# ─── Entry point ─────────────────────────────────────────────────────────────

def run_from_config_file(config_path: str):
    data   = json.loads(Path(config_path).read_text())
    config = SellerAgentConfig(**data)
    agent  = SellerAgent(config)
    asyncio.run(agent.start())


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m agents.seller-agent.agent <config.json>")
        sys.exit(1)
    run_from_config_file(sys.argv[1])
