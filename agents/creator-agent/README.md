# 🎨 Creator Agent — ClawmarketAI

Autonomous creator agent that identifies market gaps, generates digital goods using Claude, validates quality, pins to IPFS, and lists them on the marketplace — entirely without human intervention.

**Produces:** synthetic datasets + API wrappers  
**Powered by:** Claude API (idea generation + data synthesis)  
**Network:** Base Mainnet

---

## How it works

```
Every 5 minutes:
  1. Market Analyst → find best opportunity (gap or top-seller)
  2. Idea Engine (Claude) → generate detailed spec
  3. Dataset Pipeline or API Wrapper Pipeline → build the good
  4. Quality Gate → reject if score < min_quality_score
  5. IPFS → pin the file, get ipfs:// URI
  6. Seller Agent handoff → POST /creator/goods (listing + pricing delegated)
```

---

## Architecture

```
CreatorAgent (agent.py)
│
├── MarketAnalyst (analyst.py)
│   ├── GET /market/gaps          — demand without supply
│   └── GET /market/top-sellers   — clone best performers
│
├── IdeaEngine (idea_engine.py)   ← Claude API
│   ├── DatasetSpec generation    — schema, prompt, quality criteria
│   └── APIWrapperSpec generation — endpoints, client code, docs
│
├── DatasetPipeline (dataset_pipeline.py)
│   ├── Batch row generation via Claude
│   ├── Quality validation (5 automated checks)
│   └── Serialization: jsonl / csv / parquet
│
├── APIWrapperPipeline (api_wrapper_pipeline.py)
│   ├── Target API probe (reachability check)
│   ├── Quality validation (7 automated checks)
│   └── ZIP packaging: client.py + README.md + endpoints.json
│
└── GoodPublisher (publisher.py)
    ├── IPFS pin (Pinata)          → ipfs:// URI
    └── POST /creator/goods        → Seller Agent listing handoff
```

---

## Creation strategies

| Strategy | Behavior |
|----------|----------|
| `gap-first` | Detect high-demand low-supply categories first, clone top sellers as fallback |
| `clone-first` | Clone and improve top sellers first, fill gaps as fallback |
| `balanced` | Alternate between gaps and clones each cycle |

---

## Quality gates

### Datasets (5 checks)
- Row count ≥ 80% of target
- Schema compliance ≥ 95% of rows
- No empty rows
- Numeric fields are actually numeric
- First field values are unique (deduplication)

### API Wrappers (7 checks)
- Target API is reachable
- Has at least 1 endpoint
- All endpoints have path / method / description
- Client code has a class + methods
- README has content (> 100 chars)
- Target API is in the allowlist
- Access duration is sane (1–365 days)

Any good scoring below `min_quality_score` (default 0.70) is rejected and not published.

---

## Quick start

```bash
# 1. Install
pip install web3 aiohttp pydantic anthropic

# 2. Configure
cp config.example.json creator-001.json

# 3. Set env vars
export CREATOR_AGENT_PRIVATE_KEY="0x..."
export CLAWMARKET_API_KEY="..."
export ANTHROPIC_API_KEY="sk-ant-..."
export IPFS_API_KEY="..."   # Pinata JWT

# 4. Run
python -m agents.creator-agent.agent creator-001.json
```

---

## Files

| File | Purpose |
|------|---------|
| `agent.py` | Main orchestrator and entry point |
| `config.py` | Pydantic config schema |
| `analyst.py` | Market gap detection + top-seller analysis |
| `idea_engine.py` | Claude API — spec generation |
| `dataset_pipeline.py` | Synthetic dataset generation + validation |
| `api_wrapper_pipeline.py` | API wrapper packaging + validation |
| `publisher.py` | IPFS pinning + Seller Agent handoff |
| `tests/test_dataset_pipeline.py` | Unit tests |

---

## Running tests

```bash
pytest agents/creator-agent/tests/ -v
```
