"""
ClawmarketAI — Buyer Agent
tests/test_strategy.py · Unit tests for the Strategy Engine
"""

import pytest
from unittest.mock import MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from agents.buyer_agent.config import BuyerAgentConfig, Strategy
from agents.buyer_agent.scanner import Listing
from agents.buyer_agent.strategy import StrategyEngine


# ─── Fixtures ─────────────────────────────────────────────────────────────────

BASE_CONFIG = dict(
    agent_id="test-buyer",
    wallet_address="0xABC",
    marketplace_address="0x001",
    smart_wallet_address="0x002",
    escrow_address="0x003",
    reputation_address="0x004",
    api_base_url="http://localhost:8000",
    budget_usdc=1000.0,
    max_single_purchase=100.0,
)


def make_listing(
    lid="1",
    price=10.0,
    reputation=80.0,
    category="compute",
    available=True,
) -> Listing:
    return Listing(
        listing_id=lid,
        seller="0xSELLER",
        title=f"Listing {lid}",
        category=category,
        price_usdc=price,
        reputation_score=reputation,
        available=available,
    )


def make_engine(strategy: str, **overrides) -> StrategyEngine:
    cfg = BuyerAgentConfig(
        **{**BASE_CONFIG, "strategy": strategy, **overrides}
    )
    return StrategyEngine(cfg)


# ─── Hard filter tests ────────────────────────────────────────────────────────

class TestHardFilters:
    def test_filters_wrong_category(self):
        engine = make_engine("lowest-price", categories=["compute"])
        results = engine.evaluate([make_listing(category="data")])
        assert results == []

    def test_filters_low_reputation(self):
        engine = make_engine("lowest-price", min_reputation_score=75.0)
        results = engine.evaluate([make_listing(reputation=50.0)])
        assert results == []

    def test_filters_over_single_purchase_limit(self):
        engine = make_engine("lowest-price", max_single_purchase=20.0)
        results = engine.evaluate([make_listing(price=50.0)])
        assert results == []

    def test_filters_over_remaining_budget(self):
        engine = make_engine("lowest-price")
        # spent_usdc brings remaining below price
        results = engine.evaluate([make_listing(price=50.0)], spent_usdc=970.0)
        assert results == []

    def test_passes_all_filters(self):
        engine = make_engine("lowest-price")
        results = engine.evaluate([make_listing(price=10.0, reputation=80.0)])
        assert len(results) == 1


# ─── Strategy: lowest-price ───────────────────────────────────────────────────

class TestLowestPrice:
    def test_lower_price_scores_higher(self):
        engine = make_engine("lowest-price")
        cheap  = make_listing("cheap", price=5.0)
        pricey = make_listing("pricey", price=20.0)
        results = engine.evaluate([cheap, pricey])
        assert results[0].listing.listing_id == "cheap"

    def test_overpriced_gets_negative_score(self):
        engine = make_engine("lowest-price", max_price_premium=0.05)
        avg_price = 10.0
        # 50% above avg → exceeds 5% premium
        listing = make_listing(price=15.0)
        results = engine.evaluate([listing] + [make_listing(f"l{i}", price=10.0) for i in range(5)])
        overpriced = next((r for r in results if r.listing.listing_id == listing.listing_id), None)
        if overpriced:
            assert overpriced.score < 0


# ─── Strategy: best-reputation ────────────────────────────────────────────────

class TestBestReputation:
    def test_higher_reputation_scores_higher(self):
        engine = make_engine("best-reputation")
        high = make_listing("high-rep", reputation=95.0)
        low  = make_listing("low-rep",  reputation=75.0)
        results = engine.evaluate([high, low])
        assert results[0].listing.listing_id == "high-rep"

    def test_score_normalized_0_to_1(self):
        engine = make_engine("best-reputation")
        listing = make_listing(reputation=80.0)
        results = engine.evaluate([listing])
        assert abs(results[0].score - 0.8) < 0.01


# ─── Strategy: value-score ────────────────────────────────────────────────────

class TestValueScore:
    def test_value_score_between_0_and_1(self):
        engine = make_engine("value-score", weight_price=0.6, weight_reputation=0.4)
        results = engine.evaluate([make_listing(price=10.0, reputation=80.0)])
        assert 0.0 <= results[0].score <= 1.0

    def test_weights_respected(self):
        # reputation-heavy weight → high-rep listing wins even if slightly pricier
        engine = make_engine("value-score", weight_price=0.2, weight_reputation=0.8)
        high_rep  = make_listing("hr", price=15.0, reputation=95.0)
        low_price = make_listing("lp", price=5.0,  reputation=72.0)
        results = engine.evaluate([high_rep, low_price])
        assert results[0].listing.listing_id == "hr"


# ─── Strategy: budget-limit ───────────────────────────────────────────────────

class TestBudgetLimit:
    def test_score_is_positive(self):
        engine = make_engine("budget-limit")
        results = engine.evaluate([make_listing(price=30.0, reputation=80.0)])
        assert results[0].score > 0

    def test_larger_purchase_gets_utilization_bonus(self):
        engine = make_engine("budget-limit", max_single_purchase=100.0)
        large = make_listing("large", price=90.0, reputation=80.0)
        small = make_listing("small", price=10.0, reputation=80.0)
        results = engine.evaluate([large, small])
        # Large purchase should score higher due to utilization bonus
        assert results[0].listing.listing_id == "large"


# ─── Sorting ──────────────────────────────────────────────────────────────────

class TestSorting:
    def test_results_sorted_best_first(self):
        engine = make_engine("best-reputation")
        listings = [
            make_listing("a", reputation=70.0),
            make_listing("b", reputation=95.0),
            make_listing("c", reputation=82.0),
        ]
        results = engine.evaluate(listings)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)
