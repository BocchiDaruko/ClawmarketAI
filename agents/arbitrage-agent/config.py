"""
ClawmarketAI — Arbitrage Agent
config.py · Configuration and validation
"""

from __future__ import annotations

import os
from pydantic import BaseModel, Field, validator


class ArbitrageAgentConfig(BaseModel):

    # Identity
    agent_id: str               = Field(..., description="e.g. 'arbitrage-001'")

    # Wallet & network (Base)
    wallet_address: str         = Field(...)
    private_key_env: str        = Field(default="ARBITRAGE_AGENT_PRIVATE_KEY")
    rpc_url: str                = Field(default="https://mainnet.base.org")
    chain_id: int               = Field(default=8453)

    # Contracts
    marketplace_address: str    = Field(...)
    smart_wallet_address: str   = Field(...)
    escrow_address: str         = Field(...)
    reputation_address: str     = Field(...)

    # ClawmarketAI REST API
    api_base_url: str           = Field(...)
    api_key_env: str            = Field(default="CLAWMARKET_API_KEY")

    # Capital
    capital_usdc: float         = Field(..., gt=0,
                                         description="Total USDC available for arbitrage")
    max_position_usdc: float    = Field(..., gt=0,
                                         description="Max USDC per single arbitrage position")
    reserve_pct: float          = Field(default=0.10, ge=0.0, le=0.5,
                                         description="Keep this % of capital as reserve (gas + fees)")

    # Profit thresholds
    min_profit_usdc: float      = Field(default=0.50, gt=0,
                                         description="Minimum net profit to execute (after fees+gas)")
    min_profit_pct: float       = Field(default=0.05, gt=0,
                                         description="Min profit as % of buy price (0.05 = 5%)")
    target_resell_premium_pct: float = Field(default=0.15, gt=0,
                                              description="Relist at buy_price × (1 + this)")

    # Fee model
    marketplace_fee_pct: float  = Field(default=0.01,
                                         description="ClawmarketAI fee per trade (1%)")
    estimated_gas_usdc: float   = Field(default=0.05,
                                         description="Estimated gas cost per tx in USDC")

    # Risk controls
    min_seller_reputation: float= Field(default=60.0, ge=0.0, le=100.0,
                                         description="Min seller reputation to buy from")
    max_listing_age_hours: float= Field(default=48.0,
                                         description="Skip listings older than this")
    max_concurrent_positions: int = Field(default=5, ge=1,
                                           description="Max simultaneous open arbitrage positions")
    resell_timeout_hours: float = Field(default=24.0,
                                         description="Cancel unsold resell listing after N hours")

    # Same-good clustering
    similarity_threshold: float = Field(default=0.80, ge=0.0, le=1.0,
                                         description="Min title similarity to cluster as same good")

    # Operational
    scan_interval_seconds: int  = Field(default=20, ge=5,
                                         description="Seconds between full market scans")
    max_retries: int            = Field(default=3, ge=1)
    tx_timeout_seconds: int     = Field(default=60, ge=10)

    @validator("max_position_usdc")
    def position_within_capital(cls, v, values):
        if "capital_usdc" in values and v > values["capital_usdc"]:
            raise ValueError("max_position_usdc cannot exceed capital_usdc")
        return v

    def get_private_key(self) -> str:
        key = os.getenv(self.private_key_env)
        if not key:
            raise EnvironmentError(f"Private key not in '{self.private_key_env}'")
        return key

    def get_api_key(self) -> str:
        key = os.getenv(self.api_key_env)
        if not key:
            raise EnvironmentError(f"API key not in '{self.api_key_env}'")
        return key

    @property
    def deployable_capital(self) -> float:
        """Capital available to deploy (excluding reserve)."""
        return self.capital_usdc * (1.0 - self.reserve_pct)

    @property
    def total_fee_pct(self) -> float:
        """Total round-trip fee: 2 marketplace fees (buy + resell)."""
        return self.marketplace_fee_pct * 2

    class Config:
        use_enum_values = True
