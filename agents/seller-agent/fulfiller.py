"""
ClawmarketAI — Seller Agent
fulfiller.py · Order Fulfiller
Listens for PurchaseCompleted events, releases Escrow, and delivers goods via API.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum

import aiohttp
from eth_account import Account
from web3 import AsyncWeb3

from .config import FulfillmentMode, GoodTemplate, SellerAgentConfig
from .inventory import InventoryManager, SoldRecord

logger = logging.getLogger("seller_agent.fulfiller")


# ─── Enums & Results ──────────────────────────────────────────────────────────

class FulfillmentStatus(str, Enum):
    SUCCESS          = "success"
    ESCROW_FAILED    = "escrow_failed"
    DELIVERY_FAILED  = "delivery_failed"
    NOT_FOUND        = "not_found"


@dataclass
class FulfillmentResult:
    listing_id: str
    buyer: str
    status: FulfillmentStatus
    tx_hash: str | None = None
    delivery_payload: dict | None = None
    error: str | None = None


# ─── ABI snippets ─────────────────────────────────────────────────────────────

ESCROW_ABI = [
    {
        "name": "release",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "listingId", "type": "uint256"},
            {"name": "seller",    "type": "address"},
        ],
        "outputs": [],
    },
    {
        "name": "isHeld",
        "type": "function",
        "stateMutability": "view",
        "inputs":  [{"name": "listingId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
]

MARKETPLACE_ABI_EVENTS = [
    {
        "name": "PurchaseCompleted",
        "type": "event",
        "inputs": [
            {"name": "listingId", "type": "uint256", "indexed": True},
            {"name": "buyer",     "type": "address",  "indexed": True},
            {"name": "seller",    "type": "address",  "indexed": False},
            {"name": "priceUsdc", "type": "uint256",  "indexed": False},
        ],
    }
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


# ─── Fulfiller ────────────────────────────────────────────────────────────────

class OrderFulfiller:
    """
    Monitors PurchaseCompleted events on Base.
    For each sale:
      1. Confirm Escrow holds funds
      2. Release Escrow → seller wallet  (on-chain settlement)
      3. Deliver access credentials/data to buyer via REST API
    """

    def __init__(
        self,
        config: SellerAgentConfig,
        w3: AsyncWeb3,
        http_session: aiohttp.ClientSession,
        inventory: InventoryManager,
    ):
        self.config     = config
        self._w3        = w3
        self._session   = http_session
        self._inventory = inventory
        self._account   = Account.from_key(config.get_private_key())
        self._mode      = FulfillmentMode(config.fulfillment_mode)

        self._escrow = w3.eth.contract(
            address=config.escrow_address, abi=ESCROW_ABI
        )
        self._marketplace = w3.eth.contract(
            address=config.marketplace_address, abi=MARKETPLACE_ABI_EVENTS
        )
        self._smart_wallet = w3.eth.contract(
            address=config.smart_wallet_address, abi=SMART_WALLET_ABI
        )

    # ── Public interface ──────────────────────────────────────────────────────

    async def poll_and_fulfill(self):
        """
        Poll for new PurchaseCompleted events and fulfill all pending orders.
        Designed to be called periodically from the main agent loop.
        """
        try:
            latest   = await self._w3.eth.block_number
            from_blk = max(0, latest - 20)   # last ~40 seconds on Base (2s blocks)

            events = await self._marketplace.events.PurchaseCompleted.get_logs(
                fromBlock=from_blk, toBlock=latest
            )
        except Exception as exc:
            logger.warning("PurchaseCompleted poll error: %s", exc)
            return

        for evt in events:
            listing_id = str(evt["args"]["listingId"])
            buyer      = evt["args"]["buyer"]
            seller     = evt["args"]["seller"]

            # Only process sales where we're the seller
            if seller.lower() != self.config.wallet_address.lower():
                continue

            # Avoid double-processing
            listing = self._inventory.get_listing(listing_id)
            if listing and listing.sold:
                continue

            logger.info("Order detected: listing=%s buyer=%s", listing_id, buyer)
            result = await self._fulfill(listing_id, buyer)

            if result.status == FulfillmentStatus.SUCCESS:
                logger.info("Fulfilled listing %s for %s | tx=%s",
                            listing_id, buyer, result.tx_hash)
            else:
                logger.error("Fulfillment failed for listing %s: %s",
                             listing_id, result.error)

    async def fulfill_by_id(self, listing_id: str, buyer: str) -> FulfillmentResult:
        """Manually trigger fulfillment for a specific listing (e.g. from API webhook)."""
        return await self._fulfill(listing_id, buyer)

    # ── Private ───────────────────────────────────────────────────────────────

    async def _fulfill(self, listing_id: str, buyer: str) -> FulfillmentResult:
        tx_hash = None
        delivery = None

        # Step 1: On-chain Escrow release
        if self._mode in (FulfillmentMode.ONCHAIN, FulfillmentMode.BOTH):
            try:
                tx_hash = await self._release_escrow(listing_id)
            except Exception as exc:
                error = f"Escrow release failed: {exc}"
                logger.error(error)
                return FulfillmentResult(
                    listing_id=listing_id, buyer=buyer,
                    status=FulfillmentStatus.ESCROW_FAILED, error=error,
                )

        # Step 2: API delivery
        if self._mode in (FulfillmentMode.API, FulfillmentMode.BOTH):
            try:
                delivery = await self._deliver_via_api(listing_id, buyer)
            except Exception as exc:
                error = f"API delivery failed: {exc}"
                logger.error(error)
                # On-chain already settled — mark partial failure
                return FulfillmentResult(
                    listing_id=listing_id, buyer=buyer,
                    status=FulfillmentStatus.DELIVERY_FAILED,
                    tx_hash=tx_hash, error=error,
                )

        # Step 3: Update inventory
        sale = self._inventory.mark_sold(listing_id, buyer, tx_hash or "")
        if sale:
            self._inventory.mark_delivered(listing_id)

        return FulfillmentResult(
            listing_id=listing_id,
            buyer=buyer,
            status=FulfillmentStatus.SUCCESS,
            tx_hash=tx_hash,
            delivery_payload=delivery,
        )

    async def _release_escrow(self, listing_id: str) -> str:
        """Call Escrow.release() via SmartWallet and return tx hash."""
        # Verify escrow still holds funds
        is_held = await self._escrow.functions.isHeld(int(listing_id)).call()
        if not is_held:
            raise ValueError(f"Escrow not holding funds for listing {listing_id}")

        data = self._escrow.encodeABI(
            fn_name="release",
            args=[int(listing_id), self.config.wallet_address],
        )
        tx_hash = await self._send_smart_wallet_tx(
            target=self.config.escrow_address,
            data=data,
            label=f"escrow.release({listing_id})",
        )
        logger.info("Escrow released for listing %s → tx %s", listing_id, tx_hash)
        return tx_hash

    async def _deliver_via_api(self, listing_id: str, buyer: str) -> dict:
        """
        POST /fulfillment — instructs the ClawmarketAI backend to deliver
        the good's access credentials/payload to the buyer.
        The backend knows the delivery_config per listing type (set at listing time).
        """
        listing = self._inventory.get_listing(listing_id)
        good_template = self._find_good_template(listing.good_type if listing else "")

        payload = {
            "listing_id":      listing_id,
            "buyer":           buyer,
            "seller":          self.config.wallet_address,
            "good_type":       listing.good_type if listing else "",
            "delivery_config": good_template.delivery_config if good_template else {},
        }

        async with self._session.post("/fulfillment", json=payload) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                raise RuntimeError(
                    f"Delivery API returned {resp.status}: {body}"
                )
            data = await resp.json()
            logger.info("API delivery confirmed for listing %s → buyer %s",
                        listing_id, buyer)
            return data

    def _find_good_template(self, good_type: str) -> GoodTemplate | None:
        for good in self.config.goods:
            if good.good_type == good_type:
                return good
        return None

    async def _send_smart_wallet_tx(
        self, target: str, data: bytes, label: str = ""
    ) -> str:
        from web3.exceptions import TransactionNotFound

        nonce     = await self._w3.eth.get_transaction_count(self._account.address)
        gas_price = await self._w3.eth.gas_price

        tx = await self._smart_wallet.functions.execute(
            target, 0, data
        ).build_transaction({
            "from":     self._account.address,
            "nonce":    nonce,
            "gasPrice": gas_price,
            "chainId":  self.config.chain_id,
        })
        estimated = await self._w3.eth.estimate_gas(tx)
        tx["gas"]  = int(estimated * 1.20)

        signed   = self._account.sign_transaction(tx)
        tx_hash  = await self._w3.eth.send_raw_transaction(signed.rawTransaction)
        tx_hex   = tx_hash.hex()
        logger.debug("Broadcast tx %s (%s)", tx_hex, label)

        deadline = asyncio.get_event_loop().time() + self.config.tx_timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            try:
                receipt = await self._w3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    if receipt["status"] == 0:
                        raise RuntimeError(f"Tx {tx_hex} reverted")
                    return tx_hex
            except TransactionNotFound:
                pass
            await asyncio.sleep(2)

        raise TimeoutError(f"Tx {tx_hex} not confirmed in {self.config.tx_timeout_seconds}s")
