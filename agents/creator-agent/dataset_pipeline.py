"""
ClawmarketAI — Creator Agent
dataset_pipeline.py · Dataset Generation Pipeline
Generates synthetic datasets row-by-row using Claude,
validates quality, and packages them into the target format.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import random
from dataclasses import dataclass

import aiohttp

from .config import CreatorAgentConfig
from .idea_engine import DatasetSpec, IdeaEngine

logger = logging.getLogger("creator_agent.dataset_pipeline")

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"


# ─── Result ───────────────────────────────────────────────────────────────────

@dataclass
class GeneratedDataset:
    spec: DatasetSpec
    rows: list[dict]
    quality_score: float        # 0.0 – 1.0
    quality_report: list[str]   # per-criterion pass/fail
    file_bytes: bytes
    filename: str
    format: str


# ─── Pipeline ─────────────────────────────────────────────────────────────────

class DatasetPipeline:
    """
    Generates a synthetic dataset in three stages:
      1. Generate rows in batches via Claude API
      2. Validate against quality criteria
      3. Serialize to target format (jsonl / csv / parquet)
    """

    BATCH_SIZE = 25     # rows per Claude call (keeps prompts short)

    def __init__(self, config: CreatorAgentConfig, http_session: aiohttp.ClientSession):
        self.config   = config
        self._session = http_session

    # ── Public interface ──────────────────────────────────────────────────────

    async def generate(self, spec: DatasetSpec) -> GeneratedDataset | None:
        """Full pipeline: generate → validate → serialize."""
        logger.info("Generating dataset '%s' (%d rows, format=%s)",
                    spec.title, spec.num_rows, spec.format)

        rows = await self._generate_rows(spec)
        if not rows:
            logger.error("Row generation produced 0 rows for '%s'", spec.title)
            return None

        quality_score, quality_report = self._validate(rows, spec)
        if quality_score < self.config.min_quality_score:
            logger.warning(
                "Dataset '%s' failed quality gate: score=%.2f < %.2f",
                spec.title, quality_score, self.config.min_quality_score,
            )
            return None

        file_bytes, filename = self._serialize(rows, spec)
        logger.info("Dataset ready: '%s' — %d rows, score=%.2f, size=%d bytes",
                    spec.title, len(rows), quality_score, len(file_bytes))

        return GeneratedDataset(
            spec=spec,
            rows=rows,
            quality_score=quality_score,
            quality_report=quality_report,
            file_bytes=file_bytes,
            filename=filename,
            format=spec.format,
        )

    # ── Row generation ────────────────────────────────────────────────────────

    async def _generate_rows(self, spec: DatasetSpec) -> list[dict]:
        """Generate all rows in batches, deduplicating as we go."""
        all_rows: list[dict] = []
        seen_ids: set = set()
        batches = (spec.num_rows + self.BATCH_SIZE - 1) // self.BATCH_SIZE

        schema_desc = "\n".join(
            f'  - "{name}": ({info["type"]}) {info["description"]}'
            for name, info in spec.schema.items()
        )

        for batch_idx in range(batches):
            needed  = min(self.BATCH_SIZE, spec.num_rows - len(all_rows))
            batch   = await self._generate_batch(
                spec.generation_prompt, schema_desc, needed, batch_idx
            )
            # Deduplicate on first field (typically an ID)
            id_field = next(iter(spec.schema), None)
            for row in batch:
                if id_field:
                    row_id = row.get(id_field)
                    if row_id in seen_ids:
                        continue
                    seen_ids.add(row_id)
                all_rows.append(row)
                if len(all_rows) >= spec.num_rows:
                    break

            logger.debug("Batch %d/%d — total rows: %d", batch_idx + 1, batches, len(all_rows))

        return all_rows

    async def _generate_batch(
        self,
        generation_prompt: str,
        schema_desc: str,
        count: int,
        batch_idx: int,
    ) -> list[dict]:
        """Call Claude to generate one batch of rows."""
        prompt = f"""{generation_prompt}

Generate exactly {count} rows of synthetic data.
Schema:
{schema_desc}

Batch index: {batch_idx} (use this to vary the data — avoid repeating previous batches)

Return ONLY a JSON array of {count} objects matching the schema exactly.
No markdown, no explanation, no extra fields. Pure JSON array."""

        headers = {
            "x-api-key":         self.config.get_claude_api_key(),
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        }
        body = {
            "model":      self.config.claude_model,
            "max_tokens": 4096,
            "messages":   [{"role": "user", "content": prompt}],
        }

        for attempt in range(self.config.max_retries):
            try:
                async with self._session.post(
                    CLAUDE_API_URL, headers=headers, json=body
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    text = ""
                    for block in data.get("content", []):
                        if block.get("type") == "text":
                            text = block["text"].strip()
                            break
                    # Strip markdown fences if present
                    if text.startswith("```"):
                        lines = text.split("\n")
                        text  = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
                    rows = json.loads(text)
                    if isinstance(rows, list):
                        return rows
            except Exception as exc:
                logger.warning("Batch %d attempt %d failed: %s",
                               batch_idx, attempt + 1, exc)

        return []

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate(
        self, rows: list[dict], spec: DatasetSpec
    ) -> tuple[float, list[str]]:
        """
        Run automated quality checks.
        Returns (score 0-1, list of pass/fail strings).
        """
        checks: list[tuple[str, bool]] = []

        # 1. Row count
        expected = spec.num_rows
        actual   = len(rows)
        checks.append((
            f"Row count: {actual}/{expected} ({actual/expected*100:.0f}%)",
            actual >= expected * 0.80,   # pass if ≥80% of target
        ))

        # 2. Schema compliance — every row has all expected fields
        schema_fields = set(spec.schema.keys())
        compliant     = sum(1 for r in rows if schema_fields.issubset(r.keys()))
        pct           = compliant / len(rows) if rows else 0
        checks.append((
            f"Schema compliance: {compliant}/{len(rows)} rows ({pct*100:.0f}%)",
            pct >= 0.95,
        ))

        # 3. No empty rows
        non_empty = sum(1 for r in rows if any(v is not None and v != "" for v in r.values()))
        checks.append((
            f"Non-empty rows: {non_empty}/{len(rows)}",
            non_empty == len(rows),
        ))

        # 4. Numeric fields are numeric
        numeric_ok = True
        for field, info in spec.schema.items():
            if info.get("type") == "number":
                bad = [r for r in rows if field in r and not isinstance(r[field], (int, float))]
                if bad:
                    numeric_ok = False
                    break
        checks.append(("Numeric field types valid", numeric_ok))

        # 5. Uniqueness on first field
        first_field = next(iter(spec.schema), None)
        if first_field:
            ids    = [r.get(first_field) for r in rows if first_field in r]
            unique = len(set(str(i) for i in ids)) == len(ids)
            checks.append((f"Unique '{first_field}' values", unique))

        passed = sum(1 for _, ok in checks if ok)
        score  = passed / len(checks) if checks else 0.0
        report = [f"{'PASS' if ok else 'FAIL'}: {msg}" for msg, ok in checks]
        return score, report

    # ── Serialization ─────────────────────────────────────────────────────────

    def _serialize(self, rows: list[dict], spec: DatasetSpec) -> tuple[bytes, str]:
        """Serialize rows to the target format. Returns (bytes, filename)."""
        safe_title = spec.title.replace(" ", "_").replace("/", "-")[:50]

        if spec.format == "jsonl":
            content  = "\n".join(json.dumps(row) for row in rows)
            filename = f"{safe_title}.jsonl"
            return content.encode(), filename

        if spec.format == "csv":
            buf     = io.StringIO()
            fields  = list(spec.schema.keys())
            writer  = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            filename = f"{safe_title}.csv"
            return buf.getvalue().encode(), filename

        if spec.format == "parquet":
            try:
                import pandas as pd
                df       = pd.DataFrame(rows)
                buf      = io.BytesIO()
                df.to_parquet(buf, index=False)
                filename = f"{safe_title}.parquet"
                return buf.getvalue(), filename
            except ImportError:
                # Fallback to jsonl if pandas/pyarrow not installed
                logger.warning("pandas not available — falling back to jsonl")
                content  = "\n".join(json.dumps(row) for row in rows)
                filename = f"{safe_title}.jsonl"
                return content.encode(), filename

        raise ValueError(f"Unsupported format: {spec.format}")
