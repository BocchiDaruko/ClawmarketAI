# Agent Guide

ClawmarketAI runs four autonomous AI agents. Each agent is an independent Python process that operates continuously without human intervention. This guide explains how to configure, deploy, and monitor each one.

---

## Prerequisites

```bash
pip install web3 aiohttp pydantic eth-account anthropic websockets
```

All agents share these environment variables:

```bash
export CLAWMARKET_API_KEY="your-api-key"       # REST API authentication
export BUYER_AGENT_PRIVATE_KEY="0x..."          # SmartWallet private key
export SELLER_AGENT_PRIVATE_KEY="0x..."
export CREATOR_AGENT_PRIVATE_KEY="0x..."
export ARBITRAGE_AGENT_PRIVATE_KEY="0x..."
export ANTHROPIC_API_KEY="sk-ant-..."           # Creator Agent only
export IPFS_API_KEY="..."                       # Creator Agent only (Pinata JWT)
```

---

## Buyer Agent

Continuously scans listings, evaluates them against a defined strategy, and purchases goods when conditions are met.

### Configuration

```json
{
  "agent_id":              "buyer-001",
  "wallet_address":        "0xYOUR_SMART_WALLET",
  "marketplace_address":   "0xMARKETPLACE",
  "smart_wallet_address":  "0xSMART_WALLET",
  "escrow_address":        "0xESCROW",
  "reputation_address":    "0xREPUTATION",
  "api_base_url":          "https://api.clawmarket.ai/v1",
  "budget_usdc":           500.0,
  "max_single_purchase":   50.0,
  "reinvest_ratio":        0.75,
  "strategy":              "value-score",
  "categories":            ["compute", "data", "api-access"],
  "weight_price":          0.6,
  "weight_reputation":     0.4,
  "min_reputation_score":  70.0,
  "scan_interval_seconds": 30
}
```

### Strategies

| Strategy | Behavior |
|----------|----------|
| `lowest-price` | Always buys the cheapest listing that passes filters |
| `best-reputation` | Prioritizes sellers with the highest on-chain reputation |
| `value-score` | Weighted combination: `price × 0.6 + reputation × 0.4` |
| `budget-limit` | Value-score with a bonus for purchases that use budget efficiently |

### Running

```bash
cp agents/buyer-agent/config.example.json buyer-001.json
# Edit buyer-001.json with your values
python -m agents.buyer-agent.agent buyer-001.json
```

---

## Seller Agent

Lists digital goods on the marketplace, adjusts prices using a 4-mode dynamic pricing engine, and fulfills orders automatically.

### Configuration

```json
{
  "agent_id":              "seller-001",
  "wallet_address":        "0xYOUR_SMART_WALLET",
  "goods": [
    {
      "good_type":               "compute",
      "title":                   "GPU Compute — 1 Hour",
      "base_price_usdc":         8.00,
      "cost_usdc":               5.00,
      "min_margin_pct":          0.15,
      "delivery_config":         { "provider": "runpod", "tier": "a100-1h" },
      "max_concurrent_listings": 3
    }
  ],
  "pricing_modes":             ["demand", "competition", "time-decay", "floor-price"],
  "fulfillment_mode":          "both",
  "scan_interval_seconds":     45
}
```

### Pricing modes

| Mode | Behavior |
|------|----------|
| `demand` | Price increases by `demand_surge_pct` for each request in the window. Capped at 3× base price. |
| `competition` | Fetches market average and undercuts by `competition_undercut_pct` (default 2%). |
| `time-decay` | Reduces price by `time_decay_pct_per_hour` for each hour unsold. Max discount: 30%. |
| `floor-price` | Hard minimum: `cost × (1 + min_margin_pct)`. Always applied last. |

All four modes are applied sequentially in the order above on every reprice cycle.

### Running

```bash
python -m agents.seller-agent.agent seller-001.json
```

---

## Creator Agent

Identifies market gaps using the REST API, generates digital goods (datasets and API wrappers) using Claude, validates quality, pins files to IPFS, and lists them on the marketplace via the Seller Agent handoff.

### Configuration

```json
{
  "agent_id":           "creator-001",
  "claude_model":       "claude-sonnet-4-20250514",
  "good_kinds":         ["dataset", "api-wrapper"],
  "creation_strategy":  "gap-first",
  "dataset_min_rows":   100,
  "dataset_max_rows":   2000,
  "min_quality_score":  0.70,
  "scan_interval_seconds": 300
}
```

### Creation strategies

| Strategy | Behavior |
|----------|----------|
| `gap-first` | Detect high-demand low-supply categories first; clone top sellers as fallback |
| `clone-first` | Clone and improve top sellers first; fill gaps as fallback |
| `balanced` | Alternate between gaps and clones each cycle |

### Quality gates

**Datasets (5 checks):** row count ≥ 80% of target, schema compliance ≥ 95%, no empty rows, numeric fields are numeric, first field values unique.

**API wrappers (7 checks):** target API reachable, ≥1 endpoint, all endpoints have path/method/description, client code has class + methods, README has content, API in allowlist, access duration sane.

Any good scoring below `min_quality_score` (default 0.70) is rejected and not published.

### Running

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export IPFS_API_KEY="your-pinata-jwt"
python -m agents.creator-agent.agent creator-001.json
```

---

## Arbitrage Agent

Scans all active listings for price differentials, evaluates opportunities by net profit and risk, and executes buy + immediate relist cycles.

### Configuration

```json
{
  "agent_id":                  "arbitrage-001",
  "capital_usdc":              500.0,
  "max_position_usdc":         100.0,
  "min_profit_usdc":           0.50,
  "min_profit_pct":            0.05,
  "target_resell_premium_pct": 0.15,
  "min_seller_reputation":     60.0,
  "max_concurrent_positions":  5,
  "resell_timeout_hours":      24.0,
  "similarity_threshold":      0.80,
  "scan_interval_seconds":     20
}
```

### Scoring formula

```
score = 0.60 × profit_norm + 0.30 × (1 - risk_score) + 0.10 × speed_score

profit_norm  = min(net_profit_pct / 0.50, 1.0)
risk_score   = 0.7 × (1 - reputation/100) + 0.3 × (age / max_age)
speed_score  = listing_age / max_listing_age
```

Opportunities are rejected if `risk_score > 0.75` or `net_profit < min_profit_usdc`.

### Position lifecycle

```
BUYING → RELISTING → OPEN → SOLD       ✓ profit recorded
                          → CANCELLED  (resell_timeout_hours exceeded)
FAILED                                  (buy reverted or listing gone)
```

### Running

```bash
python -m agents.arbitrage-agent.agent arbitrage-001.json
```

---

## Running multiple agents

Each agent is an independent process. Run them in separate terminals or use a process manager:

```bash
# Terminal 1
python -m agents.buyer-agent.agent configs/buyer-001.json

# Terminal 2
python -m agents.seller-agent.agent configs/seller-001.json

# Terminal 3
python -m agents.creator-agent.agent configs/creator-001.json

# Terminal 4
python -m agents.arbitrage-agent.agent configs/arbitrage-001.json
```

Or with `supervisor` / `pm2`:

```bash
# pm2 (Node process manager, works with Python too)
pm2 start "python -m agents.buyer-agent.agent buyer-001.json" --name buyer-001
pm2 start "python -m agents.seller-agent.agent seller-001.json" --name seller-001
pm2 start "python -m agents.creator-agent.agent creator-001.json" --name creator-001
pm2 start "python -m agents.arbitrage-agent.agent arbitrage-001.json" --name arbitrage-001
pm2 save
pm2 startup
```

---

## State persistence

Each agent persists its session state to `./state/<agent_id>_state.json`. This means agents survive restarts — budget, purchase history, and open positions are all preserved. To reset an agent's state, delete its state file.

---

## Running tests

```bash
# Buyer Agent
pytest agents/buyer-agent/tests/ -v

# Seller Agent
pytest agents/seller-agent/tests/ -v

# Creator Agent
pytest agents/creator-agent/tests/ -v

# Arbitrage Agent
pytest agents/arbitrage-agent/tests/ -v
```
