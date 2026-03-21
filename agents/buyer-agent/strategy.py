"""
ClawmarketAI — Buyer Agent
strategy.py · Strategy Engine
Evaluates listings and returns a scored, filtered list of purchase candidates.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass

from .config import BuyerAgentConfig, Strategy
from .scanner import Listing

logger = logging.getLogger("buyer_agent.strategy")


# ─── Result ───────────────────────────────────────────────────────────────────

@dataclass
class ScoredListing:
    listing: Listing
    score: float            # Higher = more desirable
    reason: str             # Human-readable explanation of why this was scored


# ─── Strategy Engine ─────────────────────────────────────────────────────────

class StrategyEngine:
    """
    Applies the active strategy to a batch of listings and returns
    scored, filtered candidates ready for the executor.
    """

    def __init__(self, config: BuyerAgentConfig):
        self.config   = config
        self.strategy = Strategy(config.strategy)

    def evaluate(
        self,
        listings: list[Listing],
        spent_usdc: float = 0.0,
    ) -> list[ScoredListing]:
        """
        Filter and score listings.
        Returns candidates sorted best-first, skipping those that
        would violate budget constraints.
        """
        remaining_budget = self.config.budget_usdc - spent_usdc

        # 1. Hard filters (applied regardless of strategy)
        candidates = [
            lst for lst in listings
            if self._passes_hard_filters(lst, remaining_budget)
        ]

        if not candidates:
            logger.debug("No listings passed hard filters.")
            return []

        # 2. Market context (used by some strategies)
        avg_price = statistics.mean(c.price_usdc for c in candidates) if candidates else 0.0

        # 3. Score each candidate
        scored = [
            self._score(lst, avg_price)
            for lst in candidates
        ]

        # 4. Sort best-first
        scored.sort(key=lambda s: s.score, reverse=True)
        logger.info(
            "Strategy '%s' → %d/%d listings qualify. Top: %s (score=%.3f)",
            self.strategy, len(scored), len(listings),
            scored[0].listing.listing_id if scored else "—",
            scored[0].score if scored else 0.0,
        )
        return scored

    # ── Private helpers ───────────────────────────────────────────────────────

    def _passes_hard_filters(self, lst: Listing, remaining_budget: float) -> bool:
        """Filters that apply regardless of active strategy."""

        # Category filter
        if lst.category not in self.config.categories:
            return False

        # Reputation floor
        if lst.reputation_score < self.config.min_reputation_score:
            logger.debug(
                "Skip %s: reputation %.1f < min %.1f",
                lst.listing_id, lst.reputation_score, self.config.min_reputation_score,
            )
            return False

        # Budget ceiling per purchase
        if lst.price_usdc > self.config.max_single_purchase:
            logger.debug(
                "Skip %s: price %.2f > max_single_purchase %.2f",
                lst.listing_id, lst.price_usdc, self.config.max_single_purchase,
            )
            return False

        # Remaining session budget
        if lst.price_usdc > remaining_budget:
            logger.debug(
                "Skip %s: price %.2f > remaining budget %.2f",
                lst.listing_id, lst.price_usdc, remaining_budget,
            )
            return False

        return True

    def _score(self, lst: Listing, avg_price: float) -> ScoredListing:
        """Dispatch to the active strategy scorer."""
        match self.strategy:
            case Strategy.LOWEST_PRICE:
                return self._score_lowest_price(lst, avg_price)
            case Strategy.BEST_REPUTATION:
                return self._score_best_reputation(lst)
            case Strategy.VALUE_SCORE:
                return self._score_value(lst, avg_price)
            case Strategy.BUDGET_LIMIT:
                return self._score_budget_limit(lst, avg_price)
            case _:
                raise ValueError(f"Unknown strategy: {self.strategy}")

    # ── Strategy implementations ───────────────────────────────────────────────

    def _score_lowest_price(self, lst: Listing, avg_price: float) -> ScoredListing:
        """
        Score = inverse of price (normalized by avg).
        Rejects listings priced more than max_price_premium above avg.
        """
        if avg_price > 0:
            premium = (lst.price_usdc - avg_price) / avg_price
            if premium > self.config.max_price_premium:
                # Return a very low score instead of filtering (already passed hard filters)
                return ScoredListing(
                    listing=lst,
                    score=-1.0,
                    reason=f"Price {lst.price_usdc:.2f} is {premium*100:.1f}% above avg ({avg_price:.2f})",
                )
            score = 1.0 - (lst.price_usdc / (avg_price * 2))
        else:
            score = 1.0 / max(lst.price_usdc, 0.01)

        return ScoredListing(
            listing=lst,
            score=max(score, 0.0),
            reason=f"Lowest-price: {lst.price_usdc:.2f} USDC (avg {avg_price:.2f})",
        )

    def _score_best_reputation(self, lst: Listing) -> ScoredListing:
        """Score = normalized reputation (0–100 → 0.0–1.0)."""
        score = lst.reputation_score / 100.0
        return ScoredListing(
            listing=lst,
            score=score,
            reason=f"Reputation: {lst.reputation_score:.1f}/100",
        )

    def _score_value(self, lst: Listing, avg_price: float) -> ScoredListing:
        """
        Composite score = weight_price × (1 - norm_price)
                        + weight_reputation × norm_reputation

        norm_price      = price / (avg_price * 2)   capped [0, 1]
        norm_reputation = reputation / 100           [0, 1]
        """
        if avg_price > 0:
            norm_price = min(lst.price_usdc / (avg_price * 2), 1.0)
        else:
            norm_price = 0.5

        norm_rep = lst.reputation_score / 100.0

        score = (
            self.config.weight_price      * (1.0 - norm_price)
            + self.config.weight_reputation * norm_rep
        )
        return ScoredListing(
            listing=lst,
            score=score,
            reason=(
                f"Value-score: {score:.3f} "
                f"(price_w={self.config.weight_price:.1f}, "
                f"rep_w={self.config.weight_reputation:.1f}, "
                f"price={lst.price_usdc:.2f}, rep={lst.reputation_score:.1f})"
            ),
        )

    def _score_budget_limit(self, lst: Listing, avg_price: float) -> ScoredListing:
        """
        Prioritizes the best value-score while hard-enforcing budget.
        Uses value-score internally but adds a budget-utilization bonus
        (prefer purchases that use budget efficiently).
        """
        base = self._score_value(lst, avg_price)

        # Bonus: prefer listings that are a larger fraction of max_single_purchase
        # (avoids wasting budget capacity on tiny purchases)
        utilization = lst.price_usdc / self.config.max_single_purchase
        budget_bonus = utilization * 0.1   # small bonus, not dominant

        final_score = base.score + budget_bonus
        return ScoredListing(
            listing=lst,
            score=final_score,
            reason=f"Budget-limit: {base.reason} + utilization_bonus={budget_bonus:.3f}",
        )
