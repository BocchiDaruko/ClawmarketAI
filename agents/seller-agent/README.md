# 🏪 Seller Agent — ClawmarketAI

Autonomous seller agent that lists digital goods on the ClawmarketAI marketplace, continuously adjusts prices using a 4-mode dynamic pricing engine, and fulfills orders automatically via on-chain Escrow settlement + REST API delivery — without human intervention.

Operates on **Base** (mainnet, chain ID 8453).

---

## Architecture

```
SellerAgent (agent.py)
│
├── InventoryManager (inventory.py)
│   ├── Active listing tracker
│   ├── Sales history
│   └── Disk persistence (JSON)
│
├── DynamicPricingEngine (pricing.py)
│   ├── demand      — surge pricing by request count
│   ├── competition — undercut similar listings
│   ├── time-decay  — discount unsold listings over time
│   └── floor-price — enforce minimum margin
│
├── ListingManager (listing_manager.py)
│   ├── createListing  → Marketplace.sol via SmartWallet
│   ├── updatePrice    → on-chain reprice
│   ├── cancelListing  → delist
│   └── REST API sync  → POST /listings
│
└── OrderFulfiller (fulfiller.py)
    ├── Poll PurchaseCompleted events on Base
    ├── Escrow.release() → seller wallet  (on-chain)
    └── POST /fulfillment → access delivery (API)
```

---

## Supported Goods

| Type | Example |
|------|---------|
| `compute` | GPU/CPU time (e.g. 1h A100) |
| `data` | Datasets, price feeds, OHLCV |
| `ai-service` | Embeddings, inference endpoints |
| `api-access` | Timed API keys, rate-limited access |

---

## Pricing Modes

All 4 modes are applied sequentially in this order:

### 1. `demand` — surge pricing
Price increases by `demand_surge_pct` for each request in the demand window.
Capped at 3× base price.

### 2. `time-decay` — age discount
Price decreases by `time_decay_pct_per_hour` for each hour the listing hasn't sold.
Maximum discount capped at `time_decay_max_pct` (default 30%).

### 3. `competition` — market undercut
Fetches average market price via REST API.
If our price is above market, undercuts by `competition_undercut_pct` (default 2%).

### 4. `floor-price` — hard minimum (always last)
Price can never go below `cost × (1 + min_margin_pct)`.
Protects against selling at a loss even under heavy decay or competition pressure.

---

## Fulfillment Flow

```
PurchaseCompleted event (Base)
        ↓
Escrow.release() via SmartWallet   ← on-chain settlement
        ↓
POST /fulfillment                  ← API delivery
  (credentials, S3 link, API key, etc.)
        ↓
Inventory marked delivered
```

---

## Quick Start

```bash
# 1. Install deps
pip install web3 aiohttp pydantic eth-account

# 2. Configure
cp config.example.json seller-001.json
# Fill in contract addresses, goods catalogue, and settings

# 3. Set env vars
export SELLER_AGENT_PRIVATE_KEY="0x..."
export CLAWMARKET_API_KEY="your-api-key"

# 4. Run
python -m agents.seller-agent.agent seller-001.json
```

---

## Configuration Reference

| Field | Type | Description |
|-------|------|-------------|
| `goods` | list | Catalogue of goods to list (see below) |
| `pricing_modes` | list | Active pricing modes |
| `demand_surge_pct` | float | Price increase per demand unit (0.05 = 5%) |
| `competition_undercut_pct` | float | Undercut market by this % (0.02 = 2%) |
| `time_decay_pct_per_hour` | float | Discount per hour unsold (0.01 = 1%) |
| `time_decay_max_pct` | float | Max discount from time decay (0.30 = 30%) |
| `fulfillment_mode` | enum | `onchain` / `api` / `both` |
| `relist_after_minutes` | int | Minutes before triggering a reprice |

### Good Template fields

| Field | Description |
|-------|-------------|
| `good_type` | `compute` / `data` / `ai-service` / `api-access` |
| `base_price_usdc` | Starting price before pricing adjustments |
| `cost_usdc` | Agent's cost to deliver (used for margin calculation) |
| `min_margin_pct` | Floor = cost × (1 + min_margin_pct) |
| `delivery_config` | JSON payload passed to `/fulfillment` at sale time |
| `max_concurrent_listings` | How many active listings to maintain at once |

---

## Running Tests

```bash
pytest agents/seller-agent/tests/ -v
```

---

## Files

| File | Purpose |
|------|---------|
| `agent.py` | Main orchestrator and entry point |
| `config.py` | Pydantic config schema |
| `inventory.py` | Active listing and sales tracking |
| `pricing.py` | Dynamic Pricing Engine (4 modes) |
| `listing_manager.py` | On-chain listing lifecycle |
| `fulfiller.py` | Order fulfillment (Escrow + API) |
| `config.example.json` | Example config with all 4 good types |
| `tests/test_pricing.py` | Unit tests for pricing engine |
