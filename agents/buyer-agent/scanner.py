"""
ClawmarketAI — Buyer Agent
scanner.py · Market Scanner (REST API + Base on-chain events)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator

import aiohttp
from web3 import AsyncWeb3
from web3.middleware import async_geth_poa_middleware

from .config import BuyerAgentConfig, Category

logger = logging.getLogger("buyer_agent.scanner")


# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class Listing:
    """Represents a single marketplace listing."""
    listing_id: str
    seller: str                  # wallet address
    title: str
    category: str
    price_usdc: float
    reputation_score: float      # 0–100, fetched from ReputationScore.sol
    available: bool = True
    on_chain: bool = True        # False = API-only listing (not yet settled on-chain)
    metadata_uri: str = ""       # IPFS URI for item details
    raw: dict = field(default_factory=dict)  # original payload

    @property
    def is_valid(self) -> bool:
        return (
            self.available
            and self.price_usdc > 0
            and self.reputation_score >= 0
        )


# ─── ABI snippets (minimal — only events/functions we need) ──────────────────

MARKETPLACE_ABI = [
    {
        "name": "ListingCreated",
        "type": "event",
        "inputs": [
            {"name": "listingId", "type": "uint256", "indexed": True},
            {"name": "seller",    "type": "address",  "indexed": True},
            {"name": "priceUsdc", "type": "uint256",  "indexed": False},
            {"name": "category",  "type": "string",   "indexed": False},
        ],
    },
    {
        "name": "getActiveListing",
        "type": "function",
        "stateMutability": "view",
        "inputs":  [{"name": "listingId", "type": "uint256"}],
        "outputs": [
            {"name": "seller",      "type": "address"},
            {"name": "priceUsdc",   "type": "uint256"},
            {"name": "category",    "type": "string"},
            {"name": "metadataUri", "type": "string"},
            {"name": "available",   "type": "bool"},
        ],
    },
]

REPUTATION_ABI = [
    {
        "name": "getScore",
        "type": "function",
        "stateMutability": "view",
        "inputs":  [{"name": "account", "type": "address"}],
        "outputs": [{"name": "score",   "type": "uint256"}],
    }
]


# ─── Scanner ──────────────────────────────────────────────────────────────────

class MarketScanner:
    """
    Dual-source scanner: polls REST API for fast listing discovery,
    and subscribes to Base on-chain ListingCreated events for finality.
    """

    def __init__(self, config: BuyerAgentConfig):
        self.config = config
        self._w3: AsyncWeb3 | None = None
        self._session: aiohttp.ClientSession | None = None
        self._seen_listing_ids: set[str] = set()

    # ── Setup / teardown ─────────────────────────────────────────────────────

    async def start(self):
        """Initialize Web3 and HTTP session."""
        self._w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.config.rpc_url))
        self._w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)

        if not await self._w3.is_connected():
            raise ConnectionError(
                f"Cannot connect to Base RPC at {self.config.rpc_url}"
            )
        logger.info("Connected to Base (chain_id=%s)", self.config.chain_id)

        self._session = aiohttp.ClientSession(
            base_url=self.config.api_base_url,
            headers={
                "Authorization": f"Bearer {self.config.get_api_key()}",
                "Content-Type": "application/json",
            },
        )
        logger.info("HTTP session opened → %s", self.config.api_base_url)

    async def stop(self):
        if self._session:
            await self._session.close()
        logger.info("Scanner stopped.")

    # ── Public interface ─────────────────────────────────────────────────────

    async def fetch_listings(self) -> list[Listing]:
        """
        Fetch all current active listings matching configured categories.
        Merges API results with on-chain verification.
        """
        api_listings  = await self._fetch_from_api()
        onchain_ids   = await self._fetch_recent_onchain_ids()

        # Mark which listings are confirmed on-chain
        for lst in api_listings:
            lst.on_chain = lst.listing_id in onchain_ids

        # Enrich with reputation scores (batch call)
        await self._enrich_reputation(api_listings)

        new_listings = [
            lst for lst in api_listings
            if lst.listing_id not in self._seen_listing_ids and lst.is_valid
        ]

        self._seen_listing_ids.update(lst.listing_id for lst in new_listings)
        logger.info("Fetched %d new listings", len(new_listings))
        return new_listings

    async def stream_onchain_events(self) -> AsyncIterator[Listing]:
        """
        Subscribe to ListingCreated events on Base for real-time discovery.
        Yields Listing objects as events arrive.
        """
        contract = self._w3.eth.contract(
            address=self.config.marketplace_address,
            abi=MARKETPLACE_ABI,
        )
        event_filter = await contract.events.ListingCreated.create_filter(
            fromBlock="latest"
        )
        logger.info("Subscribed to ListingCreated events on Base")

        while True:
            try:
                events = await event_filter.get_new_entries()
                for evt in events:
                    listing = await self._listing_from_event(evt, contract)
                    if listing and listing.listing_id not in self._seen_listing_ids:
                        self._seen_listing_ids.add(listing.listing_id)
                        yield listing
            except Exception as exc:
                logger.warning("Event polling error: %s", exc)

            await asyncio.sleep(self.config.scan_interval_seconds)

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _fetch_from_api(self) -> list[Listing]:
        """GET /listings?category=...&available=true"""
        category_params = "&".join(
            f"category={c}" for c in self.config.categories
        )
        url = f"/listings?available=true&{category_params}"
        try:
            async with self._session.get(url) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return [self._parse_api_listing(item) for item in data.get("listings", [])]
        except aiohttp.ClientError as exc:
            logger.error("API fetch error: %s", exc)
            return []

    async def _fetch_recent_onchain_ids(self) -> set[str]:
        """
        Get listing IDs from on-chain ListingCreated events in the last
        ~256 blocks (~8.5 minutes on Base at 2s block time).
        """
        try:
            contract = self._w3.eth.contract(
                address=self.config.marketplace_address,
                abi=MARKETPLACE_ABI,
            )
            latest  = await self._w3.eth.block_number
            from_blk = max(0, latest - 256)
            events  = await contract.events.ListingCreated.get_logs(
                fromBlock=from_blk, toBlock=latest
            )
            return {str(evt["args"]["listingId"]) for evt in events}
        except Exception as exc:
            logger.warning("On-chain ID fetch error: %s", exc)
            return set()

    async def _enrich_reputation(self, listings: list[Listing]):
        """Batch-query ReputationScore.sol for all unique sellers."""
        if not listings:
            return
        rep_contract = self._w3.eth.contract(
            address=self.config.reputation_address,
            abi=REPUTATION_ABI,
        )
        sellers = {lst.seller for lst in listings}
        scores: dict[str, float] = {}

        for seller in sellers:
            try:
                raw_score = await rep_contract.functions.getScore(seller).call()
                # Contract returns score * 100 as uint256 (e.g. 8523 = 85.23)
                scores[seller] = raw_score / 100.0
            except Exception as exc:
                logger.debug("Reputation fetch failed for %s: %s", seller, exc)
                scores[seller] = 0.0

        for lst in listings:
            lst.reputation_score = scores.get(lst.seller, 0.0)

    async def _listing_from_event(self, evt, contract) -> Listing | None:
        """Build a Listing from an on-chain ListingCreated event."""
        listing_id = str(evt["args"]["listingId"])
        try:
            data = await contract.functions.getActiveListing(
                int(listing_id)
            ).call()
            seller, price_raw, category, metadata_uri, available = data
            return Listing(
                listing_id=listing_id,
                seller=seller,
                title=f"Listing #{listing_id}",
                category=category,
                price_usdc=price_raw / 1e6,   # USDC has 6 decimals
                reputation_score=0.0,          # enriched separately
                available=available,
                on_chain=True,
                metadata_uri=metadata_uri,
                raw=dict(evt["args"]),
            )
        except Exception as exc:
            logger.warning("Could not build Listing from event %s: %s", listing_id, exc)
            return None

    @staticmethod
    def _parse_api_listing(item: dict) -> Listing:
        return Listing(
            listing_id=str(item["id"]),
            seller=item.get("seller", ""),
            title=item.get("title", ""),
            category=item.get("category", ""),
            price_usdc=float(item.get("price_usdc", 0)),
            reputation_score=float(item.get("reputation_score", 0)),
            available=item.get("available", True),
            on_chain=False,
            metadata_uri=item.get("metadata_uri", ""),
            raw=item,
        )
