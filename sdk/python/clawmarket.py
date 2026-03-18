"""
clawmarketAI Python SDK
Interact with the marketplace, deploy agents, and manage smart wallets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from web3 import Web3
from web3.contract import Contract


MARKETPLACE_ABI = json.loads("""[
  {"name":"list","type":"function","inputs":[{"name":"category","type":"string"},{"name":"metadataURI","type":"string"},{"name":"price","type":"uint256"}],"outputs":[{"name":"","type":"uint256"}],"stateMutability":"nonpayable"},
  {"name":"purchase","type":"function","inputs":[{"name":"listingId","type":"uint256"}],"outputs":[],"stateMutability":"payable"},
  {"name":"listings","type":"function","inputs":[{"name":"","type":"uint256"}],"outputs":[{"name":"id","type":"uint256"},{"name":"seller","type":"address"},{"name":"category","type":"string"},{"name":"metadataURI","type":"string"},{"name":"price","type":"uint256"},{"name":"active","type":"bool"}],"stateMutability":"view"},
  {"name":"listingCount","type":"function","inputs":[],"outputs":[{"name":"","type":"uint256"}],"stateMutability":"view"}
]""")


@dataclass
class Listing:
    id: int
    seller: str
    category: str
    metadata_uri: str
    price: int
    active: bool


class ClawMarketSDK:
    """Python SDK for interacting with the clawmarketAI marketplace."""

    def __init__(self, rpc_url: str, marketplace_address: str):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.contract: Contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(marketplace_address),
            abi=MARKETPLACE_ABI,
        )

    def get_listing(self, listing_id: int) -> Listing:
        """Fetch a single listing by ID."""
        result = self.contract.functions.listings(listing_id).call()
        return Listing(
            id=result[0],
            seller=result[1],
            category=result[2],
            metadata_uri=result[3],
            price=result[4],
            active=result[5],
        )

    def get_listing_count(self) -> int:
        return self.contract.functions.listingCount().call()

    def get_all_listings(self) -> list[Listing]:
        count = self.get_listing_count()
        return [
            self.get_listing(i)
            for i in range(1, count + 1)
            if self.get_listing(i).active
        ]

    def get_listings_by_category(self, category: str) -> list[Listing]:
        return [l for l in self.get_all_listings() if l.category == category]

    def list_good(
        self,
        category: str,
        metadata_uri: str,
        price_wei: int,
        private_key: str,
    ) -> str:
        """List a new good on the marketplace. Returns transaction hash."""
        account = self.w3.eth.account.from_key(private_key)
        tx = self.contract.functions.list(category, metadata_uri, price_wei).build_transaction({
            "from": account.address,
            "nonce": self.w3.eth.get_transaction_count(account.address),
            "gas": 200_000,
            "gasPrice": self.w3.eth.gas_price,
        })
        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        return self.w3.to_hex(tx_hash)

    def purchase(self, listing_id: int, price_wei: int, private_key: str) -> str:
        """Purchase a listing. Returns transaction hash."""
        account = self.w3.eth.account.from_key(private_key)
        tx = self.contract.functions.purchase(listing_id).build_transaction({
            "from": account.address,
            "value": price_wei,
            "nonce": self.w3.eth.get_transaction_count(account.address),
            "gas": 150_000,
            "gasPrice": self.w3.eth.gas_price,
        })
        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        return self.w3.to_hex(tx_hash)
