"""
clawmarketAI — Buyer Agent
Autonomously scans listings and purchases goods matching a defined strategy.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Literal

from web3 import Web3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [BUYER] %(message)s")
log = logging.getLogger(__name__)


@dataclass
class BuyerConfig:
    agent_id: str
    wallet_address: str
    private_key: str
    budget_wei: int
    strategy: Literal["lowest-price", "best-reputation", "balanced"]
    categories: list[str]
    reinvest_ratio: float
    risk_tolerance: Literal["low", "medium", "high"]
    max_tx_per_hour: int = 10
    rpc_url: str = "https://mainnet.infura.io/v3/YOUR_KEY"
    marketplace_address: str = ""


class BuyerAgent:
    """
    Autonomous buyer agent that:
    1. Fetches active marketplace listings
    2. Filters by category and strategy
    3. Purchases the best match within budget
    4. Reinvests a portion of any resale profits
    """

    def __init__(self, config: BuyerConfig):
        self.config = config
        self.w3 = Web3(Web3.HTTPProvider(config.rpc_url))
        self.tx_count_this_hour = 0
        self.total_spent = 0

    async def observe(self) -> list[dict]:
        """Fetch active listings from on-chain events or indexer API."""
        log.info("Scanning marketplace listings...")
        # In production: query The Graph or a custom indexer
        # Simulated response for illustration:
        return [
            {"id": 1, "category": "compute", "price": 10**17, "reputation": 4.8},
            {"id": 2, "category": "data", "price": 5 * 10**16, "reputation": 4.2},
            {"id": 3, "category": "api-access", "price": 2 * 10**17, "reputation": 4.9},
        ]

    def evaluate(self, listings: list[dict]) -> dict | None:
        """Select the best listing based on strategy."""
        eligible = [
            l for l in listings
            if l["category"] in self.config.categories
            and l["price"] <= self.config.budget_wei
        ]

        if not eligible:
            log.info("No eligible listings found.")
            return None

        if self.config.strategy == "lowest-price":
            return min(eligible, key=lambda l: l["price"])
        elif self.config.strategy == "best-reputation":
            return max(eligible, key=lambda l: l["reputation"])
        else:  # balanced
            return max(eligible, key=lambda l: l["reputation"] / l["price"])

    async def purchase(self, listing: dict) -> bool:
        """Sign and send a purchase transaction via SmartWallet."""
        if self.tx_count_this_hour >= self.config.max_tx_per_hour:
            log.warning("Hourly transaction limit reached. Waiting...")
            return False

        log.info(f"Purchasing listing #{listing['id']} for {listing['price']} wei")

        # In production: encode marketplace.purchase(listingId) call
        # and send via SmartWallet.execute()
        self.tx_count_this_hour += 1
        self.total_spent += listing["price"]
        log.info(f"✅ Purchase successful. Total spent: {self.total_spent} wei")
        return True

    async def reinvest(self, profit: int):
        """Reinvest a portion of profits back into the agent's budget."""
        reinvest_amount = int(profit * self.config.reinvest_ratio)
        self.config.budget_wei += reinvest_amount
        log.info(f"♻️  Reinvested {reinvest_amount} wei. New budget: {self.config.budget_wei} wei")

    async def run(self):
        """Main autonomous loop."""
        log.info(f"🤖 Buyer agent {self.config.agent_id} started.")
        while True:
            try:
                listings = await self.observe()
                best = self.evaluate(listings)
                if best:
                    await self.purchase(best)
                await asyncio.sleep(30)  # Poll every 30 seconds
            except Exception as e:
                log.error(f"Agent error: {e}")
                await asyncio.sleep(10)


if __name__ == "__main__":
    with open("config.json") as f:
        raw = json.load(f)

    config = BuyerConfig(**raw)
    agent = BuyerAgent(config)
    asyncio.run(agent.run())
