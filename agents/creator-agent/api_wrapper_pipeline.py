"""
ClawmarketAI — Creator Agent
api_wrapper_pipeline.py · API Wrapper Generation Pipeline
Validates the target API, packages the generated client code,
and prepares the delivery bundle (code + docs + credentials template).
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from dataclasses import dataclass

import aiohttp

from .config import CreatorAgentConfig
from .idea_engine import APIWrapperSpec

logger = logging.getLogger("creator_agent.api_wrapper_pipeline")


# ─── Result ───────────────────────────────────────────────────────────────────

@dataclass
class GeneratedAPIWrapper:
    spec: APIWrapperSpec
    quality_score: float
    quality_report: list[str]
    bundle_bytes: bytes       # ZIP: client.py + README.md + endpoints.json
    filename: str


# ─── Pipeline ─────────────────────────────────────────────────────────────────

class APIWrapperPipeline:
    """
    Validates the target public API, runs quality checks on the
    generated spec, and packages everything into a delivery ZIP bundle.
    """

    def __init__(self, config: CreatorAgentConfig, http_session: aiohttp.ClientSession):
        self.config   = config
        self._session = http_session

    # ── Public interface ──────────────────────────────────────────────────────

    async def generate(self, spec: APIWrapperSpec) -> GeneratedAPIWrapper | None:
        """Full pipeline: validate → quality check → package."""
        logger.info("Packaging API wrapper '%s' → %s",
                    spec.title, spec.target_api_url)

        # 1. Verify the target API is reachable
        reachable = await self._probe_api(spec.target_api_url)
        if not reachable:
            logger.warning("Target API unreachable: %s — skipping", spec.target_api_url)
            # Don't fail hard — API may be temporarily down; still package
            # but note it in the quality report

        # 2. Quality checks
        quality_score, quality_report = self._validate(spec, reachable)
        if quality_score < self.config.min_quality_score:
            logger.warning(
                "API wrapper '%s' failed quality gate: %.2f < %.2f",
                spec.title, quality_score, self.config.min_quality_score,
            )
            return None

        # 3. Package into ZIP bundle
        bundle_bytes, filename = self._package(spec)

        logger.info("API wrapper ready: '%s' — %d endpoints, score=%.2f, size=%d bytes",
                    spec.title, len(spec.endpoints), quality_score, len(bundle_bytes))

        return GeneratedAPIWrapper(
            spec=spec,
            quality_score=quality_score,
            quality_report=quality_report,
            bundle_bytes=bundle_bytes,
            filename=filename,
        )

    # ── Validation ────────────────────────────────────────────────────────────

    async def _probe_api(self, url: str) -> bool:
        """Quick HEAD/GET to verify the target API responds."""
        # Only probe allowlisted APIs
        if not any(url.startswith(allowed) for allowed in self.config.public_api_allowlist):
            logger.warning("API %s not in allowlist — skipping probe", url)
            return False
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                return resp.status < 500
        except Exception as exc:
            logger.debug("API probe failed for %s: %s", url, exc)
            return False

    def _validate(
        self, spec: APIWrapperSpec, api_reachable: bool
    ) -> tuple[float, list[str]]:
        checks: list[tuple[str, bool]] = []

        # 1. API reachability
        checks.append(("Target API reachable", api_reachable))

        # 2. Has endpoints
        has_eps = len(spec.endpoints) >= 1
        checks.append((f"Has endpoints: {len(spec.endpoints)}", has_eps))

        # 3. Endpoints have required fields
        ep_valid = all(
            "path" in ep and "method" in ep and "description" in ep
            for ep in spec.endpoints
        )
        checks.append(("All endpoints have path/method/description", ep_valid))

        # 4. Client code is non-empty and contains a class definition
        has_class = "class " in spec.client_code and "def " in spec.client_code
        checks.append(("Client code has class + methods", has_class))

        # 5. README is non-empty
        has_readme = len(spec.readme) > 100
        checks.append(("README has content", has_readme))

        # 6. API is in allowlist
        in_allowlist = any(
            spec.target_api_url.startswith(a)
            for a in self.config.public_api_allowlist
        )
        checks.append(("Target API in allowlist", in_allowlist))

        # 7. Access duration is sane
        duration_ok = 1 <= spec.access_duration_days <= 365
        checks.append((f"Access duration {spec.access_duration_days}d is sane", duration_ok))

        passed = sum(1 for _, ok in checks if ok)
        score  = passed / len(checks) if checks else 0.0
        report = [f"{'PASS' if ok else 'FAIL'}: {msg}" for msg, ok in checks]
        return score, report

    # ── Packaging ─────────────────────────────────────────────────────────────

    def _package(self, spec: APIWrapperSpec) -> tuple[bytes, str]:
        """
        Create a ZIP bundle containing:
          - client.py         : the Python client class
          - README.md         : full documentation
          - endpoints.json    : machine-readable endpoint list
          - delivery.json     : access configuration template
        """
        safe_title = spec.title.replace(" ", "_").replace("/", "-")[:50]
        filename   = f"{safe_title}.zip"

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Python client
            zf.writestr("client.py", spec.client_code)

            # README
            zf.writestr("README.md", spec.readme)

            # Endpoints manifest
            zf.writestr("endpoints.json", json.dumps(spec.endpoints, indent=2))

            # Delivery config template (filled at fulfillment time)
            delivery_template = {
                "product":              spec.title,
                "target_api":           spec.target_api_url,
                "rate_limit":           spec.rate_limit,
                "access_duration_days": spec.access_duration_days,
                "api_key":              "__GENERATED_AT_PURCHASE__",
                "expires_at":           "__SET_AT_DELIVERY__",
            }
            zf.writestr("delivery.json", json.dumps(delivery_template, indent=2))

        return buf.getvalue(), filename
