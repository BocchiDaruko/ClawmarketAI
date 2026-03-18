"""
clawmarketAI — Seller Agent
Autonomously lists digital goods, adjusts prices, and fulfills orders.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SELLER] %(message)s")
log = logging.getLogger(__name__)


@dataclass
class Good:
    name: str
    category: str
    metadata_uri: str       # IPFS URI
    base_price_wei: int
    current_price_wei: int = 0

    def __post_init__(self):
        if self.current_price_wei == 0:
            self.current_price_wei = self.base_price_wei


@dataclass
class SellerConfig:
    agent_id: str
    wallet_address: str
    goods: list[dict]
    pricing_strategy: str = "dynamic"   # "fixed" | "dynamic"
    min_margin_bps: int = 500           # 5% minimum margin
    rpc_url: str = ""
    marketplace_address: str = ""


class SellerAgent:
    """
    Autonomous seller that lists goods, reprices dynamically,
    and confirms delivery upon purchase.
    """

    def __init__(self, config: SellerConfig):
        self.config = config
        self.active_listings: dict[int, Good] = {}
        self.goods = [Good(**g) for g in config.goods]

    async def list_goods(self):
        """Push all configured goods to the marketplace."""
        for good in self.goods:
            listing_id = await self._submit_listing(good)
            self.active_listings[listing_id] = good
            log.info(f"📦 Listed '{good.name}' at {good.current_price_wei} wei (ID: {listing_id})")

    async def _submit_listing(self, good: Good) -> int:
        """Sign and send marketplace.list() via SmartWallet."""
        # In production: encode and send transaction
        import random
        return random.randint(100, 999)

    async def reprice(self):
        """Adjust prices based on demand signals."""
        if self.config.pricing_strategy != "dynamic":
            return

        for listing_id, good in self.active_listings.items():
            demand_signal = await self._get_demand_signal(good.category)

            if demand_signal > 1.2:
                # High demand — increase price up to 20%
                good.current_price_wei = int(good.current_price_wei * 1.10)
                log.info(f"📈 Repriced '{good.name}' up → {good.current_price_wei} wei")
            elif demand_signal < 0.8:
                # Low demand — reduce price but protect margin
                floor = int(good.base_price_wei * (1 + self.config.min_margin_bps / 10000))
                good.current_price_wei = max(int(good.current_price_wei * 0.95), floor)
                log.info(f"📉 Repriced '{good.name}' down → {good.current_price_wei} wei")

    async def _get_demand_signal(self, category: str) -> float:
        """Returns a demand multiplier from on-chain analytics."""
        # Simulated — in production: query indexer or oracle
        import random
        return random.uniform(0.6, 1.5)

    async def confirm_delivery(self, listing_id: int):
        """Called when a buyer triggers delivery confirmation."""
        good = self.active_listings.get(listing_id)
        if good:
            log.info(f"✅ Delivery confirmed for listing #{listing_id}: '{good.name}'")
            del self.active_listings[listing_id]

    async def run(self):
        """Main autonomous loop."""
        log.info(f"🤖 Seller agent {self.config.agent_id} started.")
        await self.list_goods()
        while True:
            try:
                await self.reprice()
                await asyncio.sleep(60)
            except Exception as e:
                log.error(f"Agent error: {e}")
                await asyncio.sleep(15)


if __name__ == "__main__":
    with open("config.json") as f:
        raw = json.load(f)
    config = SellerConfig(**raw)
    agent = SellerAgent(config)
    asyncio.run(agent.run())
