"""
ClawmarketAI — Creator Agent
config.py · Configuration and validation
"""

from __future__ import annotations

import os
from enum import Enum
from pydantic import BaseModel, Field


# ─── Enums ────────────────────────────────────────────────────────────────────

class GoodKind(str, Enum):
    DATASET     = "dataset"
    API_WRAPPER = "api-wrapper"


class CreationStrategy(str, Enum):
    GAP_FIRST    = "gap-first"     # detect demand gaps, fall back to cloning
    CLONE_FIRST  = "clone-first"   # clone top sellers, fall back to gaps
    BALANCED     = "balanced"      # alternate between both


# ─── Config ───────────────────────────────────────────────────────────────────

class CreatorAgentConfig(BaseModel):

    # Identity
    agent_id: str               = Field(..., description="e.g. 'creator-001'")

    # Wallet & network (Base)
    wallet_address: str         = Field(...)
    private_key_env: str        = Field(default="CREATOR_AGENT_PRIVATE_KEY")
    rpc_url: str                = Field(default="https://mainnet.base.org")
    chain_id: int               = Field(default=8453)

    # Contracts
    marketplace_address: str    = Field(...)
    smart_wallet_address: str   = Field(...)
    escrow_address: str         = Field(...)

    # ClawmarketAI REST API
    api_base_url: str           = Field(...)
    api_key_env: str            = Field(default="CLAWMARKET_API_KEY")

    # Claude API (for idea generation and dataset synthesis)
    claude_api_key_env: str     = Field(default="ANTHROPIC_API_KEY")
    claude_model: str           = Field(default="claude-sonnet-4-20250514")

    # IPFS pinning (e.g. Pinata, web3.storage)
    ipfs_api_url: str           = Field(default="https://api.pinata.cloud/pinning/pinFileToIPFS")
    ipfs_api_key_env: str       = Field(default="IPFS_API_KEY")

    # Creation strategy
    good_kinds: list[GoodKind]  = Field(default=[GoodKind.DATASET, GoodKind.API_WRAPPER])
    creation_strategy: CreationStrategy = Field(default=CreationStrategy.GAP_FIRST)

    # Dataset generation settings
    dataset_min_rows: int       = Field(default=100, ge=10)
    dataset_max_rows: int       = Field(default=2000, le=50000)
    dataset_formats: list[str]  = Field(default=["jsonl", "csv", "parquet"])

    # API wrapper settings
    public_api_allowlist: list[str] = Field(
        default=[
            "https://api.coinpaprika.com",
            "https://api.open-meteo.com",
            "https://restcountries.eu",
            "https://api.frankfurter.app",
            "https://pokeapi.co",
        ],
        description="Public APIs the agent is allowed to wrap and resell",
    )

    # Economics
    dataset_base_price_usdc: float  = Field(default=5.0, gt=0)
    api_wrapper_base_price_usdc: float = Field(default=3.0, gt=0)
    min_margin_pct: float           = Field(default=0.40, ge=0.0,
                                             description="Creator targets 40% margin")

    # Operational
    scan_interval_seconds: int  = Field(default=300, ge=60,
                                         description="5 min between creation cycles")
    max_goods_per_cycle: int    = Field(default=3, ge=1)
    max_retries: int            = Field(default=3, ge=1)
    tx_timeout_seconds: int     = Field(default=60, ge=10)

    # Quality gates
    min_quality_score: float    = Field(default=0.70, ge=0.0, le=1.0,
                                         description="Reject goods scoring below this")

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

    def get_claude_api_key(self) -> str:
        key = os.getenv(self.claude_api_key_env)
        if not key:
            raise EnvironmentError(f"Claude API key not in '{self.claude_api_key_env}'")
        return key

    def get_ipfs_api_key(self) -> str:
        key = os.getenv(self.ipfs_api_key_env)
        if not key:
            raise EnvironmentError(f"IPFS API key not in '{self.ipfs_api_key_env}'")
        return key

    class Config:
        use_enum_values = True
