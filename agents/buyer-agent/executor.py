"""
ClawmarketAI — Buyer Agent
executor.py · Transaction Executor
Handles on-chain purchases via SmartWallet → Escrow → Marketplace.sol on Base.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum

import aiohttp
from eth_account import Account
from web3 import AsyncWeb3
from web3.exceptions import TransactionNotFound

from .config import BuyerAgentConfig
from .scanner import Listing
from .strategy import ScoredListing

logger = logging.getLogger("buyer_agent.executor")


# ─── Result ───────────────────────────────────────────────────────────────────

class PurchaseStatus(str, Enum):
    SUCCESS   = "success"
    FAILED    = "failed"
    REVERTED  = "reverted"
    TIMEOUT   = "timeout"
    SKIPPED   = "skipped"    # e.g. listing bought by someone else first


@dataclass
class PurchaseResult:
    listing_id: str
    status: PurchaseStatus
    tx_hash: str | None = None
    gas_used: int | None = None
    price_usdc: float = 0.0
    error: str | None = None


# ─── ABI snippets ─────────────────────────────────────────────────────────────

MARKETPLACE_ABI = [
    {
        "name": "buy",
        "type": "function",
        "stateMutability": "payable",
        "inputs": [
            {"name": "listingId", "type": "uint256"},
            {"name": "buyer",     "type": "address"},
        ],
        "outputs": [],
    },
    {
        "name": "isAvailable",
        "type": "function",
        "stateMutability": "view",
        "inputs":  [{"name": "listingId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
]

SMART_WALLET_ABI = [
    {
        "name": "execute",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "target", "type": "address"},
            {"name": "value",  "type": "uint256"},
            {"name": "data",   "type": "bytes"},
        ],
        "outputs": [{"name": "returnData", "type": "bytes"}],
    },
    {
        "name": "spendingLimit",
        "type": "function",
        "stateMutability": "view",
        "inputs":  [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

USDC_ABI = [
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount",  "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs":  [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

# USDC on Base Mainnet
USDC_ADDRESS_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


# ─── Executor ─────────────────────────────────────────────────────────────────

class TransactionExecutor:
    """
    Executes purchases through the SmartWallet → Escrow → Marketplace pipeline.
    Also confirms purchases via REST API after on-chain settlement.
    """

    def __init__(
        self,
        config: BuyerAgentConfig,
        w3: AsyncWeb3,
        http_session: aiohttp.ClientSession,
    ):
        self.config   = config
        self._w3      = w3
        self._session = http_session
        self._account = Account.from_key(config.get_private_key())

        # Contracts
        self._marketplace  = w3.eth.contract(
            address=config.marketplace_address, abi=MARKETPLACE_ABI
        )
        self._smart_wallet = w3.eth.contract(
            address=config.smart_wallet_address, abi=SMART_WALLET_ABI
        )
        self._usdc = w3.eth.contract(
            address=USDC_ADDRESS_BASE, abi=USDC_ABI
        )

    # ── Public interface ──────────────────────────────────────────────────────

    async def execute_purchase(self, candidate: ScoredListing) -> PurchaseResult:
        """
        Full purchase flow:
        1. Verify listing still available on-chain
        2. Approve USDC spending via SmartWallet
        3. Call Marketplace.buy() through SmartWallet.execute()
        4. Wait for receipt
        5. Confirm purchase via REST API
        """
        lst = candidate.listing
        logger.info(
            "→ Attempting purchase: listing=%s price=%.2f USDC reason='%s'",
            lst.listing_id, lst.price_usdc, candidate.reason,
        )

        for attempt in range(1, self.config.max_retries + 1):
            try:
                result = await self._try_purchase(lst)
                if result.status == PurchaseStatus.SUCCESS:
                    await self._notify_api(result)
                return result

            except Exception as exc:
                logger.warning(
                    "Purchase attempt %d/%d failed for listing %s: %s",
                    attempt, self.config.max_retries, lst.listing_id, exc,
                )
                if attempt < self.config.max_retries:
                    await asyncio.sleep(2 ** attempt)  # exponential backoff

        return PurchaseResult(
            listing_id=lst.listing_id,
            status=PurchaseStatus.FAILED,
            price_usdc=lst.price_usdc,
            error="Max retries exceeded",
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _try_purchase(self, lst: Listing) -> PurchaseResult:
        """Single purchase attempt."""

        # 1. Confirm listing is still available on-chain
        available = await self._marketplace.functions.isAvailable(
            int(lst.listing_id)
        ).call()
        if not available:
            logger.info("Listing %s no longer available — skipping", lst.listing_id)
            return PurchaseResult(
                listing_id=lst.listing_id,
                status=PurchaseStatus.SKIPPED,
                price_usdc=lst.price_usdc,
                error="Listing no longer available",
            )

        # 2. Check USDC balance
        price_raw = int(lst.price_usdc * 1e6)
        balance   = await self._usdc.functions.balanceOf(
            self.config.wallet_address
        ).call()
        if balance < price_raw:
            raise ValueError(
                f"Insufficient USDC: have {balance/1e6:.2f}, need {lst.price_usdc:.2f}"
            )

        # 3. Approve USDC for the escrow contract (via SmartWallet)
        approve_data = self._usdc.encodeABI(
            fn_name="approve",
            args=[self.config.escrow_address, price_raw],
        )
        await self._send_smart_wallet_tx(
            target=USDC_ADDRESS_BASE,
            value=0,
            data=approve_data,
            label=f"USDC approve {lst.price_usdc:.2f} for listing {lst.listing_id}",
        )

        # 4. Call Marketplace.buy() through SmartWallet
        buy_data = self._marketplace.encodeABI(
            fn_name="buy",
            args=[int(lst.listing_id), self.config.wallet_address],
        )
        tx_hash, gas_used = await self._send_smart_wallet_tx(
            target=self.config.marketplace_address,
            value=0,
            data=buy_data,
            label=f"buy listing {lst.listing_id}",
        )

        logger.info(
            "✓ Purchase confirmed: listing=%s tx=%s gas=%s",
            lst.listing_id, tx_hash, gas_used,
        )
        return PurchaseResult(
            listing_id=lst.listing_id,
            status=PurchaseStatus.SUCCESS,
            tx_hash=tx_hash,
            gas_used=gas_used,
            price_usdc=lst.price_usdc,
        )

    async def _send_smart_wallet_tx(
        self,
        target: str,
        value: int,
        data: bytes,
        label: str = "",
    ) -> tuple[str, int]:
        """
        Builds, signs, and broadcasts a transaction via SmartWallet.execute().
        Returns (tx_hash_hex, gas_used).
        """
        nonce    = await self._w3.eth.get_transaction_count(self._account.address)
        gas_price = await self._w3.eth.gas_price

        tx = await self._smart_wallet.functions.execute(
            target, value, data
        ).build_transaction({
            "from":     self._account.address,
            "nonce":    nonce,
            "gasPrice": gas_price,
            "chainId":  self.config.chain_id,
        })

        # Estimate gas with a 20% buffer
        estimated = await self._w3.eth.estimate_gas(tx)
        tx["gas"] = int(estimated * 1.20)

        signed  = self._account.sign_transaction(tx)
        tx_hash = await self._w3.eth.send_raw_transaction(signed.rawTransaction)
        tx_hash_hex = tx_hash.hex()
        logger.debug("Broadcast tx %s (%s)", tx_hash_hex, label)

        # Wait for receipt
        receipt = await self._wait_for_receipt(tx_hash_hex)
        if receipt["status"] == 0:
            raise RuntimeError(
                f"Transaction {tx_hash_hex} reverted on-chain"
            )

        return tx_hash_hex, receipt["gasUsed"]

    async def _wait_for_receipt(self, tx_hash: str, poll_interval: float = 2.0) -> dict:
        """Poll for transaction receipt until confirmed or timeout."""
        deadline = asyncio.get_event_loop().time() + self.config.tx_timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            try:
                receipt = await self._w3.eth.get_transaction_receipt(tx_hash)
                if receipt is not None:
                    return dict(receipt)
            except TransactionNotFound:
                pass
            await asyncio.sleep(poll_interval)

        raise TimeoutError(
            f"Transaction {tx_hash} not confirmed within {self.config.tx_timeout_seconds}s"
        )

    async def _notify_api(self, result: PurchaseResult):
        """POST /purchases — notify the REST API after on-chain settlement."""
        payload = {
            "listing_id": result.listing_id,
            "buyer":      self.config.wallet_address,
            "tx_hash":    result.tx_hash,
            "price_usdc": result.price_usdc,
        }
        try:
            async with self._session.post("/purchases", json=payload) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    logger.warning("API purchase notification failed: %s — %s", resp.status, body)
                else:
                    logger.debug("API notified of purchase %s", result.listing_id)
        except aiohttp.ClientError as exc:
            logger.warning("API notification error: %s", exc)
