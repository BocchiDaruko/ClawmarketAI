# 🛍️ Buyer Agent — ClawmarketAI

Autonomous buyer agent that continuously scans the ClawmarketAI marketplace, evaluates listings against a defined strategy, and purchases goods when conditions are met — without human intervention.

Operates on **Base** (mainnet, chain ID 8453) via dual-source market data: **REST API** for fast discovery + **on-chain events** for finality verification.

---

## Architecture

```
BuyerAgent (agent.py)
│
├── MarketScanner (scanner.py)
│   ├── REST API polling  →  GET /listings
│   └── Base on-chain     →  ListingCreated events
│
├── StrategyEngine (strategy.py)
│   ├── lowest-price       — cheapest absolute price
│   ├── best-reputation    — highest on-chain reputation score
│   ├── value-score        — weighted (price × reputation)
│   └── budget-limit       — value-score + budget utilization bonus
│
├── TransactionExecutor (executor.py)
│   ├── USDC balance check
│   ├── SmartWallet.execute() → USDC approve
│   ├── SmartWallet.execute() → Marketplace.buy()
│   └── REST API purchase notification
│
└── StateManager (state.py)
    ├── Session budget tracking
    ├── Purchase history
    ├── Disk persistence (JSON)
    └── Reinvestment hook
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install web3 aiohttp pydantic eth-account
```

### 2. Configure the agent

```bash
cp config.example.json buyer-001.json
# Edit buyer-001.json with your contract addresses and settings
```

### 3. Set environment variables

```bash
export BUYER_AGENT_PRIVATE_KEY="0x..."
export CLAWMARKET_API_KEY="your-api-key"
```

### 4. Run

```bash
python -m agents.buyer-agent.agent buyer-001.json
```

---

## Configuration Reference

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | string | Unique identifier (e.g. `"buyer-001"`) |
| `wallet_address` | string | SmartWallet address |
| `budget_usdc` | float | Total USDC budget for this session |
| `max_single_purchase` | float | Max USDC per single purchase |
| `reinvest_ratio` | float | Fraction of profit to reinvest (0–1) |
| `strategy` | enum | `lowest-price` / `best-reputation` / `value-score` / `budget-limit` |
| `categories` | list | `compute`, `data`, `api-access`, `ai-service`, `digital` |
| `weight_price` | float | Weight for price in `value-score` (must sum to 1 with `weight_reputation`) |
| `weight_reputation` | float | Weight for reputation in `value-score` |
| `min_reputation_score` | float | Hard minimum seller reputation (0–100) |
| `max_price_premium` | float | Max % above avg price to overpay (0.05 = 5%) |
| `scan_interval_seconds` | int | Seconds between market scans |

---

## Strategies

### `lowest-price`
Prefers the cheapest listing that passes the reputation floor. Rejects listings priced more than `max_price_premium` above the market average.

### `best-reputation`
Prioritizes sellers with the highest on-chain reputation score from `ReputationScore.sol`, regardless of price (within budget limits).

### `value-score`
Composite score:
```
score = weight_price × (1 - norm_price) + weight_reputation × norm_reputation
```
Default weights: `price=0.6`, `reputation=0.4`. Adjust per risk tolerance.

### `budget-limit`
Same as `value-score` but adds a small bonus for purchases that make better use of the available budget capacity. Prevents fragmenting the budget on many tiny low-value purchases.

---

## Decision Loop

```
Every scan_interval_seconds:
  1. Fetch new listings (API + on-chain)
  2. Apply hard filters (category, reputation, budget)
  3. Score listings with active strategy
  4. Execute top candidate if score > 0
  5. Update state and persist to disk
  6. Apply reinvestment if applicable
  7. Sleep and repeat
```

---

## Running Tests

```bash
pytest agents/buyer-agent/tests/ -v
```

---

## Files

| File | Purpose |
|------|---------|
| `agent.py` | Main orchestrator, decision loop, entry point |
| `config.py` | Pydantic config schema and validation |
| `scanner.py` | Dual-source market scanner (API + Base events) |
| `strategy.py` | Strategy Engine (4 strategies) |
| `executor.py` | On-chain transaction executor |
| `state.py` | Session state, budget tracking, persistence |
| `config.example.json` | Example configuration file |
| `tests/test_strategy.py` | Unit tests for strategy engine |
