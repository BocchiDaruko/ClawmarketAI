"""
ClawmarketAI — Buyer Agent
config.py · Agent configuration and validation
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, validator


# ─── Enums ───────────────────────────────────────────────────────────────────

class Strategy(str, Enum):
    LOWEST_PRICE     = "lowest-price"
    BEST_REPUTATION  = "best-reputation"
    VALUE_SCORE      = "value-score"
    BUDGET_LIMIT     = "budget-limit"


class Category(str, Enum):
    COMPUTE    = "compute"
    DATA       = "data"
    API_ACCESS = "api-access"
    AI_SERVICE = "ai-service"
    DIGITAL    = "digital"


class RiskTolerance(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


# ─── Agent Config ─────────────────────────────────────────────────────────────

class BuyerAgentConfig(BaseModel):
    """
    Full configuration for a BuyerAgent instance.
    Loaded from a JSON file or env variables.
    """

    # Identity
    agent_id: str = Field(..., description="Unique agent identifier (e.g. 'buyer-001')")

    # Wallet & network
    wallet_address: str       = Field(..., description="Non-custodial smart wallet address")
    private_key_env: str      = Field(default="BUYER_AGENT_PRIVATE_KEY",
                                      description="Env var name holding the private key")
    rpc_url: str              = Field(default="https://mainnet.base.org",
                                      description="Base network RPC endpoint")
    chain_id: int             = Field(default=8453, description="Base Mainnet chain ID")

    # Contract addresses
    marketplace_address: str  = Field(..., description="Marketplace.sol address")
    smart_wallet_address: str = Field(..., description="SmartWallet.sol address")
    escrow_address: str       = Field(..., description="Escrow.sol address")
    reputation_address: str   = Field(..., description="ReputationScore.sol address")

    # API
    api_base_url: str         = Field(..., description="ClawmarketAI REST API base URL")
    api_key_env: str          = Field(default="CLAWMARKET_API_KEY",
                                      description="Env var name holding the API key")

    # Budget
    budget_usdc: float        = Field(..., gt=0, description="Total USDC budget for this session")
    max_single_purchase: float= Field(..., gt=0, description="Max USDC per individual purchase")
    reinvest_ratio: float     = Field(default=0.75, ge=0.0, le=1.0,
                                      description="Fraction of profit to reinvest (0–1)")

    # Strategy
    strategy: Strategy        = Field(default=Strategy.VALUE_SCORE)
    categories: list[Category]= Field(default=[Category.COMPUTE, Category.DATA,
                                               Category.API_ACCESS])
    risk_tolerance: RiskTolerance = Field(default=RiskTolerance.LOW)

    # Strategy weights (for value-score)
    weight_price:      float  = Field(default=0.6, ge=0.0, le=1.0)
    weight_reputation: float  = Field(default=0.4, ge=0.0, le=1.0)

    # Strategy thresholds
    min_reputation_score: float = Field(default=70.0, ge=0.0, le=100.0,
                                         description="Minimum on-chain reputation to consider")
    max_price_premium: float    = Field(default=0.05,
                                         description="Max % above market avg to overpay (0.05 = 5%)")

    # Operational
    scan_interval_seconds: int  = Field(default=30, ge=5,
                                         description="Seconds between market scans")
    max_retries: int            = Field(default=3, ge=1)
    tx_timeout_seconds: int     = Field(default=60, ge=10)

    @validator("weight_price", "weight_reputation", always=True)
    def weights_sum_to_one(cls, v, values):
        if "weight_price" in values:
            total = values["weight_price"] + v
            if not (0.99 <= total <= 1.01):
                raise ValueError(
                    f"weight_price + weight_reputation must sum to 1.0 (got {total:.2f})"
                )
        return v

    @validator("max_single_purchase", always=True)
    def single_purchase_within_budget(cls, v, values):
        if "budget_usdc" in values and v > values["budget_usdc"]:
            raise ValueError(
                "max_single_purchase cannot exceed budget_usdc"
            )
        return v

    def get_private_key(self) -> str:
        key = os.getenv(self.private_key_env)
        if not key:
            raise EnvironmentError(
                f"Private key not found in env var '{self.private_key_env}'"
            )
        return key

    def get_api_key(self) -> str:
        key = os.getenv(self.api_key_env)
        if not key:
            raise EnvironmentError(
                f"API key not found in env var '{self.api_key_env}'"
            )
        return key

    class Config:
        use_enum_values = True
