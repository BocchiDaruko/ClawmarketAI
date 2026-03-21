"""
ClawmarketAI — Creator Agent
agent.py · Main Creator Agent Orchestrator

Autonomous creation loop:
  1. Market Analyst finds the best opportunity (gap or top-seller clone)
  2. Idea Engine (Claude) generates a detailed spec
  3. Dataset or API Wrapper Pipeline produces the actual good
  4. Good Publisher pins to IPFS and registers with the Seller Agent
  5. Sleep and repeat
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from .analyst import MarketAnalyst
from .api_wrapper_pipeline import APIWrapperPipeline
from .config import CreatorAgentConfig, GoodKind
from .dataset_pipeline import DatasetPipeline
from .idea_engine import IdeaEngine
from .publisher import GoodPublisher, PublishedGood

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("creator_agent")


# ─── Session State ────────────────────────────────────────────────────────────

@dataclass
class CreatorState:
    agent_id: str
    goods_created: int = 0
    datasets_created: int = 0
    api_wrappers_created: int = 0
    failed_attempts: int = 0
    published: list[dict] = field(default_factory=list)
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def record(self, good: PublishedGood):
        self.goods_created += 1
        if good.good_kind == GoodKind.DATASET:
            self.datasets_created += 1
        else:
            self.api_wrappers_created += 1
        self.published.append({
            "title":         good.title,
            "kind":          good.good_kind,
            "listing_id":    good.listing_id,
            "ipfs_uri":      good.ipfs_uri,
            "price_usdc":    good.price_usdc,
            "quality_score": good.quality_score,
            "published_at":  good.published_at,
        })

    def summary(self) -> dict:
        return {
            "agent_id":          self.agent_id,
            "goods_created":     self.goods_created,
            "datasets":          self.datasets_created,
            "api_wrappers":      self.api_wrappers_created,
            "failed_attempts":   self.failed_attempts,
            "started_at":        self.started_at,
        }


# ─── Creator Agent ────────────────────────────────────────────────────────────

class CreatorAgent:
    """
    Autonomous Creator Agent for ClawmarketAI (Base Mainnet).
    Creates datasets and API wrappers using Claude, validates quality,
    pins to IPFS, and lists on the marketplace via Seller Agent handoff.
    """

    def __init__(self, config: CreatorAgentConfig):
        self.config   = config
        self._running = False
        self._state   = CreatorState(agent_id=config.agent_id)
        self._state_path = Path(f"./state/{config.agent_id}_state.json")
        self._state_path.parent.mkdir(parents=True, exist_ok=True)

        # Components (initialized on start)
        self._session:      aiohttp.ClientSession | None = None
        self._analyst:      MarketAnalyst | None         = None
        self._idea_engine:  IdeaEngine | None            = None
        self._dataset_pipe: DatasetPipeline | None       = None
        self._wrapper_pipe: APIWrapperPipeline | None    = None
        self._publisher:    GoodPublisher | None         = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        logger.info(
            "Starting CreatorAgent '%s' | strategy=%s | kinds=%s",
            self.config.agent_id,
            self.config.creation_strategy,
            self.config.good_kinds,
        )

        self._session = aiohttp.ClientSession(
            base_url=self.config.api_base_url,
            headers={
                "Authorization": f"Bearer {self.config.get_api_key()}",
                "Content-Type":  "application/json",
            },
        )

        self._analyst      = MarketAnalyst(self.config, self._session)
        self._idea_engine  = IdeaEngine(self.config, self._session)
        self._dataset_pipe = DatasetPipeline(self.config, self._session)
        self._wrapper_pipe = APIWrapperPipeline(self.config, self._session)
        self._publisher    = GoodPublisher(self.config, self._session)

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        self._running = True
        logger.info("CreatorAgent running. Cycle interval: %ds",
                    self.config.scan_interval_seconds)
        await self._run_loop()

    async def stop(self):
        logger.info("Shutting down CreatorAgent '%s'…", self.config.agent_id)
        self._running = False
        if self._session:
            await self._session.close()
        self._save_state()
        logger.info("Final summary:\n%s", json.dumps(self._state.summary(), indent=2))

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def _run_loop(self):
        tick = 0
        while self._running:
            try:
                await self._creation_cycle()
            except Exception as exc:
                logger.error("Unhandled error in creation cycle: %s", exc, exc_info=True)
                self._state.failed_attempts += 1

            tick += 1
            if tick % 5 == 0:
                logger.info("Summary: %s", json.dumps(self._state.summary()))

            await asyncio.sleep(self.config.scan_interval_seconds)

    async def _creation_cycle(self):
        """One full creation cycle: find → spec → build → publish."""
        logger.info("=== Creation cycle starting ===")

        # 1. Find opportunities
        opportunities = await self._analyst.find_opportunities(
            max_results=self.config.max_goods_per_cycle * 2
        )
        if not opportunities:
            logger.info("No opportunities found this cycle.")
            return

        created = 0
        for opportunity in opportunities:
            if created >= self.config.max_goods_per_cycle:
                break

            logger.info(
                "Processing opportunity: '%s' (kind=%s, source=%s)",
                opportunity.title, opportunity.good_kind, opportunity.source,
            )

            # 2. Generate spec via Claude
            spec = await self._idea_engine.generate_spec(opportunity)
            if not spec:
                logger.warning("Spec generation failed for '%s'", opportunity.title)
                self._state.failed_attempts += 1
                continue

            # 3. Build the good
            published = await self._build_and_publish(spec, opportunity.good_kind)
            if published:
                self._state.record(published)
                self._save_state()
                created += 1
                logger.info(
                    "Created good #%d: '%s' | listing=%s | price=%.2f USDC | score=%.2f",
                    self._state.goods_created,
                    published.title,
                    published.listing_id,
                    published.price_usdc,
                    published.quality_score,
                )
            else:
                self._state.failed_attempts += 1

        logger.info("=== Cycle complete: %d goods created ===", created)

    async def _build_and_publish(self, spec, good_kind: GoodKind) -> PublishedGood | None:
        """Route to the correct pipeline and publish."""
        if good_kind == GoodKind.DATASET:
            from .idea_engine import DatasetSpec
            if not isinstance(spec, DatasetSpec):
                return None
            result = await self._dataset_pipe.generate(spec)
            if not result:
                return None
            return await self._publisher.publish_dataset(result)

        else:  # API_WRAPPER
            from .idea_engine import APIWrapperSpec
            if not isinstance(spec, APIWrapperSpec):
                return None
            result = await self._wrapper_pipe.generate(spec)
            if not result:
                return None
            return await self._publisher.publish_api_wrapper(result)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_state(self):
        try:
            self._state_path.write_text(
                json.dumps(asdict(self._state), indent=2)
            )
        except Exception as exc:
            logger.warning("State save failed: %s", exc)


# ─── Entry point ──────────────────────────────────────────────────────────────

def run_from_config_file(config_path: str):
    data   = json.loads(Path(config_path).read_text())
    config = CreatorAgentConfig(**data)
    agent  = CreatorAgent(config)
    asyncio.run(agent.start())


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m agents.creator-agent.agent <config.json>")
        sys.exit(1)
    run_from_config_file(sys.argv[1])
