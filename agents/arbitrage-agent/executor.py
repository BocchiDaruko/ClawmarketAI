"""
ClawmarketAI — Arbitrage Agent
executor.py · Flash Executor
Executes arbitrage: buy the underpriced listing, then immediately
create a new listing at the target resell price.
Also monitors open positions and cancels stale resell listings.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import aiohttp
from eth_account import Account
from web3 import AsyncWeb3
from web3.exceptions import TransactionNotFound

from .config import ArbitrageAgentConfig
from .evaluator import ArbitrageOpportunity

logger = logging.getLogger("arbitrage_agent.executor")


# ─── Position tracking ────────────────────────────────────────────────────────

class PositionStatus(str, Enum):
    BUYING    = "buying"
    RELISTING = "relisting"
    OPEN      = "open"       # buy confirmed, resell listing live
    SOLD      = "sold"       # resell completed
    CANCELLED = "cancelled"  # resell listing cancelled (timeout)
    FAILED    = "failed"


@dataclass
class ArbitragePosition:
    opportunity_id: str            # listing_id of the bought item
    buy_listing_id: str
    buy_price_usdc: float
    buy_tx: str | None
    resell_listing_id: str | None
    resell_price_usdc: float
    expected_net_profit: float
    status: PositionStatus
    opened_at: str
    closed_at: str | None = None
    actual_profit_usdc: float | None = None

    @property
    def age_hours(self) -> float:
        opened = datetime.fromisoformat(self.opened_at)
        return (datetime.now(timezone.utc) - opened).total_seconds() / 3600


@dataclass
class ExecutionResult:
    success: bool
    position: ArbitragePosition | None
    error: str | None = None


# ─── ABIs ─────────────────────────────────────────────────────────────────────

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
        "name": "cancelListing",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "listingId", "type": "uint256"}],
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

USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


# ─── Flash Executor ───────────────────────────────────────────────────────────

class FlashExecutor:
    """
    Executes the full arbitrage cycle:
      1. Verify listing still available
      2. Approve USDC + buy via SmartWallet
      3. Immediately create a new resell listing at target price
      4. Monitor open positions → cancel timed-out resell listings
    """

    def __init__(
        self,
        config: ArbitrageAgentConfig,
        w3: AsyncWeb3,
        session: aiohttp.ClientSession,
    ):
        self.config   = config
        self._w3      = w3
        self._session = session
        self._account = Account.from_key(config.get_private_key())

        self._marketplace  = w3.eth.contract(address=config.marketplace_address,
                                              abi=MARKETPLACE_ABI)
        self._smart_wallet = w3.eth.contract(address=config.smart_wallet_address,
                                              abi=SMART_WALLET_ABI)
        self._usdc         = w3.eth.contract(address=USDC_BASE, abi=USDC_ABI)

        # Open positions (listing_id → position)
        self._positions: dict[str, ArbitragePosition] = {}

    # ── Public interface ──────────────────────────────────────────────────────

    @property
    def open_positions(self) -> list[ArbitragePosition]:
        return [p for p in self._positions.values()
                if p.status in (PositionStatus.OPEN, PositionStatus.RELISTING,
                                PositionStatus.BUYING)]

    @property
    def deployed_capital(self) -> float:
        return sum(p.buy_price_usdc for p in self.open_positions)

    async def execute(self, opp: ArbitrageOpportunity) -> ExecutionResult:
        """Buy the listing and immediately relist at profit price."""
        lid = opp.buy_listing.listing_id
        logger.info(
            "Executing arb: buy listing=%s @ %.4f → resell @ %.4f | "
            "net=%.4f USDC (%.1f%%) score=%.3f",
            lid, opp.buy_price_usdc, opp.resell_price_usdc,
            opp.net_profit_usdc, opp.net_profit_pct * 100, opp.final_score,
        )

        position = ArbitragePosition(
            opportunity_id=lid,
            buy_listing_id=lid,
            buy_price_usdc=opp.buy_price_usdc,
            buy_tx=None,
            resell_listing_id=None,
            resell_price_usdc=opp.resell_price_usdc,
            expected_net_profit=opp.net_profit_usdc,
            status=PositionStatus.BUYING,
            opened_at=datetime.now(timezone.utc).isoformat(),
        )
        self._positions[lid] = position

        for attempt in range(1, self.config.max_retries + 1):
            try:
                result = await self._try_execute(opp, position)
                return result
            except Exception as exc:
                logger.warning("Attempt %d/%d failed for listing %s: %s",
                               attempt, self.config.max_retries, lid, exc)
                if attempt < self.config.max_retries:
                    await asyncio.sleep(2 ** attempt)

        position.status = PositionStatus.FAILED
        return ExecutionResult(success=False, position=position,
                               error="Max retries exceeded")

    async def monitor_positions(self):
        """
        Check open resell listings:
        - If sold → mark as SOLD, record profit
        - If too old → cancel listing, mark CANCELLED
        Called periodically from the main loop.
        """
        for lid, pos in list(self._positions.items()):
            if pos.status != PositionStatus.OPEN:
                continue

            # Check if resell listing was purchased
            if pos.resell_listing_id:
                try:
                    available = await self._marketplace.functions.isAvailable(
                        int(pos.resell_listing_id)
                    ).call()
                    if not available:
                        pos.status             = PositionStatus.SOLD
                        pos.actual_profit_usdc = pos.expected_net_profit
                        pos.closed_at          = datetime.now(timezone.utc).isoformat()
                        logger.info("Position SOLD: buy=%s resell=%s profit=%.4f USDC",
                                    pos.buy_listing_id, pos.resell_listing_id,
                                    pos.actual_profit_usdc)
                        continue
                except Exception:
                    pass

            # Check timeout
            if pos.age_hours >= self.config.resell_timeout_hours and pos.resell_listing_id:
                logger.info("Position timeout: cancelling resell listing %s",
                            pos.resell_listing_id)
                await self._cancel_listing(pos.resell_listing_id)
                pos.status    = PositionStatus.CANCELLED
                pos.closed_at = datetime.now(timezone.utc).isoformat()

    # ── Private ───────────────────────────────────────────────────────────────

    async def _try_execute(
        self, opp: ArbitrageOpportunity, position: ArbitragePosition
    ) -> ExecutionResult:
        lid = opp.buy_listing.listing_id

        # 1. Verify listing still available
        available = await self._marketplace.functions.isAvailable(int(lid)).call()
        if not available:
            position.status = PositionStatus.FAILED
            return ExecutionResult(success=False, position=position,
                                   error="Listing no longer available")

        # 2. Approve USDC
        price_raw = int(opp.buy_price_usdc * 1e6)
        approve_data = self._usdc.encodeABI(
            fn_name="approve",
            args=[self.config.escrow_address, price_raw],
        )
        await self._send_wallet_tx(USDC_BASE, 0, approve_data,
                                   label=f"approve {opp.buy_price_usdc:.2f} USDC")

        # 3. Buy
        buy_data = self._marketplace.encodeABI(
            fn_name="buy",
            args=[int(lid), self.config.wallet_address],
        )
        buy_tx, _ = await self._send_wallet_tx(
            self.config.marketplace_address, 0, buy_data,
            label=f"buy listing {lid}",
        )
        position.buy_tx = buy_tx
        position.status = PositionStatus.RELISTING
        logger.info("Bought listing %s | tx=%s", lid, buy_tx)

        # 4. Immediately relist at profit price
        resell_price_raw = int(opp.resell_price_usdc * 1e6)
        create_data = self._marketplace.encodeABI(
            fn_name="createListing",
            args=[
                self.config.wallet_address,
                resell_price_raw,
                opp.buy_listing.category,
                opp.buy_listing.metadata_uri,
            ],
        )
        _, resell_id = await self._send_wallet_tx(
            self.config.marketplace_address, 0, create_data,
            label=f"createListing resell {opp.resell_price_usdc:.4f}",
        )
        position.resell_listing_id = str(resell_id)
        position.status            = PositionStatus.OPEN

        logger.info(
            "Relisted as listing %s @ %.4f USDC | expected net profit: %.4f USDC",
            resell_id, opp.resell_price_usdc, opp.net_profit_usdc,
        )

        # 5. Notify API
        await self._notify_api(position)
        return ExecutionResult(success=True, position=position)

    async def _cancel_listing(self, listing_id: str):
        try:
            data = self._marketplace.encodeABI(
                fn_name="cancelListing", args=[int(listing_id)]
            )
            await self._send_wallet_tx(
                self.config.marketplace_address, 0, data,
                label=f"cancelListing {listing_id}",
            )
        except Exception as exc:
            logger.warning("Cancel listing %s failed: %s", listing_id, exc)

    async def _notify_api(self, position: ArbitragePosition):
        payload = {
            "agent_id":        self.config.agent_id,
            "buy_listing_id":  position.buy_listing_id,
            "buy_tx":          position.buy_tx,
            "resell_listing_id": position.resell_listing_id,
            "buy_price_usdc":  position.buy_price_usdc,
            "resell_price_usdc": position.resell_price_usdc,
            "expected_profit": position.expected_net_profit,
        }
        try:
            async with self._session.post("/arbitrage/positions", json=payload) as resp:
                if resp.status not in (200, 201):
                    logger.warning("API position notify failed: %s", resp.status)
        except aiohttp.ClientError as exc:
            logger.warning("API notify error: %s", exc)

    async def _send_wallet_tx(
        self, target: str, value: int, data: bytes, label: str = ""
    ) -> tuple[str, int]:
        """Send tx via SmartWallet.execute(), wait for receipt, return (tx_hash, return_int)."""
        nonce     = await self._w3.eth.get_transaction_count(self._account.address)
        gas_price = await self._w3.eth.gas_price
        tx = await self._smart_wallet.functions.execute(
            target, value, data
        ).build_transaction({
            "from": self._account.address, "nonce": nonce,
            "gasPrice": gas_price, "chainId": self.config.chain_id,
        })
        tx["gas"] = int(await self._w3.eth.estimate_gas(tx) * 1.20)
        signed    = self._account.sign_transaction(tx)
        tx_hash   = await self._w3.eth.send_raw_transaction(signed.rawTransaction)
        tx_hex    = tx_hash.hex()
        logger.debug("Broadcast %s (%s)", tx_hex, label)

        deadline = asyncio.get_event_loop().time() + self.config.tx_timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            try:
                receipt = await self._w3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    if receipt["status"] == 0:
                        raise RuntimeError(f"Tx {tx_hex} reverted")
                    ret_int = int(receipt.get("logs", [{}])[0].get("data", "0x0"), 16) \
                        if receipt.get("logs") else 0
                    return tx_hex, ret_int
            except TransactionNotFound:
                pass
            await asyncio.sleep(2)
        raise TimeoutError(f"Tx {tx_hex} not confirmed in {self.config.tx_timeout_seconds}s")
