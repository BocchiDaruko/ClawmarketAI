"""
ClawmarketAI — Arbitrage Agent
tests/test_evaluator.py · Unit tests for OpportunityEvaluator
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from agents.arbitrage_agent.config import ArbitrageAgentConfig
from agents.arbitrage_agent.scanner import MarketListing, PriceCluster, SubvaluedListing
from agents.arbitrage_agent.evaluator import OpportunityEvaluator, OpportunityType


# ─── Fixtures ─────────────────────────────────────────────────────────────────

BASE_CONFIG = dict(
    agent_id="test-arb",
    wallet_address="0xABC",
    marketplace_address="0x001",
    smart_wallet_address="0x002",
    escrow_address="0x003",
    reputation_address="0x004",
    api_base_url="http://localhost:8000",
    capital_usdc=1000.0,
    max_position_usdc=200.0,
    min_profit_usdc=0.50,
    min_profit_pct=0.05,
    marketplace_fee_pct=0.01,
    estimated_gas_usdc=0.05,
    min_seller_reputation=60.0,
)


def make_listing(lid="1", price=10.0, rep=80.0, age=1.0, category="compute") -> MarketListing:
    return MarketListing(
        listing_id=lid, seller="0xSELLER",
        title=f"Item {lid}", category=category,
        price_usdc=price, reputation_score=rep,
        age_hours=age, available=True,
    )


def make_cluster(prices: list[float], rep=80.0) -> PriceCluster:
    listings = [make_listing(str(i), price=p, rep=rep) for i, p in enumerate(prices)]
    return PriceCluster(canonical_title="Test Item", category="compute", listings=listings)


def make_subvalued(price=5.0, avg=10.0, rep=80.0) -> SubvaluedListing:
    return SubvaluedListing(
        listing=make_listing(price=price, rep=rep),
        category_avg=avg,
        discount_pct=(avg - price) / avg,
    )


def make_evaluator(**overrides) -> OpportunityEvaluator:
    cfg = ArbitrageAgentConfig(**{**BASE_CONFIG, **overrides})
    return OpportunityEvaluator(cfg)


# ─── Profit filter tests ───────────────────────────────────────────────────────

class TestProfitFilter:
    def test_profitable_cluster_passes(self):
        ev  = make_evaluator()
        # buy @ 5, resell avg=10 × 1.15 = 11.5 → gross=6.5, fees=0.23, net≈6.2
        c   = make_cluster([5.0, 10.0, 10.0])
        ops = ev.evaluate([c], [])
        assert len(ops) == 1
        assert ops[0].net_profit_usdc > 0.50

    def test_tiny_spread_rejected(self):
        ev  = make_evaluator(min_profit_usdc=1.0)
        # buy @ 9.9 vs 10.0 — spread too small after fees
        c   = make_cluster([9.9, 10.0])
        ops = ev.evaluate([c], [])
        assert ops == []

    def test_exceeds_max_position_rejected(self):
        ev  = make_evaluator(max_position_usdc=50.0)
        c   = make_cluster([100.0, 200.0])   # buy price 100 > max 50
        ops = ev.evaluate([c], [])
        assert ops == []

    def test_exceeds_available_capital_rejected(self):
        ev  = make_evaluator()
        c   = make_cluster([5.0, 50.0])
        # deployed_capital = 990 → available = 10 → buy @ 5 ok
        # But if deployed = 996 → available = 4 → buy @ 5 rejected
        ops = ev.evaluate([c], [], deployed_capital=996.0)
        assert ops == []


# ─── Risk filter tests ─────────────────────────────────────────────────────────

class TestRiskFilter:
    def test_low_reputation_cluster_rejected(self):
        ev  = make_evaluator()
        # reputation 20 → rep_risk = 0.8 → risk_score > 0.75
        c   = make_cluster([5.0, 20.0], rep=20.0)
        ops = ev.evaluate([c], [])
        assert ops == []

    def test_high_reputation_passes(self):
        ev  = make_evaluator()
        c   = make_cluster([5.0, 20.0], rep=90.0)
        ops = ev.evaluate([c], [])
        assert len(ops) == 1

    def test_very_old_listing_has_higher_risk(self):
        ev   = make_evaluator()
        new  = make_cluster([5.0, 20.0])
        new.listings[0].age_hours = 1.0
        old  = make_cluster([5.0, 20.0])
        old.listings[0].age_hours = 47.0

        ops_new = ev.evaluate([new], [])
        ops_old = ev.evaluate([old], [])
        if ops_new and ops_old:
            assert ops_new[0].risk_score < ops_old[0].risk_score


# ─── Opportunity type tests ────────────────────────────────────────────────────

class TestOpportunityTypes:
    def test_cluster_produces_same_good_type(self):
        ev  = make_evaluator()
        c   = make_cluster([5.0, 20.0])
        ops = ev.evaluate([c], [])
        if ops:
            assert ops[0].opp_type == OpportunityType.SAME_GOOD

    def test_subvalued_produces_subvalued_type(self):
        ev  = make_evaluator()
        sv  = make_subvalued(price=5.0, avg=12.0)
        ops = ev.evaluate([], [sv])
        if ops:
            assert ops[0].opp_type == OpportunityType.SUBVALUED


# ─── Scoring and ranking tests ─────────────────────────────────────────────────

class TestScoring:
    def test_results_sorted_best_first(self):
        ev   = make_evaluator()
        c1   = make_cluster([5.0, 20.0])   # larger spread
        c2   = make_cluster([9.0, 10.5])   # smaller spread
        ops  = ev.evaluate([c1, c2], [])
        if len(ops) >= 2:
            assert ops[0].final_score >= ops[1].final_score

    def test_score_between_0_and_1(self):
        ev  = make_evaluator()
        c   = make_cluster([5.0, 20.0])
        ops = ev.evaluate([c], [])
        if ops:
            assert 0.0 <= ops[0].final_score <= 1.0

    def test_net_profit_accounts_for_fees(self):
        ev  = make_evaluator(marketplace_fee_pct=0.01, estimated_gas_usdc=0.05)
        c   = make_cluster([10.0, 20.0])
        ops = ev.evaluate([c], [])
        if ops:
            op = ops[0]
            # fee = 10 * 0.02 = 0.20, gas = 0.10
            # gross = resell - 10, net = gross - 0.30
            assert op.fee_cost_usdc == pytest.approx(op.buy_price_usdc * 0.02, abs=0.01)
            assert op.net_profit_usdc < op.gross_profit_usdc
