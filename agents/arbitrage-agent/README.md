# 📊 Arbitrage Agent — ClawmarketAI

Autonomous arbitrage agent that continuously scans the marketplace for price differentials, evaluates opportunities by net profit and risk, and executes buy + relist cycles atomically — without human intervention.

Operates on **Base** (mainnet, chain ID 8453).

---

## How it works

```
Every 20 seconds:
  1. Scan all active listings
     ├── Same-good clustering  — group identical goods sold at different prices
     └── Cross-category scan   — find listings priced ≥20% below category avg
  2. Evaluate opportunities
     ├── Profit filter  — net profit > min_profit_usdc AND > min_profit_pct
     ├── Risk filter    — seller reputation + listing age within bounds
     └── Speed filter   — flag expiring listings as higher priority
  3. Execute best opportunity (if score > 0)
     ├── Buy via SmartWallet → Escrow
     └── Immediately relist at target resell price
  4. Monitor open positions
     ├── Sold → record profit
     └── Timeout → cancel resell listing
```

---

## Architecture

```
ArbitrageAgent (agent.py)
│
├── PriceScanner (scanner.py)
│   ├── GET /listings              — full market snapshot
│   ├── Same-good clustering       — SequenceMatcher title similarity
│   └── Cross-category subvalued   — listings ≥20% below category avg
│
├── OpportunityEvaluator (evaluator.py)
│   ├── Profit filter              — net > min after fees + gas
│   ├── Risk score                 — 0.7 × rep_risk + 0.3 × age_risk
│   ├── Speed score                — age / max_age (urgency proxy)
│   └── Final score                — 0.6×profit + 0.3×(1-risk) + 0.1×speed
│
└── FlashExecutor (executor.py)
    ├── isAvailable check          — verify listing not sniped
    ├── USDC approve → buy()       — SmartWallet → Escrow
    ├── createListing()            — immediate relist at profit price
    ├── Position monitor           — poll sold status, cancel on timeout
    └── POST /arbitrage/positions  — notify REST API
```

---

## Profit calculation

```
gross_profit  = resell_price - buy_price
fee_cost      = buy_price × marketplace_fee_pct × 2   (buy + resell)
gas_cost      = estimated_gas_usdc × 2
net_profit    = gross_profit - fee_cost - gas_cost
```

An opportunity is only executed when:
- `net_profit ≥ min_profit_usdc` (default: 0.50 USDC)
- `net_profit / buy_price ≥ min_profit_pct` (default: 5%)

---

## Risk model

```
rep_risk   = 1 - (seller_reputation / 100)
age_risk   = listing_age_hours / max_listing_age_hours
risk_score = 0.7 × rep_risk + 0.3 × age_risk
```

Opportunities with `risk_score > 0.75` are automatically rejected.

---

## Position lifecycle

```
BUYING → RELISTING → OPEN → SOLD      ✓ profit recorded
                          → CANCELLED  (resell_timeout_hours exceeded)
         FAILED                        (buy reverted or unavailable)
```

---

## Quick start

```bash
pip install web3 aiohttp pydantic eth-account

cp config.example.json arbitrage-001.json

export ARBITRAGE_AGENT_PRIVATE_KEY="0x..."
export CLAWMARKET_API_KEY="..."

python -m agents.arbitrage-agent.agent arbitrage-001.json
```

---

## Key config parameters

| Field | Default | Description |
|-------|---------|-------------|
| `capital_usdc` | — | Total USDC for arbitrage |
| `max_position_usdc` | — | Max USDC per position |
| `reserve_pct` | 0.10 | Keep 10% as reserve |
| `min_profit_usdc` | 0.50 | Min net profit per trade |
| `min_profit_pct` | 0.05 | Min profit as % of buy price |
| `target_resell_premium_pct` | 0.15 | Relist at avg × 1.15 |
| `min_seller_reputation` | 60.0 | Skip low-rep sellers |
| `max_concurrent_positions` | 5 | Cap open positions |
| `resell_timeout_hours` | 24.0 | Cancel unsold after 24h |
| `similarity_threshold` | 0.80 | Title match % for clustering |
| `scan_interval_seconds` | 20 | Scan every 20s |

---

## Running tests

```bash
pytest agents/arbitrage-agent/tests/ -v
```

---

## Files

| File | Purpose |
|------|---------|
| `agent.py` | Main orchestrator, loop, stats |
| `config.py` | Pydantic config + validators |
| `scanner.py` | Market scan, clustering, subvalued detection |
| `evaluator.py` | Profit/risk/speed scoring, opportunity ranking |
| `executor.py` | Buy + relist execution, position monitoring |
| `tests/test_evaluator.py` | Unit tests for evaluator |
