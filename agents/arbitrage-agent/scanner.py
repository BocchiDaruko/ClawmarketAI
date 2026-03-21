"""
ClawmarketAI — Arbitrage Agent
scanner.py · Price Scanner
Fetches all active listings, clusters same-good duplicates,
and surfaces price differentials ready for the evaluator.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import aiohttp
from web3 import AsyncWeb3

from .config import ArbitrageAgentConfig

logger = logging.getLogger("arbitrage_agent.scanner")


# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class MarketListing:
    listing_id: str
    seller: str
    title: str
    category: str
    price_usdc: float
    reputation_score: float
    age_hours: float
    available: bool = True
    metadata_uri: str = ""


@dataclass
class PriceCluster:
    """
    A group of listings that appear to be the same (or very similar) good
    sold at different prices — the raw material for arbitrage.
    """
    canonical_title: str
    category: str
    listings: list[MarketListing]

    @property
    def cheapest(self) -> MarketListing:
        return min(self.listings, key=lambda l: l.price_usdc)

    @property
    def most_expensive(self) -> MarketListing:
        return max(self.listings, key=lambda l: l.price_usdc)

    @property
    def price_spread_usdc(self) -> float:
        return self.most_expensive.price_usdc - self.cheapest.price_usdc

    @property
    def price_spread_pct(self) -> float:
        if self.cheapest.price_usdc == 0:
            return 0.0
        return self.price_spread_usdc / self.cheapest.price_usdc

    @property
    def average_price(self) -> float:
        return sum(l.price_usdc for l in self.listings) / len(self.listings)


@dataclass
class SubvaluedListing:
    """
    A listing priced significantly below the category average —
    a cross-category arbitrage signal.
    """
    listing: MarketListing
    category_avg: float
    discount_pct: float     # how much cheaper vs category avg


# ─── ABI ──────────────────────────────────────────────────────────────────────

REPUTATION_ABI = [
    {
        "name": "getScore",
        "type": "function",
        "stateMutability": "view",
        "inputs":  [{"name": "account", "type": "address"}],
        "outputs": [{"name": "score",   "type": "uint256"}],
    }
]


# ─── Price Scanner ────────────────────────────────────────────────────────────

class PriceScanner:
    """
    Dual-mode scanner:
      1. Same-good clustering: groups listings of identical goods sold at
         different prices — identifies internal arbitrage (buy cheap, resell).
      2. Cross-category scan: finds listings priced well below their category
         average — identifies undervalued goods worth flipping.
    """

    def __init__(
        self,
        config: ArbitrageAgentConfig,
        w3: AsyncWeb3,
        session: aiohttp.ClientSession,
    ):
        self.config   = config
        self._w3      = w3
        self._session = session

        self._rep_contract = w3.eth.contract(
            address=config.reputation_address, abi=REPUTATION_ABI
        )

    # ── Public interface ──────────────────────────────────────────────────────

    async def scan(self) -> tuple[list[PriceCluster], list[SubvaluedListing]]:
        """
        Full market scan.
        Returns (clusters_with_spread, subvalued_listings).
        """
        listings = await self._fetch_all_listings()
        if not listings:
            return [], []

        # Enrich with on-chain reputation scores
        await self._enrich_reputation(listings)

        # Filter: skip old listings and low-reputation sellers
        listings = [
            l for l in listings
            if l.age_hours <= self.config.max_listing_age_hours
            and l.reputation_score >= self.config.min_seller_reputation
        ]

        clusters   = self._cluster_by_similarity(listings)
        subvalued  = self._find_subvalued(listings)

        # Only keep clusters with a meaningful spread
        spreads = [
            c for c in clusters
            if c.price_spread_usdc > 0
            and len(c.listings) >= 2
        ]

        logger.info(
            "Scan complete: %d listings → %d clusters with spread, %d subvalued",
            len(listings), len(spreads), len(subvalued),
        )
        return spreads, subvalued

    # ── Fetch ─────────────────────────────────────────────────────────────────

    async def _fetch_all_listings(self) -> list[MarketListing]:
        """GET /listings?available=true — all active marketplace listings."""
        try:
            async with self._session.get("/listings?available=true&limit=500") as resp:
                if resp.status != 200:
                    logger.warning("Listings API returned %s", resp.status)
                    return []
                data = await resp.json()
                return [self._parse(item) for item in data.get("listings", [])]
        except aiohttp.ClientError as exc:
            logger.error("Listings fetch error: %s", exc)
            return []

    # ── Reputation enrichment ─────────────────────────────────────────────────

    async def _enrich_reputation(self, listings: list[MarketListing]):
        """Batch-fetch reputation scores from ReputationScore.sol."""
        sellers = {l.seller for l in listings}
        scores: dict[str, float] = {}
        for seller in sellers:
            try:
                raw = await self._rep_contract.functions.getScore(seller).call()
                scores[seller] = raw / 100.0
            except Exception:
                scores[seller] = 0.0
        for l in listings:
            l.reputation_score = scores.get(l.seller, 0.0)

    # ── Same-good clustering ──────────────────────────────────────────────────

    def _cluster_by_similarity(self, listings: list[MarketListing]) -> list[PriceCluster]:
        """
        Group listings whose titles are similar enough (≥ similarity_threshold)
        to be considered the same good sold at different prices.
        Uses a greedy O(n²) approach — fine for marketplace scale.
        """
        threshold = self.config.similarity_threshold
        clusters:  list[list[MarketListing]] = []
        assigned:  set[str] = set()

        for listing in listings:
            if listing.listing_id in assigned:
                continue
            cluster = [listing]
            assigned.add(listing.listing_id)

            for other in listings:
                if other.listing_id in assigned:
                    continue
                if other.category != listing.category:
                    continue
                sim = self._title_similarity(listing.title, other.title)
                if sim >= threshold:
                    cluster.append(other)
                    assigned.add(other.listing_id)

            if len(cluster) >= 2:
                clusters.append(cluster)

        return [
            PriceCluster(
                canonical_title=self._canonical(group[0].title),
                category=group[0].category,
                listings=group,
            )
            for group in clusters
        ]

    # ── Cross-category subvalued scan ─────────────────────────────────────────

    def _find_subvalued(self, listings: list[MarketListing]) -> list[SubvaluedListing]:
        """
        For each category, compute avg price.
        Flag listings priced ≥ 20% below avg as subvalued.
        """
        by_category: dict[str, list[MarketListing]] = {}
        for l in listings:
            by_category.setdefault(l.category, []).append(l)

        subvalued: list[SubvaluedListing] = []
        for cat, cat_listings in by_category.items():
            if len(cat_listings) < 3:   # need enough data to compute a meaningful avg
                continue
            avg = sum(l.price_usdc for l in cat_listings) / len(cat_listings)
            for l in cat_listings:
                discount = (avg - l.price_usdc) / avg if avg > 0 else 0
                if discount >= 0.20:    # 20% below avg = subvalued signal
                    subvalued.append(SubvaluedListing(
                        listing=l,
                        category_avg=avg,
                        discount_pct=discount,
                    ))

        subvalued.sort(key=lambda s: s.discount_pct, reverse=True)
        return subvalued

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _title_similarity(a: str, b: str) -> float:
        """Normalized similarity ratio between two listing titles."""
        a_norm = re.sub(r"[^a-z0-9\s]", "", a.lower()).strip()
        b_norm = re.sub(r"[^a-z0-9\s]", "", b.lower()).strip()
        return SequenceMatcher(None, a_norm, b_norm).ratio()

    @staticmethod
    def _canonical(title: str) -> str:
        """Normalize title to a canonical form for cluster naming."""
        return re.sub(r"\s+", " ", title.strip()).title()

    @staticmethod
    def _parse(item: dict) -> MarketListing:
        from datetime import datetime, timezone
        listed_at = item.get("listed_at", "")
        age_hours = 0.0
        if listed_at:
            try:
                dt = datetime.fromisoformat(listed_at)
                age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
            except ValueError:
                pass
        return MarketListing(
            listing_id=str(item["id"]),
            seller=item.get("seller", ""),
            title=item.get("title", ""),
            category=item.get("category", ""),
            price_usdc=float(item.get("price_usdc", 0)),
            reputation_score=float(item.get("reputation_score", 0)),
            age_hours=age_hours,
            available=item.get("available", True),
            metadata_uri=item.get("metadata_uri", ""),
        )
