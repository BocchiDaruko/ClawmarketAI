"""
ClawmarketAI — Creator Agent
tests/test_dataset_pipeline.py · Unit tests for DatasetPipeline
"""

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from agents.creator_agent.config import CreatorAgentConfig, GoodKind
from agents.creator_agent.idea_engine import DatasetSpec
from agents.creator_agent.dataset_pipeline import DatasetPipeline, GeneratedDataset


# ─── Fixtures ─────────────────────────────────────────────────────────────────

BASE_CONFIG = dict(
    agent_id="test-creator",
    wallet_address="0xABC",
    marketplace_address="0x001",
    smart_wallet_address="0x002",
    escrow_address="0x003",
    api_base_url="http://localhost:8000",
    dataset_min_rows=10,
    dataset_max_rows=100,
    min_quality_score=0.60,
)

SAMPLE_SCHEMA = {
    "id":     {"type": "number",  "description": "unique row ID"},
    "name":   {"type": "string",  "description": "item name"},
    "price":  {"type": "number",  "description": "price in USD"},
    "active": {"type": "boolean", "description": "is active"},
}


def make_spec(num_rows=50, fmt="jsonl") -> DatasetSpec:
    return DatasetSpec(
        title="Test Dataset",
        description="A test dataset",
        category="test",
        format=fmt,
        schema=SAMPLE_SCHEMA,
        generation_prompt="Generate test rows",
        num_rows=num_rows,
        quality_criteria=["no duplicate IDs", "price > 0"],
        estimated_price_usdc=5.0,
        tags=["test"],
    )


def make_rows(n=50) -> list[dict]:
    return [
        {"id": i, "name": f"item-{i}", "price": float(i + 1), "active": True}
        for i in range(n)
    ]


def make_pipeline() -> DatasetPipeline:
    from agents.creator_agent.config import CreatorAgentConfig
    config  = CreatorAgentConfig(**BASE_CONFIG)
    session = AsyncMock()
    return DatasetPipeline(config, session)


# ─── Validation tests ─────────────────────────────────────────────────────────

class TestValidation:
    def test_perfect_rows_score_high(self):
        pipe  = make_pipeline()
        spec  = make_spec(num_rows=50)
        rows  = make_rows(50)
        score, report = pipe._validate(rows, spec)
        assert score >= 0.80
        assert any("PASS" in r for r in report)

    def test_empty_rows_score_low(self):
        pipe  = make_pipeline()
        spec  = make_spec(num_rows=50)
        score, report = pipe._validate([], spec)
        assert score < 0.50

    def test_missing_fields_lowers_score(self):
        pipe  = make_pipeline()
        spec  = make_spec(num_rows=10)
        # Rows missing the 'price' field
        rows  = [{"id": i, "name": f"x-{i}", "active": True} for i in range(10)]
        score, report = pipe._validate(rows, spec)
        schema_check  = next((r for r in report if "Schema" in r), "")
        assert "FAIL" in schema_check

    def test_duplicate_ids_detected(self):
        pipe = make_pipeline()
        spec = make_spec(num_rows=10)
        # All rows have the same id
        rows = [{"id": 1, "name": f"item-{i}", "price": float(i), "active": True}
                for i in range(10)]
        score, report = pipe._validate(rows, spec)
        unique_check  = next((r for r in report if "Unique" in r), "")
        assert "FAIL" in unique_check

    def test_non_numeric_price_fails(self):
        pipe = make_pipeline()
        spec = make_spec(num_rows=5)
        rows = [{"id": i, "name": f"item-{i}", "price": "not-a-number", "active": True}
                for i in range(5)]
        score, report = pipe._validate(rows, spec)
        numeric_check = next((r for r in report if "Numeric" in r), "")
        assert "FAIL" in numeric_check


# ─── Serialization tests ──────────────────────────────────────────────────────

class TestSerialization:
    def test_jsonl_serialization(self):
        pipe     = make_pipeline()
        spec     = make_spec(fmt="jsonl")
        rows     = make_rows(5)
        b, fname = pipe._serialize(rows, spec)
        assert fname.endswith(".jsonl")
        lines    = b.decode().strip().split("\n")
        assert len(lines) == 5
        import json
        assert json.loads(lines[0])["id"] == 0

    def test_csv_serialization(self):
        pipe     = make_pipeline()
        spec     = make_spec(fmt="csv")
        rows     = make_rows(5)
        b, fname = pipe._serialize(rows, spec)
        assert fname.endswith(".csv")
        content  = b.decode()
        assert "id,name,price,active" in content or "id" in content

    def test_unknown_format_raises(self):
        pipe = make_pipeline()
        spec = make_spec(fmt="xlsx")  # not supported
        with pytest.raises(ValueError):
            pipe._serialize(make_rows(5), spec)


# ─── Quality gate tests ───────────────────────────────────────────────────────

class TestQualityGate:
    def test_good_dataset_passes_gate(self):
        pipe = make_pipeline()
        spec = make_spec(num_rows=50)
        rows = make_rows(50)
        score, _ = pipe._validate(rows, spec)
        assert score >= pipe.config.min_quality_score

    def test_bad_dataset_fails_gate(self):
        pipe = make_pipeline()
        spec = make_spec(num_rows=50)
        # 0 rows → should fail
        score, _ = pipe._validate([], spec)
        assert score < pipe.config.min_quality_score
