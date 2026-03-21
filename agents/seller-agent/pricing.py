"""
ClawmarketAI — Seller Agent
pricing.py · Dynamic Pricing Engine

Combines 4 pricing modes into a single optimal price per listing:
  - demand      : surge pricing based on recent request count
  - competition : undercut or match similar active listings
  - time-decay  : discount listings that haven't sold
  - floor-price : never sell below cost + min margin
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import aiohttp

from .config import PricingMode, SellerAgentConfig
from .inventory import ActiveListing

logger = logging.getLogger("seller_agent.pricing")


# ─── Result ───────────────────────────────────────────────────────────────────

@dataclass
class PriceDecision:
    listing_id: str
    old_price: float
    new_price: float
    floor_price: float
    changed: bool
    reasons: list[str]


# ─── Pricing Engine ───────────────────────────────────────────────────────────

class DynamicPricingEngine:
    """
    Computes the optimal price for each active listing by composing
    all enabled pricing modes sequentially.

    Order of application:
      1. Start from base_price_usdc
      2. Apply demand surge      (+%)
      3. Apply time-decay decay  (-%)
      4. Apply competition floor (clamp to market)
      5. Enforce floor price     (never below cost + margin)
    """

    def __init__(self, config: SellerAgentConfig, http_session: aiohttp.ClientSession):
        self.config   = config
        self._session = http_session
        self._modes   = set(PricingMode(m) for m in config.pricing_modes)

    # ── Public interface ──────────────────────────────────────────────────────

    async def reprice(self, listing: ActiveListing) -> PriceDecision:
        """Compute the new optimal price for a single listing."""
        price   = listing.base_price_usdc
        reasons: list[str] = []

        # 1. Demand surge
        if PricingMode.DEMAND in self._modes:
            price, r = self._apply_demand(price, listing)
            if r:
                reasons.append(r)

        # 2. Time decay
        if PricingMode.TIME_DECAY in self._modes:
            price, r = self._apply_time_decay(price, listing)
            if r:
                reasons.append(r)

        # 3. Competition
        if PricingMode.COMPETITION in self._modes:
            market_price = await self._fetch_market_price(listing.good_type)
            price, r = self._apply_competition(price, market_price)
            if r:
                reasons.append(r)

        # 4. Floor price (always last — hard minimum)
        floor   = self._floor_price(listing)
        price   = max(price, floor)
        if PricingMode.FLOOR_PRICE in self._modes:
            reasons.append(f"floor={floor:.4f} USDC")

        # Round to 4 decimal places (USDC micro-precision)
        price   = round(price, 4)
        changed = abs(price - listing.current_price_usdc) > 0.0001

        return PriceDecision(
            listing_id=listing.listing_id,
            old_price=listing.current_price_usdc,
            new_price=price,
            floor_price=floor,
            changed=changed,
            reasons=reasons,
        )

    async def initial_price(self, base_price: float, good_type: str, cost: float) -> float:
        """Compute first listing price (no age, no demand history yet)."""
        price = base_price

        if PricingMode.COMPETITION in self._modes:
            market = await self._fetch_market_price(good_type)
            if market and market < price:
                undercut = market * (1 - self.config.competition_undercut_pct)
                floor    = cost * (1 + 0.10)   # 10% min margin at launch
                price    = max(undercut, floor)
                logger.debug("Initial price undercut: %.4f → %.4f (market %.4f)",
                             base_price, price, market)

        return round(max(price, cost * 1.05), 4)   # always at least 5% margin

    # ── Pricing mode implementations ──────────────────────────────────────────

    def _apply_demand(
        self, price: float, listing: ActiveListing
    ) -> tuple[float, str]:
        """
        Increase price proportionally to demand_count in the window.
        Each unit of demand adds demand_surge_pct to the price.
        Cap surge at 3× base price to prevent runaway pricing.
        """
        if listing.demand_count <= 0:
            return price, ""

        surge    = 1.0 + (listing.demand_count * self.config.demand_surge_pct)
        surge    = min(surge, 3.0)       # cap at 3×
        new_price = price * surge
        reason   = (f"demand surge ×{surge:.2f} "
                    f"({listing.demand_count} requests)")
        return new_price, reason

    def _apply_time_decay(
        self, price: float, listing: ActiveListing
    ) -> tuple[float, str]:
        """
        Reduce price by time_decay_pct_per_hour for each hour unsold.
        Never decay below (1 - time_decay_max_pct) of base price.
        """
        if listing.age_hours < 1.0:
            return price, ""

        decay_pct = min(
            listing.age_hours * self.config.time_decay_pct_per_hour,
            self.config.time_decay_max_pct,
        )
        new_price = price * (1.0 - decay_pct)
        reason    = (f"time decay -{decay_pct*100:.1f}% "
                     f"({listing.age_hours:.1f}h old)")
        return new_price, reason

    def _apply_competition(
        self, price: float, market_price: float | None
    ) -> tuple[float, str]:
        """
        If a market price exists and our price is above it,
        undercut by competition_undercut_pct.
        If we're already cheaper, keep our price.
        """
        if not market_price or market_price <= 0:
            return price, ""

        target = market_price * (1.0 - self.config.competition_undercut_pct)
        if price > target:
            reason = (f"competition: undercut {market_price:.4f} → {target:.4f} "
                      f"(-{self.config.competition_undercut_pct*100:.1f}%)")
            return target, reason

        return price, f"already competitive vs market {market_price:.4f}"

    def _floor_price(self, listing: ActiveListing) -> float:
        """Minimum allowed price = cost × (1 + min_margin_pct)."""
        # Find the matching good template for this listing type
        for good in self.config.goods:
            if good.good_type == listing.good_type:
                return listing.cost_usdc * (1.0 + good.min_margin_pct)
        return listing.cost_usdc * 1.05   # fallback: 5% margin

    # ── Market data ───────────────────────────────────────────────────────────

    async def _fetch_market_price(self, good_type: str) -> float | None:
        """
        GET /market/average-price?category=<type>
        Returns the average active listing price for the good type.
        """
        try:
            async with self._session.get(
                f"/market/average-price?category={good_type}"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data.get("average_price_usdc", 0)) or None
        except aiohttp.ClientError as exc:
            logger.warning("Market price fetch failed for '%s': %s", good_type, exc)
        return None
