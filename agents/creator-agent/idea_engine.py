"""
ClawmarketAI — Creator Agent
idea_engine.py · Idea Engine (Claude API)
Uses Claude to turn a market opportunity into a detailed good specification:
  - Dataset: schema, sample rows, generation prompt, quality criteria
  - API wrapper: target API, endpoints to expose, client code, docs
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import aiohttp

from .analyst import CreationOpportunity
from .config import CreatorAgentConfig, GoodKind

logger = logging.getLogger("creator_agent.idea_engine")


# ─── Specs ────────────────────────────────────────────────────────────────────

@dataclass
class DatasetSpec:
    title: str
    description: str
    category: str
    format: str                         # jsonl | csv | parquet
    schema: dict                        # field_name → {type, description}
    generation_prompt: str              # prompt to use for row generation
    num_rows: int
    quality_criteria: list[str]
    estimated_price_usdc: float
    tags: list[str] = field(default_factory=list)


@dataclass
class APIWrapperSpec:
    title: str
    description: str
    category: str
    target_api_url: str
    endpoints: list[dict]               # [{path, method, description, params}]
    client_code: str                    # Python client code (generated)
    readme: str                         # markdown docs
    rate_limit: str                     # e.g. "100 req/min"
    access_duration_days: int
    estimated_price_usdc: float
    tags: list[str] = field(default_factory=list)


# ─── Idea Engine ──────────────────────────────────────────────────────────────

class IdeaEngine:
    """
    Calls Claude to generate detailed, actionable specs from a market opportunity.
    Returns a DatasetSpec or APIWrapperSpec ready for the production pipeline.
    """

    CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, config: CreatorAgentConfig, http_session: aiohttp.ClientSession):
        self.config   = config
        self._session = http_session

    # ── Public interface ──────────────────────────────────────────────────────

    async def generate_spec(
        self, opportunity: CreationOpportunity
    ) -> DatasetSpec | APIWrapperSpec | None:
        """Generate a production spec for the given opportunity."""
        try:
            if opportunity.good_kind == GoodKind.DATASET:
                return await self._dataset_spec(opportunity)
            else:
                return await self._api_wrapper_spec(opportunity)
        except Exception as exc:
            logger.error("Spec generation failed for '%s': %s",
                         opportunity.title, exc)
            return None

    # ── Dataset spec ──────────────────────────────────────────────────────────

    async def _dataset_spec(self, op: CreationOpportunity) -> DatasetSpec:
        """Ask Claude to design a complete dataset spec."""
        num_rows = min(
            max(self.config.dataset_min_rows, 500),
            self.config.dataset_max_rows,
        )
        fmt = self.config.dataset_formats[0]   # default to first format

        prompt = f"""You are an autonomous AI agent designing a synthetic dataset to sell on a digital marketplace.

Opportunity:
- Title: {op.title}
- Category: {op.category}
- Description: {op.description}
- Rationale: {op.rationale}
- Target rows: {num_rows}
- Format: {fmt}

Return ONLY a valid JSON object with this exact structure (no markdown, no explanation):
{{
  "title": "string — final product title",
  "description": "string — 2-3 sentence product description for buyers",
  "schema": {{
    "field_name": {{"type": "string|number|boolean|array", "description": "what this field contains"}}
  }},
  "generation_prompt": "string — detailed prompt to use when generating each row of synthetic data",
  "quality_criteria": ["criterion 1", "criterion 2", "criterion 3"],
  "tags": ["tag1", "tag2", "tag3"]
}}

Requirements:
- Schema must have 5-12 fields
- generation_prompt must be specific and detailed (will be used to generate {num_rows} rows)
- quality_criteria must be measurable (e.g. "no duplicate IDs", "price > 0")
- tags should be relevant search terms buyers would use"""

        raw = await self._call_claude(prompt)
        data = self._parse_json(raw)

        return DatasetSpec(
            title=data.get("title", op.title),
            description=data.get("description", op.description),
            category=op.category,
            format=fmt,
            schema=data.get("schema", {}),
            generation_prompt=data.get("generation_prompt", ""),
            num_rows=num_rows,
            quality_criteria=data.get("quality_criteria", []),
            estimated_price_usdc=op.estimated_price_usdc or self.config.dataset_base_price_usdc,
            tags=data.get("tags", []),
        )

    # ── API wrapper spec ──────────────────────────────────────────────────────

    async def _api_wrapper_spec(self, op: CreationOpportunity) -> APIWrapperSpec:
        """Ask Claude to design a complete API wrapper spec + generate client code."""
        # Pick a suitable public API from the allowlist
        target_api = self._pick_api_for_category(op.category)

        prompt = f"""You are an autonomous AI agent designing an API wrapper product to sell on a digital marketplace.

Opportunity:
- Title: {op.title}
- Category: {op.category}
- Target public API: {target_api}
- Description: {op.description}

Return ONLY a valid JSON object with this exact structure (no markdown, no explanation):
{{
  "title": "string — final product title",
  "description": "string — 2-3 sentence description for buyers",
  "endpoints": [
    {{
      "path": "/resource",
      "method": "GET",
      "description": "what this endpoint returns",
      "params": {{"param_name": "description"}}
    }}
  ],
  "rate_limit": "string — e.g. '100 req/min'",
  "access_duration_days": 7,
  "tags": ["tag1", "tag2"]
}}

Requirements:
- Expose 3-6 useful endpoints from {target_api}
- Each endpoint must add value (filtering, formatting, enrichment) beyond raw passthrough
- rate_limit should be realistic and sustainable"""

        raw  = await self._call_claude(prompt)
        data = self._parse_json(raw)

        # Generate client code in a second Claude call
        client_code = await self._generate_client_code(
            target_api, data.get("endpoints", []), op.title
        )
        readme = self._build_readme(data, target_api, client_code)

        return APIWrapperSpec(
            title=data.get("title", op.title),
            description=data.get("description", op.description),
            category=op.category,
            target_api_url=target_api,
            endpoints=data.get("endpoints", []),
            client_code=client_code,
            readme=readme,
            rate_limit=data.get("rate_limit", "60 req/min"),
            access_duration_days=int(data.get("access_duration_days", 7)),
            estimated_price_usdc=op.estimated_price_usdc or self.config.api_wrapper_base_price_usdc,
            tags=data.get("tags", []),
        )

    async def _generate_client_code(
        self, api_url: str, endpoints: list[dict], title: str
    ) -> str:
        """Generate a clean Python client for the wrapper."""
        endpoints_desc = "\n".join(
            f"  - {ep['method']} {ep['path']}: {ep['description']}"
            for ep in endpoints
        )
        prompt = f"""Write a clean, production-ready Python client class for this API wrapper product.

Product: {title}
Base URL: {api_url}
Endpoints:
{endpoints_desc}

Requirements:
- Class named `ClawClient`
- __init__ accepts api_key: str
- One method per endpoint with type hints and docstring
- Uses httpx or requests (prefer requests)
- Returns parsed JSON as dict or list
- Raises ValueError on API errors with clear message
- No external dependencies beyond requests

Return ONLY the Python code, no markdown fences, no explanation."""

        return await self._call_claude(prompt)

    # ── Claude API call ───────────────────────────────────────────────────────

    async def _call_claude(self, prompt: str) -> str:
        """Single-turn Claude API call. Returns the text response."""
        headers = {
            "x-api-key":         self.config.get_claude_api_key(),
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        }
        body = {
            "model":      self.config.claude_model,
            "max_tokens": 2048,
            "messages":   [{"role": "user", "content": prompt}],
        }
        async with self._session.post(
            self.CLAUDE_API_URL,
            headers=headers,
            json=body,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            # Extract text from content blocks
            for block in data.get("content", []):
                if block.get("type") == "text":
                    return block["text"].strip()
        raise ValueError("Claude returned no text content")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Parse JSON from Claude response, stripping any accidental markdown."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines   = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error: %s\nRaw: %s", exc, raw[:300])
            return {}

    def _pick_api_for_category(self, category: str) -> str:
        """Map a category to a suitable public API from the allowlist."""
        mapping = {
            "crypto":      "https://api.coinpaprika.com",
            "crypto-prices": "https://api.coinpaprika.com",
            "fx-rates":    "https://api.frankfurter.app",
            "weather":     "https://api.open-meteo.com",
            "weather-history": "https://api.open-meteo.com",
            "country":     "https://restcountries.eu",
            "country-data": "https://restcountries.eu",
        }
        for key, url in mapping.items():
            if key in category.lower():
                return url
        # Default: first allowlisted API
        return self.config.public_api_allowlist[0]

    @staticmethod
    def _build_readme(spec: dict, api_url: str, client_code: str) -> str:
        endpoints_md = "\n".join(
            f"### `{ep['method']} {ep['path']}`\n{ep['description']}\n"
            for ep in spec.get("endpoints", [])
        )
        return f"""# {spec.get('title', 'API Wrapper')}

{spec.get('description', '')}

**Source API:** {api_url}
**Rate limit:** {spec.get('rate_limit', '60 req/min')}
**Access:** {spec.get('access_duration_days', 7)} days

## Endpoints

{endpoints_md}

## Python Client

```python
{client_code}
```

## Quickstart

```python
client = ClawClient(api_key="YOUR_KEY")
result = client.get_data()
print(result)
```

---
*Generated autonomously by ClawmarketAI Creator Agent*
"""
