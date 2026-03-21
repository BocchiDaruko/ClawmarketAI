"""
ClawmarketAI — Creator Agent
analyst.py · Market Analyst
Reads market data to surface creation opportunities:
  - Gap detection: high-demand categories with few/no listings
  - Top-seller cloning: best-performing goods to replicate and improve
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp

from .config import CreatorAgentConfig, GoodKind

logger = logging.getLogger("creator_agent.analyst")


# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class MarketGap:
    """A category with demand but insufficient supply."""
    category: str
    good_kind: GoodKind
    search_volume: int       # number of buyer searches / requests
    listing_count: int       # current active listings
    avg_price_usdc: float
    opportunity_score: float # higher = bigger gap


@dataclass
class TopSeller:
    """A high-performing listing to clone and improve."""
    listing_id: str
    title: str
    category: str
    good_kind: GoodKind
    sales_count: int
    avg_rating: float
    price_usdc: float
    seller: str
    metadata_uri: str


@dataclass
class CreationOpportunity:
    """Final recommendation: what to create and why."""
    good_kind: GoodKind
    title: str
    description: str
    category: str
    rationale: str
    source: str              # "gap" | "clone"
    reference_listing_id: str | None = None
    estimated_price_usdc: float = 0.0


# ─── Market Analyst ───────────────────────────────────────────────────────────

class MarketAnalyst:
    """
    Queries the ClawmarketAI REST API to identify where the
    Creator Agent can generate the most value.
    """

    def __init__(self, config: CreatorAgentConfig, session: aiohttp.ClientSession):
        self.config   = config
        self._session = session

    # ── Public interface ──────────────────────────────────────────────────────

    async def find_opportunities(
        self, max_results: int = 5
    ) -> list[CreationOpportunity]:
        """
        Returns a ranked list of creation opportunities.
        Strategy determines ordering (gap-first, clone-first, balanced).
        """
        from .config import CreationStrategy

        gaps    = await self._detect_gaps()
        clones  = await self._find_top_sellers()

        strategy = self.config.creation_strategy

        if strategy == CreationStrategy.GAP_FIRST:
            ordered = self._gaps_to_opportunities(gaps) + self._clones_to_opportunities(clones)
        elif strategy == CreationStrategy.CLONE_FIRST:
            ordered = self._clones_to_opportunities(clones) + self._gaps_to_opportunities(gaps)
        else:  # BALANCED — interleave
            gap_ops   = self._gaps_to_opportunities(gaps)
            clone_ops = self._clones_to_opportunities(clones)
            ordered   = []
            for i in range(max(len(gap_ops), len(clone_ops))):
                if i < len(gap_ops):
                    ordered.append(gap_ops[i])
                if i < len(clone_ops):
                    ordered.append(clone_ops[i])

        # Filter to configured good kinds only
        filtered = [
            op for op in ordered
            if op.good_kind in self.config.good_kinds
        ]

        logger.info(
            "Found %d opportunities (%d gaps, %d clones)",
            len(filtered), len(gaps), len(clones),
        )
        return filtered[:max_results]

    # ── Gap detection ─────────────────────────────────────────────────────────

    async def _detect_gaps(self) -> list[MarketGap]:
        """
        GET /market/gaps
        Returns categories where search_volume >> listing_count.
        """
        try:
            async with self._session.get(
                "/market/gaps?kinds=dataset,api-wrapper&limit=10"
            ) as resp:
                if resp.status != 200:
                    logger.warning("Gap API returned %s", resp.status)
                    return self._synthetic_gaps()   # fallback
                data = await resp.json()
                gaps = []
                for item in data.get("gaps", []):
                    gaps.append(MarketGap(
                        category=item["category"],
                        good_kind=GoodKind(item["kind"]),
                        search_volume=item.get("search_volume", 0),
                        listing_count=item.get("listing_count", 0),
                        avg_price_usdc=item.get("avg_price_usdc", 0.0),
                        opportunity_score=item.get("opportunity_score", 0.0),
                    ))
                # Sort by opportunity score descending
                gaps.sort(key=lambda g: g.opportunity_score, reverse=True)
                return gaps
        except aiohttp.ClientError as exc:
            logger.warning("Gap fetch error: %s — using synthetic gaps", exc)
            return self._synthetic_gaps()

    def _synthetic_gaps(self) -> list[MarketGap]:
        """
        Fallback gaps when the API is unavailable.
        Based on common high-demand low-supply categories.
        """
        return [
            MarketGap("crypto-prices", GoodKind.DATASET, 800, 2, 8.0, 0.92),
            MarketGap("weather-history", GoodKind.DATASET, 600, 4, 6.0, 0.85),
            MarketGap("fx-rates", GoodKind.API_WRAPPER, 500, 1, 4.0, 0.88),
            MarketGap("country-data", GoodKind.API_WRAPPER, 400, 3, 3.5, 0.78),
            MarketGap("llm-training", GoodKind.DATASET, 700, 5, 12.0, 0.80),
        ]

    # ── Top-seller cloning ────────────────────────────────────────────────────

    async def _find_top_sellers(self) -> list[TopSeller]:
        """
        GET /market/top-sellers?kinds=dataset,api-wrapper
        Returns best-performing listings to replicate with improvements.
        """
        try:
            async with self._session.get(
                "/market/top-sellers?kinds=dataset,api-wrapper&limit=10&sort=sales"
            ) as resp:
                if resp.status != 200:
                    logger.warning("Top-sellers API returned %s", resp.status)
                    return []
                data = await resp.json()
                sellers = []
                for item in data.get("listings", []):
                    sellers.append(TopSeller(
                        listing_id=str(item["id"]),
                        title=item.get("title", ""),
                        category=item.get("category", ""),
                        good_kind=GoodKind(item.get("kind", "dataset")),
                        sales_count=item.get("sales_count", 0),
                        avg_rating=item.get("avg_rating", 0.0),
                        price_usdc=item.get("price_usdc", 0.0),
                        seller=item.get("seller", ""),
                        metadata_uri=item.get("metadata_uri", ""),
                    ))
                return sellers
        except aiohttp.ClientError as exc:
            logger.warning("Top-sellers fetch error: %s", exc)
            return []

    # ── Opportunity builders ──────────────────────────────────────────────────

    def _gaps_to_opportunities(self, gaps: list[MarketGap]) -> list[CreationOpportunity]:
        return [
            CreationOpportunity(
                good_kind=gap.good_kind,
                title=self._gap_title(gap),
                description=self._gap_description(gap),
                category=gap.category,
                rationale=(
                    f"High demand ({gap.search_volume} searches) "
                    f"with only {gap.listing_count} listings. "
                    f"Opportunity score: {gap.opportunity_score:.2f}"
                ),
                source="gap",
                estimated_price_usdc=gap.avg_price_usdc or self._default_price(gap.good_kind),
            )
            for gap in gaps
        ]

    def _clones_to_opportunities(self, sellers: list[TopSeller]) -> list[CreationOpportunity]:
        return [
            CreationOpportunity(
                good_kind=seller.good_kind,
                title=f"{seller.title} — Enhanced",
                description=(
                    f"Improved version of top-selling '{seller.title}' "
                    f"({seller.sales_count} sales, {seller.avg_rating:.1f}★)"
                ),
                category=seller.category,
                rationale=(
                    f"Top seller with {seller.sales_count} sales. "
                    f"Clone + improve to capture existing demand."
                ),
                source="clone",
                reference_listing_id=seller.listing_id,
                estimated_price_usdc=seller.price_usdc * 1.10,  # slight premium
            )
            for seller in sellers
        ]

    @staticmethod
    def _gap_title(gap: MarketGap) -> str:
        titles = {
            "crypto-prices":   "Crypto Price History — Top 100 Tokens",
            "weather-history": "Weather History Dataset — 5 Years Global",
            "fx-rates":        "FX Rates API Wrapper — 170 Currencies",
            "country-data":    "Country Data API — Demographics + Economy",
            "llm-training":    "LLM Instruction Dataset — 1K Examples",
        }
        return titles.get(gap.category, f"{gap.category.replace('-', ' ').title()} Dataset")

    @staticmethod
    def _gap_description(gap: MarketGap) -> str:
        return (
            f"Synthetic {gap.good_kind} for the '{gap.category}' category. "
            f"Auto-generated to fill market gap "
            f"({gap.search_volume} searches, {gap.listing_count} existing listings)."
        )

    def _default_price(self, kind: GoodKind) -> float:
        if kind == GoodKind.DATASET:
            return self.config.dataset_base_price_usdc
        return self.config.api_wrapper_base_price_usdc
