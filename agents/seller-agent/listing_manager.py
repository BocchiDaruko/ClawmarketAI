"""
ClawmarketAI — Seller Agent
listing_manager.py · Listing Manager
Creates, updates, and cancels listings on-chain via Marketplace.sol
and keeps the REST API in sync.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiohttp
from eth_account import Account
from web3 import AsyncWeb3

from .config import GoodTemplate, SellerAgentConfig
from .inventory import ActiveListing, InventoryManager
from .pricing import DynamicPricingEngine, PriceDecision

logger = logging.getLogger("seller_agent.listing_manager")


# ─── ABI snippets ─────────────────────────────────────────────────────────────

MARKETPLACE_ABI = [
    {
        "name": "createListing",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "seller",      "type": "address"},
            {"name": "priceUsdc",   "type": "uint256"},
            {"name": "category",    "type": "string"},
            {"name": "metadataUri", "type": "string"},
        ],
        "outputs": [{"name": "listingId", "type": "uint256"}],
    },
    {
        "name": "updatePrice",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "listingId",  "type": "uint256"},
            {"name": "newPrice",   "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "name": "cancelListing",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "listingId", "type": "uint256"}],
        "outputs": [],
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
]


# ─── Listing Manager ──────────────────────────────────────────────────────────

class ListingManager:
    """
    Handles on-chain listing lifecycle:
      - createListing → new listing on Marketplace.sol
      - updatePrice   → reprice existing listing
      - cancelListing → delist
    Also syncs all state changes to the REST API.
    """

    def __init__(
        self,
        config: SellerAgentConfig,
        w3: AsyncWeb3,
        http_session: aiohttp.ClientSession,
        inventory: InventoryManager,
        pricing: DynamicPricingEngine,
    ):
        self.config    = config
        self._w3       = w3
        self._session  = http_session
        self._inventory = inventory
        self._pricing  = pricing
        self._account  = Account.from_key(config.get_private_key())

        self._marketplace  = w3.eth.contract(
            address=config.marketplace_address, abi=MARKETPLACE_ABI
        )
        self._smart_wallet = w3.eth.contract(
            address=config.smart_wallet_address, abi=SMART_WALLET_ABI
        )

    # ── Public interface ──────────────────────────────────────────────────────

    async def publish_listing(self, good: GoodTemplate) -> ActiveListing | None:
        """
        Compute initial price, create on-chain listing, and register in inventory.
        Returns the new ActiveListing or None on failure.
        """
        price = await self._pricing.initial_price(
            base_price=good.base_price_usdc,
            good_type=good.good_type,
            cost=good.cost_usdc,
        )
        price_raw = int(price * 1e6)   # USDC 6 decimals

        try:
            data = self._marketplace.encodeABI(
                fn_name="createListing",
                args=[
                    self.config.wallet_address,
                    price_raw,
                    good.good_type,
                    good.metadata_uri,
                ],
            )
            tx_hash, listing_id = await self._send_tx(data, label=f"createListing {good.title}")
        except Exception as exc:
            logger.error("createListing failed for '%s': %s", good.title, exc)
            return None

        now = datetime.now(timezone.utc).isoformat()
        listing = ActiveListing(
            listing_id=str(listing_id),
            good_type=good.good_type,
            title=good.title,
            current_price_usdc=price,
            base_price_usdc=good.base_price_usdc,
            cost_usdc=good.cost_usdc,
            listed_at=now,
            last_price_update=now,
            tx_hash=tx_hash,
        )
        self._inventory.add_listing(listing)
        await self._api_notify_listing(listing, action="create")
        logger.info("Published: listing=%s '%s' @ %.4f USDC tx=%s",
                    listing_id, good.title, price, tx_hash)
        return listing

    async def reprice_listing(self, listing: ActiveListing) -> PriceDecision:
        """Evaluate and apply a new price to an active listing."""
        decision = await self._pricing.reprice(listing)

        if not decision.changed:
            logger.debug("No reprice needed for listing %s (price=%.4f)",
                         listing.listing_id, listing.current_price_usdc)
            return decision

        price_raw = int(decision.new_price * 1e6)
        try:
            data = self._marketplace.encodeABI(
                fn_name="updatePrice",
                args=[int(listing.listing_id), price_raw],
            )
            await self._send_tx(data, label=f"updatePrice {listing.listing_id}")
            self._inventory.update_price(listing.listing_id, decision.new_price)
            await self._api_notify_listing(listing, action="reprice",
                                           new_price=decision.new_price)
            logger.info(
                "Repriced listing %s: %.4f → %.4f USDC | reasons: %s",
                listing.listing_id, decision.old_price, decision.new_price,
                "; ".join(decision.reasons),
            )
        except Exception as exc:
            logger.error("updatePrice failed for listing %s: %s",
                         listing.listing_id, exc)

        return decision

    async def cancel_listing(self, listing_id: str) -> bool:
        """Cancel an on-chain listing and update inventory."""
        try:
            data = self._marketplace.encodeABI(
                fn_name="cancelListing",
                args=[int(listing_id)],
            )
            await self._send_tx(data, label=f"cancelListing {listing_id}")
            self._inventory.mark_cancelled(listing_id)
            await self._api_notify_cancel(listing_id)
            logger.info("Cancelled listing %s", listing_id)
            return True
        except Exception as exc:
            logger.error("cancelListing failed for %s: %s", listing_id, exc)
            return False

    # ── Transaction helpers ───────────────────────────────────────────────────

    async def _send_tx(self, encoded_data: bytes, label: str = "") -> tuple[str, int]:
        """
        Send a transaction via SmartWallet.execute() and wait for receipt.
        Returns (tx_hash_hex, return_value_as_int).
        """
        import asyncio
        from web3.exceptions import TransactionNotFound

        nonce     = await self._w3.eth.get_transaction_count(self._account.address)
        gas_price = await self._w3.eth.gas_price

        tx = await self._smart_wallet.functions.execute(
            self.config.marketplace_address, 0, encoded_data
        ).build_transaction({
            "from":     self._account.address,
            "nonce":    nonce,
            "gasPrice": gas_price,
            "chainId":  self.config.chain_id,
        })
        estimated = await self._w3.eth.estimate_gas(tx)
        tx["gas"] = int(estimated * 1.20)

        signed  = self._account.sign_transaction(tx)
        tx_hash = await self._w3.eth.send_raw_transaction(signed.rawTransaction)
        tx_hex  = tx_hash.hex()
        logger.debug("Broadcast tx %s (%s)", tx_hex, label)

        # Wait for receipt
        deadline = asyncio.get_event_loop().time() + self.config.tx_timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            try:
                receipt = await self._w3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    if receipt["status"] == 0:
                        raise RuntimeError(f"Tx {tx_hex} reverted")
                    # Extract return value (listing ID for createListing)
                    return_int = int(receipt.get("logs", [{}])[0].get("data", "0x0"), 16) \
                        if receipt.get("logs") else 0
                    return tx_hex, return_int
            except TransactionNotFound:
                pass
            await asyncio.sleep(2)

        raise TimeoutError(f"Tx {tx_hex} not confirmed in {self.config.tx_timeout_seconds}s")

    # ── API sync ──────────────────────────────────────────────────────────────

    async def _api_notify_listing(
        self,
        listing: ActiveListing,
        action: str,
        new_price: float | None = None,
    ):
        payload = {
            "listing_id":   listing.listing_id,
            "seller":       self.config.wallet_address,
            "good_type":    listing.good_type,
            "title":        listing.title,
            "price_usdc":   new_price or listing.current_price_usdc,
            "action":       action,
        }
        try:
            async with self._session.post("/listings", json=payload) as resp:
                if resp.status not in (200, 201):
                    logger.warning("API listing notify failed: %s", resp.status)
        except aiohttp.ClientError as exc:
            logger.warning("API listing notify error: %s", exc)

    async def _api_notify_cancel(self, listing_id: str):
        try:
            async with self._session.delete(f"/listings/{listing_id}") as resp:
                if resp.status not in (200, 204):
                    logger.warning("API cancel notify failed: %s", resp.status)
        except aiohttp.ClientError as exc:
            logger.warning("API cancel notify error: %s", exc)
