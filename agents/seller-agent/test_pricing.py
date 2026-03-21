"""
ClawmarketAI — Seller Agent
tests/test_pricing.py · Unit tests for DynamicPricingEngine
"""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from agents.seller_agent.config import SellerAgentConfig, GoodTemplate, PricingMode
from agents.seller_agent.inventory import ActiveListing
from agents.seller_agent.pricing import DynamicPricingEngine


# ─── Helpers ──────────────────────────────────────────────────────────────────

BASE_GOOD = GoodTemplate(
    good_type="compute",
    title="GPU 1h",
    description="test",
    base_price_usdc=10.0,
    cost_usdc=5.0,
    min_margin_pct=0.10,
)

BASE_CONFIG = dict(
    agent_id="test-seller",
    wallet_address="0xABC",
    marketplace_address="0x001",
    smart_wallet_address="0x002",
    escrow_address="0x003",
    reputation_address="0x004",
    api_base_url="http://localhost:8000",
    goods=[BASE_GOOD],
)


def make_listing(
    price=10.0,
    base_price=10.0,
    cost=5.0,
    demand_count=0,
    age_hours=0.0,
    good_type="compute",
) -> ActiveListing:
    listed = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    return ActiveListing(
        listing_id="1",
        good_type=good_type,
        title="GPU 1h",
        current_price_usdc=price,
        base_price_usdc=base_price,
        cost_usdc=cost,
        listed_at=listed.isoformat(),
        last_price_update=listed.isoformat(),
        demand_count=demand_count,
    )


def make_engine(modes: list[str], **overrides) -> DynamicPricingEngine:
    session = AsyncMock()
    cfg = SellerAgentConfig(
        **{**BASE_CONFIG, "pricing_modes": modes, **overrides}
    )
    engine = DynamicPricingEngine(cfg, session)
    return engine


# ─── Floor price ──────────────────────────────────────────────────────────────

class TestFloorPrice:
    def test_floor_is_cost_plus_margin(self):
        engine  = make_engine(["floor-price"])
        listing = make_listing(cost=5.0)
        floor   = engine._floor_price(listing)
        assert abs(floor - 5.5) < 0.001   # 5.0 × 1.10

    def test_price_never_goes_below_floor(self):
        engine  = make_engine(["floor-price", "time-decay"],
                               time_decay_pct_per_hour=0.50,
                               time_decay_max_pct=0.90)
        listing = make_listing(price=10.0, base_price=10.0, cost=5.0, age_hours=20.0)
        decision = asyncio.get_event_loop().run_until_complete(engine.reprice(listing))
        assert decision.new_price >= decision.floor_price


# ─── Demand surge ─────────────────────────────────────────────────────────────

class TestDemandPricing:
    def test_demand_increases_price(self):
        engine  = make_engine(["demand"], demand_surge_pct=0.10)
        listing = make_listing(price=10.0, base_price=10.0, demand_count=3)
        new_p, reason = engine._apply_demand(10.0, listing)
        assert new_p > 10.0
        assert "demand surge" in reason

    def test_zero_demand_no_change(self):
        engine  = make_engine(["demand"])
        listing = make_listing(demand_count=0)
        new_p, reason = engine._apply_demand(10.0, listing)
        assert new_p == 10.0
        assert reason == ""

    def test_demand_capped_at_3x(self):
        engine  = make_engine(["demand"], demand_surge_pct=1.0)
        listing = make_listing(demand_count=100)
        new_p, _ = engine._apply_demand(10.0, listing)
        assert new_p <= 30.0   # 3× cap


# ─── Time decay ───────────────────────────────────────────────────────────────

class TestTimeDecay:
    def test_fresh_listing_no_decay(self):
        engine  = make_engine(["time-decay"])
        listing = make_listing(age_hours=0.5)
        new_p, reason = engine._apply_time_decay(10.0, listing)
        assert new_p == 10.0
        assert reason == ""

    def test_old_listing_discounted(self):
        engine  = make_engine(["time-decay"], time_decay_pct_per_hour=0.05)
        listing = make_listing(age_hours=4.0)
        new_p, reason = engine._apply_time_decay(10.0, listing)
        assert new_p < 10.0
        assert "time decay" in reason

    def test_decay_capped_at_max(self):
        engine  = make_engine(["time-decay"],
                               time_decay_pct_per_hour=0.10,
                               time_decay_max_pct=0.30)
        listing = make_listing(age_hours=100.0)
        new_p, _ = engine._apply_time_decay(10.0, listing)
        assert new_p >= 10.0 * 0.70   # max 30% off


# ─── Competition ──────────────────────────────────────────────────────────────

class TestCompetition:
    def test_undercuts_higher_market_price(self):
        engine = make_engine(["competition"], competition_undercut_pct=0.02)
        new_p, reason = engine._apply_competition(15.0, market_price=12.0)
        assert new_p < 12.0
        assert "undercut" in reason

    def test_no_change_if_already_cheaper(self):
        engine = make_engine(["competition"], competition_undercut_pct=0.02)
        new_p, reason = engine._apply_competition(8.0, market_price=12.0)
        assert new_p == 8.0
        assert "competitive" in reason

    def test_no_market_price_no_change(self):
        engine = make_engine(["competition"])
        new_p, reason = engine._apply_competition(10.0, market_price=None)
        assert new_p == 10.0
        assert reason == ""


# ─── Initial price ────────────────────────────────────────────────────────────

class TestInitialPrice:
    def test_initial_price_above_cost(self):
        engine = make_engine(["floor-price"])
        engine._fetch_market_price = AsyncMock(return_value=None)
        price = asyncio.get_event_loop().run_until_complete(
            engine.initial_price(10.0, "compute", cost=5.0)
        )
        assert price >= 5.0 * 1.05

    def test_initial_price_undercuts_market(self):
        engine = make_engine(["competition"], competition_undercut_pct=0.02)
        engine._fetch_market_price = AsyncMock(return_value=8.0)
        price = asyncio.get_event_loop().run_until_complete(
            engine.initial_price(10.0, "compute", cost=2.0)
        )
        assert price <= 8.0


# ─── Composite reprice ────────────────────────────────────────────────────────

class TestCompositeReprice:
    def test_reprice_returns_valid_decision(self):
        engine  = make_engine(["demand", "time-decay", "floor-price"])
        engine._fetch_market_price = AsyncMock(return_value=None)
        listing = make_listing(price=10.0, base_price=10.0, demand_count=2, age_hours=2.0)
        decision = asyncio.get_event_loop().run_until_complete(engine.reprice(listing))
        assert decision.new_price >= decision.floor_price
        assert decision.new_price > 0

    def test_unchanged_listing_not_flagged_as_changed(self):
        engine  = make_engine(["floor-price"])
        engine._fetch_market_price = AsyncMock(return_value=None)
        listing = make_listing(price=5.5, base_price=10.0, cost=5.0, age_hours=0.1)
        decision = asyncio.get_event_loop().run_until_complete(engine.reprice(listing))
        assert not decision.changed
