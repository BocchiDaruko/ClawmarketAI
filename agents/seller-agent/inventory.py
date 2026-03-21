"""
ClawmarketAI — Seller Agent
inventory.py · Inventory Manager
Tracks which goods the agent owns, what's listed, and listing expiry.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .config import GoodTemplate, SellerAgentConfig

logger = logging.getLogger("seller_agent.inventory")


# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class ActiveListing:
    listing_id: str
    good_type: str
    title: str
    current_price_usdc: float
    base_price_usdc: float
    cost_usdc: float
    listed_at: str              # ISO timestamp
    last_price_update: str      # ISO timestamp
    tx_hash: str | None = None
    sold: bool = False
    cancelled: bool = False
    demand_count: int = 0       # request count in demand window

    @property
    def age_hours(self) -> float:
        listed = datetime.fromisoformat(self.listed_at)
        return (datetime.now(timezone.utc) - listed).total_seconds() / 3600

    @property
    def is_active(self) -> bool:
        return not self.sold and not self.cancelled

    @property
    def margin_pct(self) -> float:
        if self.cost_usdc == 0:
            return 1.0
        return (self.current_price_usdc - self.cost_usdc) / self.cost_usdc


@dataclass
class SoldRecord:
    listing_id: str
    good_type: str
    title: str
    sale_price_usdc: float
    cost_usdc: float
    profit_usdc: float
    buyer: str
    tx_hash: str
    sold_at: str
    fulfillment_status: str = "pending"  # pending | delivered | failed


# ─── Inventory Manager ────────────────────────────────────────────────────────

class InventoryManager:
    """
    Manages the seller's active listings and sold history.
    Persists state to disk so listings survive restarts.
    """

    def __init__(self, config: SellerAgentConfig, state_dir: str = "./state"):
        self.config = config
        self._dir   = Path(state_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

        self._listings_path = self._dir / f"{config.agent_id}_listings.json"
        self._sales_path    = self._dir / f"{config.agent_id}_sales.json"

        self._listings: dict[str, ActiveListing] = {}
        self._sales:    list[SoldRecord]          = []
        self._load()

    # ── Listings ──────────────────────────────────────────────────────────────

    def add_listing(self, listing: ActiveListing):
        self._listings[listing.listing_id] = listing
        logger.info("Listing added: %s — %s @ %.2f USDC",
                    listing.listing_id, listing.title, listing.current_price_usdc)
        self._save()

    def update_price(self, listing_id: str, new_price: float):
        lst = self._listings.get(listing_id)
        if lst:
            lst.current_price_usdc   = new_price
            lst.last_price_update    = datetime.now(timezone.utc).isoformat()
            self._save()

    def mark_sold(self, listing_id: str, buyer: str, tx_hash: str) -> SoldRecord | None:
        lst = self._listings.get(listing_id)
        if not lst:
            return None
        lst.sold = True
        record = SoldRecord(
            listing_id=listing_id,
            good_type=lst.good_type,
            title=lst.title,
            sale_price_usdc=lst.current_price_usdc,
            cost_usdc=lst.cost_usdc,
            profit_usdc=lst.current_price_usdc - lst.cost_usdc,
            buyer=buyer,
            tx_hash=tx_hash,
            sold_at=datetime.now(timezone.utc).isoformat(),
        )
        self._sales.append(record)
        self._save()
        return record

    def mark_cancelled(self, listing_id: str):
        lst = self._listings.get(listing_id)
        if lst:
            lst.cancelled = True
            self._save()

    def increment_demand(self, listing_id: str):
        lst = self._listings.get(listing_id)
        if lst:
            lst.demand_count += 1
            self._save()

    def mark_delivered(self, listing_id: str):
        for sale in self._sales:
            if sale.listing_id == listing_id:
                sale.fulfillment_status = "delivered"
        self._save()

    # ── Queries ───────────────────────────────────────────────────────────────

    @property
    def active_listings(self) -> list[ActiveListing]:
        return [l for l in self._listings.values() if l.is_active]

    @property
    def sold_listings(self) -> list[SoldRecord]:
        return self._sales

    def get_listing(self, listing_id: str) -> ActiveListing | None:
        return self._listings.get(listing_id)

    def listings_by_type(self, good_type: str) -> list[ActiveListing]:
        return [l for l in self.active_listings if l.good_type == good_type]

    def count_active_by_type(self, good_type: str) -> int:
        return len(self.listings_by_type(good_type))

    def needs_relisting(self, good: GoodTemplate) -> bool:
        """True if this good type has fewer active listings than its max_concurrent."""
        active = self.count_active_by_type(good.good_type)
        return active < good.max_concurrent_listings

    def stale_listings(self, min_age_hours: float = 0.5) -> list[ActiveListing]:
        """Listings that have been active long enough for a price re-evaluation."""
        return [l for l in self.active_listings if l.age_hours >= min_age_hours]

    # ── Analytics ────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        total_profit = sum(s.profit_usdc for s in self._sales)
        return {
            "agent_id":       self.config.agent_id,
            "active_listings":len(self.active_listings),
            "total_sold":     len(self._sales),
            "total_profit_usdc": round(total_profit, 4),
            "pending_delivery": sum(1 for s in self._sales if s.fulfillment_status == "pending"),
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self):
        if self._listings_path.exists():
            try:
                data = json.loads(self._listings_path.read_text())
                self._listings = {k: ActiveListing(**v) for k, v in data.items()}
                logger.info("Loaded %d listings from disk", len(self._listings))
            except Exception as exc:
                logger.warning("Could not load listings: %s", exc)

        if self._sales_path.exists():
            try:
                data = json.loads(self._sales_path.read_text())
                self._sales = [SoldRecord(**s) for s in data]
                logger.info("Loaded %d sales records from disk", len(self._sales))
            except Exception as exc:
                logger.warning("Could not load sales: %s", exc)

    def _save(self):
        self._listings_path.write_text(
            json.dumps({k: asdict(v) for k, v in self._listings.items()}, indent=2)
        )
        self._sales_path.write_text(
            json.dumps([asdict(s) for s in self._sales], indent=2)
        )
