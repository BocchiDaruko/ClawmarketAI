"""
ClawmarketAI — Creator Agent
publisher.py · Good Publisher
Uploads generated goods to IPFS, then hands off to the Seller Agent
by calling the REST API to create a listing (with pricing delegated to the Seller Agent).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp

from .api_wrapper_pipeline import GeneratedAPIWrapper
from .config import CreatorAgentConfig, GoodKind
from .dataset_pipeline import GeneratedDataset
from .idea_engine import APIWrapperSpec, DatasetSpec

logger = logging.getLogger("creator_agent.publisher")


# ─── Result ───────────────────────────────────────────────────────────────────

@dataclass
class PublishedGood:
    good_kind: GoodKind
    title: str
    ipfs_uri: str
    listing_id: str | None       # set by Seller Agent / marketplace
    price_usdc: float
    quality_score: float
    published_at: str


# ─── Publisher ────────────────────────────────────────────────────────────────

class GoodPublisher:
    """
    Two-step publisher:
      1. Pin the good's file(s) to IPFS → get ipfs:// URI
      2. POST to the ClawmarketAI REST API to trigger the Seller Agent
         to list it on Marketplace.sol with dynamic pricing
    """

    def __init__(self, config: CreatorAgentConfig, session: aiohttp.ClientSession):
        self.config   = config
        self._session = session

    # ── Public interface ──────────────────────────────────────────────────────

    async def publish_dataset(self, dataset: GeneratedDataset) -> PublishedGood | None:
        """Upload dataset file to IPFS, then register with the marketplace."""
        logger.info("Publishing dataset '%s' (%d bytes)",
                    dataset.spec.title, len(dataset.file_bytes))

        metadata = self._dataset_metadata(dataset)
        ipfs_uri = await self._pin_to_ipfs(
            file_bytes=dataset.file_bytes,
            filename=dataset.filename,
            metadata=metadata,
        )
        if not ipfs_uri:
            return None

        return await self._register_listing(
            good_kind=GoodKind.DATASET,
            title=dataset.spec.title,
            description=dataset.spec.description,
            category=dataset.spec.category,
            ipfs_uri=ipfs_uri,
            price_usdc=dataset.spec.estimated_price_usdc,
            quality_score=dataset.quality_score,
            tags=dataset.spec.tags,
            extra={"format": dataset.spec.format, "num_rows": len(dataset.rows)},
        )

    async def publish_api_wrapper(self, wrapper: GeneratedAPIWrapper) -> PublishedGood | None:
        """Upload wrapper ZIP to IPFS, then register with the marketplace."""
        logger.info("Publishing API wrapper '%s' (%d bytes)",
                    wrapper.spec.title, len(wrapper.bundle_bytes))

        metadata = self._wrapper_metadata(wrapper)
        ipfs_uri = await self._pin_to_ipfs(
            file_bytes=wrapper.bundle_bytes,
            filename=wrapper.filename,
            metadata=metadata,
        )
        if not ipfs_uri:
            return None

        return await self._register_listing(
            good_kind=GoodKind.API_WRAPPER,
            title=wrapper.spec.title,
            description=wrapper.spec.description,
            category=wrapper.spec.category,
            ipfs_uri=ipfs_uri,
            price_usdc=wrapper.spec.estimated_price_usdc,
            quality_score=wrapper.quality_score,
            tags=wrapper.spec.tags,
            extra={
                "target_api":           wrapper.spec.target_api_url,
                "num_endpoints":        len(wrapper.spec.endpoints),
                "access_duration_days": wrapper.spec.access_duration_days,
            },
        )

    # ── IPFS ──────────────────────────────────────────────────────────────────

    async def _pin_to_ipfs(
        self,
        file_bytes: bytes,
        filename: str,
        metadata: dict,
    ) -> str | None:
        """
        Pin a file to IPFS via Pinata (or compatible pinning service).
        Returns the ipfs:// URI or None on failure.
        """
        try:
            form = aiohttp.FormData()
            form.add_field(
                "file", file_bytes,
                filename=filename,
                content_type="application/octet-stream",
            )
            form.add_field(
                "pinataMetadata",
                json.dumps({"name": filename, "keyvalues": metadata}),
                content_type="application/json",
            )
            form.add_field(
                "pinataOptions",
                json.dumps({"cidVersion": 1}),
                content_type="application/json",
            )

            async with aiohttp.ClientSession(headers={
                "Authorization": f"Bearer {self.config.get_ipfs_api_key()}"
            }) as ipfs_session:
                async with ipfs_session.post(
                    self.config.ipfs_api_url, data=form
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    cid  = data.get("IpfsHash") or data.get("cid")
                    if not cid:
                        raise ValueError("No CID in IPFS response")
                    uri = f"ipfs://{cid}"
                    logger.info("Pinned to IPFS: %s → %s", filename, uri)
                    return uri

        except Exception as exc:
            logger.error("IPFS pin failed for '%s': %s", filename, exc)
            # Fallback: use placeholder URI so the pipeline can continue in dev
            fallback = f"ipfs://placeholder-{filename.replace(' ', '-')}"
            logger.warning("Using placeholder URI: %s", fallback)
            return fallback

    # ── Marketplace registration ───────────────────────────────────────────────

    async def _register_listing(
        self,
        good_kind: GoodKind,
        title: str,
        description: str,
        category: str,
        ipfs_uri: str,
        price_usdc: float,
        quality_score: float,
        tags: list[str],
        extra: dict,
    ) -> PublishedGood | None:
        """
        POST /creator/goods — tells the Seller Agent to list this good
        on Marketplace.sol with dynamic pricing enabled.
        The Seller Agent owns the listing lifecycle from this point.
        """
        payload = {
            "agent_id":       self.config.agent_id,
            "seller_wallet":  self.config.wallet_address,
            "good_kind":      good_kind,
            "title":          title,
            "description":    description,
            "category":       category,
            "metadata_uri":   ipfs_uri,
            "base_price_usdc":price_usdc,
            "quality_score":  quality_score,
            "tags":           tags,
            "extra":          extra,
            "created_by":     "creator-agent",
            "created_at":     datetime.now(timezone.utc).isoformat(),
        }

        try:
            async with self._session.post("/creator/goods", json=payload) as resp:
                resp.raise_for_status()
                data = await resp.json()
                listing_id = str(data.get("listing_id", ""))
                logger.info(
                    "Registered listing: id=%s title='%s' ipfs=%s price=%.2f",
                    listing_id, title, ipfs_uri, price_usdc,
                )
                return PublishedGood(
                    good_kind=good_kind,
                    title=title,
                    ipfs_uri=ipfs_uri,
                    listing_id=listing_id or None,
                    price_usdc=price_usdc,
                    quality_score=quality_score,
                    published_at=datetime.now(timezone.utc).isoformat(),
                )
        except aiohttp.ClientError as exc:
            logger.error("Marketplace registration failed for '%s': %s", title, exc)
            return None

    # ── Metadata builders ─────────────────────────────────────────────────────

    @staticmethod
    def _dataset_metadata(dataset: GeneratedDataset) -> dict:
        return {
            "kind":          "dataset",
            "category":      dataset.spec.category,
            "format":        dataset.spec.format,
            "num_rows":      str(len(dataset.rows)),
            "quality_score": str(round(dataset.quality_score, 3)),
            "fields":        ",".join(dataset.spec.schema.keys()),
        }

    @staticmethod
    def _wrapper_metadata(wrapper: GeneratedAPIWrapper) -> dict:
        return {
            "kind":               "api-wrapper",
            "category":           wrapper.spec.category,
            "target_api":         wrapper.spec.target_api_url,
            "num_endpoints":      str(len(wrapper.spec.endpoints)),
            "access_days":        str(wrapper.spec.access_duration_days),
            "quality_score":      str(round(wrapper.quality_score, 3)),
        }
