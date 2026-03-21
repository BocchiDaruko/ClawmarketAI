"""
ClawmarketAI — Arbitrage Agent
evaluator.py · Opportunity Evaluator
Scores and ranks arbitrage opportunities by net profit, risk, and execution speed.
Applies three sequential filters: profit → risk → speed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from .config import ArbitrageAgentConfig
from .scanner import MarketListing, PriceCluster, SubvaluedListing

logger = logging.getLogger("arbitrage_agent.evaluator")


# ─── Opportunity types ────────────────────────────────────────────────────────

class OpportunityType(str, Enum):
    SAME_GOOD  = "same-good"    # buy cheapest, resell at cluster avg/max
    SUBVALUED  = "subvalued"    # buy undervalued listing, resell at category avg


@dataclass
class ArbitrageOpportunity:
    opp_type: OpportunityType
    buy_listing: MarketListing      # the listing to purchase
    buy_price_usdc: float
    resell_price_usdc: float        # target resell price
    gross_profit_usdc: float        # before fees and gas
    net_profit_usdc: float          # after all costs
    net_profit_pct: float           # net / buy_price
    fee_cost_usdc: float
    gas_cost_usdc: float
    risk_score: float               # 0 = low risk, 1 = high risk
    speed_score: float              # 0 = slow, 1 = urgent (listing expiring soon)
    final_score: float              # composite ranking score
    rationale: str


# ─── Evaluator ────────────────────────────────────────────────────────────────

class OpportunityEvaluator:
    """
    Converts raw scanner output (clusters + subvalued listings) into
    ranked, actionable ArbitrageOpportunity objects.

    Scoring pipeline per candidate:
      1. Profit filter  — net profit > min_profit_usdc AND > min_profit_pct
      2. Risk filter    — seller reputation + listing age within bounds
      3. Speed filter   — flag listings expiring soon as higher priority
      4. Final score    = 0.6 × profit_norm + 0.3 × (1 - risk) + 0.1 × speed
    """

    def __init__(self, config: ArbitrageAgentConfig):
        self.config = config

    # ── Public interface ──────────────────────────────────────────────────────

    def evaluate(
        self,
        clusters: list[PriceCluster],
        subvalued: list[SubvaluedListing],
        deployed_capital: float = 0.0,
    ) -> list[ArbitrageOpportunity]:
        """
        Evaluate all opportunities and return them sorted best-first.
        deployed_capital is the USDC already locked in open positions.
        """
        available = self.config.deployable_capital - deployed_capital
        candidates: list[ArbitrageOpportunity] = []

        # Same-good cluster opportunities
        for cluster in clusters:
            opp = self._eval_cluster(cluster, available)
            if opp:
                candidates.append(opp)

        # Subvalued listing opportunities
        for sv in subvalued:
            opp = self._eval_subvalued(sv, available)
            if opp:
                candidates.append(opp)

        # Sort: highest final_score first
        candidates.sort(key=lambda o: o.final_score, reverse=True)
        logger.info(
            "Evaluated %d clusters + %d subvalued → %d actionable opportunities",
            len(clusters), len(subvalued), len(candidates),
        )
        return candidates

    # ── Cluster evaluation ────────────────────────────────────────────────────

    def _eval_cluster(
        self, cluster: PriceCluster, available_capital: float
    ) -> ArbitrageOpportunity | None:
        """
        Strategy: buy the cheapest listing in the cluster,
        relist at (avg_price × (1 + target_resell_premium_pct)).
        """
        buy     = cluster.cheapest
        avg     = cluster.average_price
        resell  = avg * (1.0 + self.config.target_resell_premium_pct)

        return self._build_opportunity(
            opp_type=OpportunityType.SAME_GOOD,
            buy_listing=buy,
            resell_price=resell,
            available_capital=available_capital,
            rationale=(
                f"Same-good cluster: buy @ {buy.price_usdc:.2f}, "
                f"relist @ {resell:.2f} (avg {avg:.2f}, "
                f"spread {cluster.price_spread_pct*100:.1f}%)"
            ),
        )

    # ── Subvalued evaluation ──────────────────────────────────────────────────

    def _eval_subvalued(
        self, sv: SubvaluedListing, available_capital: float
    ) -> ArbitrageOpportunity | None:
        """
        Strategy: buy listing priced below category avg,
        relist at category_avg × (1 + target_resell_premium_pct).
        """
        resell = sv.category_avg * (1.0 + self.config.target_resell_premium_pct)

        return self._build_opportunity(
            opp_type=OpportunityType.SUBVALUED,
            buy_listing=sv.listing,
            resell_price=resell,
            available_capital=available_capital,
            rationale=(
                f"Subvalued: buy @ {sv.listing.price_usdc:.2f}, "
                f"relist @ {resell:.2f} "
                f"({sv.discount_pct*100:.1f}% below category avg {sv.category_avg:.2f})"
            ),
        )

    # ── Shared opportunity builder ─────────────────────────────────────────────

    def _build_opportunity(
        self,
        opp_type: OpportunityType,
        buy_listing: MarketListing,
        resell_price: float,
        available_capital: float,
        rationale: str,
    ) -> ArbitrageOpportunity | None:

        buy_price = buy_listing.price_usdc

        # ── 1. Capital check ────────────────────────────────────────────────
        if buy_price > available_capital:
            logger.debug("Skip %s: buy price %.2f > available %.2f",
                         buy_listing.listing_id, buy_price, available_capital)
            return None
        if buy_price > self.config.max_position_usdc:
            logger.debug("Skip %s: exceeds max_position_usdc %.2f",
                         buy_listing.listing_id, self.config.max_position_usdc)
            return None

        # ── 2. Profit filter ─────────────────────────────────────────────────
        fee_cost  = buy_price * self.config.total_fee_pct
        gas_cost  = self.config.estimated_gas_usdc * 2   # buy tx + relist tx
        gross     = resell_price - buy_price
        net       = gross - fee_cost - gas_cost
        net_pct   = net / buy_price if buy_price > 0 else 0.0

        if net < self.config.min_profit_usdc:
            logger.debug("Skip %s: net profit %.4f < min %.4f",
                         buy_listing.listing_id, net, self.config.min_profit_usdc)
            return None
        if net_pct < self.config.min_profit_pct:
            logger.debug("Skip %s: net profit pct %.2f%% < min %.2f%%",
                         buy_listing.listing_id, net_pct * 100,
                         self.config.min_profit_pct * 100)
            return None

        # ── 3. Risk score ────────────────────────────────────────────────────
        # Low reputation = high risk; old listing = higher risk of expiry race
        rep_risk  = 1.0 - (buy_listing.reputation_score / 100.0)
        age_risk  = min(buy_listing.age_hours / self.config.max_listing_age_hours, 1.0)
        risk_score = 0.7 * rep_risk + 0.3 * age_risk

        # Risk hard ceiling: skip very risky positions
        if risk_score > 0.75:
            logger.debug("Skip %s: risk_score %.2f > 0.75",
                         buy_listing.listing_id, risk_score)
            return None

        # ── 4. Speed score ───────────────────────────────────────────────────
        # Listing near max_age → higher urgency → higher speed score
        speed_score = age_risk   # reuse age_risk as urgency proxy

        # ── 5. Final composite score ─────────────────────────────────────────
        # Normalize net profit: cap at 50% profit = score of 1.0
        profit_norm  = min(net_pct / 0.50, 1.0)
        final_score  = (
            0.60 * profit_norm
            + 0.30 * (1.0 - risk_score)
            + 0.10 * speed_score
        )

        return ArbitrageOpportunity(
            opp_type=opp_type,
            buy_listing=buy_listing,
            buy_price_usdc=buy_price,
            resell_price_usdc=round(resell_price, 4),
            gross_profit_usdc=round(gross, 4),
            net_profit_usdc=round(net, 4),
            net_profit_pct=round(net_pct, 4),
            fee_cost_usdc=round(fee_cost, 4),
            gas_cost_usdc=round(gas_cost, 4),
            risk_score=round(risk_score, 3),
            speed_score=round(speed_score, 3),
            final_score=round(final_score, 4),
            rationale=rationale,
        )
