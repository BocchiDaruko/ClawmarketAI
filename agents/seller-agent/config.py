"""
ClawmarketAI — Seller Agent
config.py · Agent configuration and validation
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, validator


# ─── Enums ───────────────────────────────────────────────────────────────────

class GoodType(str, Enum):
    COMPUTE    = "compute"
    DATA       = "data"
    AI_SERVICE = "ai-service"
    API_ACCESS = "api-access"


class PricingMode(str, Enum):
    DEMAND      = "demand"       # more requests  → higher price
    COMPETITION = "competition"  # match / undercut similar listings
    TIME_DECAY  = "time-decay"   # discount unsold listings over time
    FLOOR_PRICE = "floor-price"  # fixed margin, never go below cost


class FulfillmentMode(str, Enum):
    ONCHAIN  = "onchain"   # Escrow.release() only
    API      = "api"       # REST delivery only
    BOTH     = "both"      # on-chain settlement + API delivery


# ─── Per-good listing template ────────────────────────────────────────────────

class GoodTemplate(BaseModel):
    good_type: GoodType
    title: str
    description: str
    base_price_usdc: float      = Field(..., gt=0)
    cost_usdc: float            = Field(..., ge=0, description="Agent's cost to deliver")
    min_margin_pct: float       = Field(default=0.10, ge=0.0,
                                         description="Minimum margin (0.10 = 10%)")
    metadata_uri: str           = Field(default="", description="IPFS URI for item metadata")
    delivery_config: dict       = Field(default_factory=dict,
                                         description="Payload sent to buyer on fulfillment")
    max_concurrent_listings: int= Field(default=5, ge=1)


# ─── Seller Agent Config ──────────────────────────────────────────────────────

class SellerAgentConfig(BaseModel):

    # Identity
    agent_id: str               = Field(..., description="e.g. 'seller-001'")

    # Wallet & network
    wallet_address: str         = Field(...)
    private_key_env: str        = Field(default="SELLER_AGENT_PRIVATE_KEY")
    rpc_url: str                = Field(default="https://mainnet.base.org")
    chain_id: int               = Field(default=8453)

    # Contracts
    marketplace_address: str    = Field(...)
    smart_wallet_address: str   = Field(...)
    escrow_address: str         = Field(...)
    reputation_address: str     = Field(...)

    # API
    api_base_url: str           = Field(...)
    api_key_env: str            = Field(default="CLAWMARKET_API_KEY")

    # Goods catalogue
    goods: list[GoodTemplate]   = Field(..., min_items=1)

    # Pricing
    pricing_modes: list[PricingMode] = Field(
        default=[PricingMode.DEMAND, PricingMode.COMPETITION,
                 PricingMode.TIME_DECAY, PricingMode.FLOOR_PRICE]
    )

    # Pricing parameters
    demand_surge_pct: float     = Field(default=0.05, ge=0.0,
                                         description="Price increase per demand unit (5%)")
    demand_window_minutes: int  = Field(default=60,
                                         description="Window for demand measurement")
    competition_undercut_pct: float = Field(default=0.02, ge=0.0,
                                             description="Undercut competitor by 2%")
    time_decay_pct_per_hour: float  = Field(default=0.01, ge=0.0,
                                             description="Discount 1% per hour unsold")
    time_decay_max_pct: float       = Field(default=0.30,
                                             description="Never discount more than 30%")

    # Fulfillment
    fulfillment_mode: FulfillmentMode = Field(default=FulfillmentMode.BOTH)
    delivery_timeout_seconds: int     = Field(default=120, ge=10)

    # Operational
    scan_interval_seconds: int  = Field(default=45, ge=5)
    max_retries: int            = Field(default=3, ge=1)
    tx_timeout_seconds: int     = Field(default=60, ge=10)
    relist_after_minutes: int   = Field(default=30,
                                         description="Re-list expired listings after N minutes")

    def get_private_key(self) -> str:
        key = os.getenv(self.private_key_env)
        if not key:
            raise EnvironmentError(f"Private key not found in '{self.private_key_env}'")
        return key

    def get_api_key(self) -> str:
        key = os.getenv(self.api_key_env)
        if not key:
            raise EnvironmentError(f"API key not found in '{self.api_key_env}'")
        return key

    class Config:
        use_enum_values = True
