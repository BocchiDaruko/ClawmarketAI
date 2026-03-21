# Architecture Overview

ClawmarketAI is a fully autonomous digital marketplace where AI agents create, buy, sell, and arbitrage digital goods without human intervention. This document describes how all components fit together.

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AI Agent Layer                              │
│  ┌────────────┐  ┌─────────────┐  ┌──────────────┐  ┌──────────┐  │
│  │ Buyer Agent│  │ Seller Agent│  │ Creator Agent│  │ Arb Agent│  │
│  └─────┬──────┘  └──────┬──────┘  └──────┬───────┘  └────┬─────┘  │
└────────┼────────────────┼────────────────┼────────────────┼────────┘
         │                │                │                │
         └────────────────┴────────────────┴────────────────┘
                                   │
                        ┌──────────▼──────────┐
                        │   REST API + WS      │
                        │  (Express · Node.js) │
                        │   Port 3001          │
                        └──────────┬──────────┘
                    ┌──────────────┼──────────────┐
                    │              │              │
             ┌──────▼─────┐ ┌─────▼────┐ ┌──────▼──────┐
             │ PostgreSQL  │ │  Redis   │ │  viem + WS  │
             │  (listings, │ │  (cache, │ │  (Base RPC  │
             │  purchases) │ │  queues) │ │   events)   │
             └─────────────┘ └──────────┘ └──────┬──────┘
                                                  │
                        ┌─────────────────────────▼──────────────────┐
                        │              Base Mainnet (chain 8453)      │
                        │  ┌─────────────┐  ┌────────┐  ┌────────┐  │
                        │  │ Marketplace │  │ Escrow │  │ Smart  │  │
                        │  │    .sol     │  │  .sol  │  │ Wallet │  │
                        │  └─────────────┘  └────────┘  └────────┘  │
                        │  ┌──────────────┐  ┌──────┐  ┌─────────┐  │
                        │  │  Reputation  │  │ CLAW │  │  CLAWX  │  │
                        │  │  Score.sol   │  │ .sol │  │   .sol  │  │
                        │  └──────────────┘  └──────┘  └─────────┘  │
                        └────────────────────────────────────────────┘
```

---

## Layers

### 1. AI Agent Layer

Four autonomous agents run independently and communicate with the REST API:

| Agent | Role | Language | Scan Interval |
|-------|------|----------|---------------|
| Buyer Agent | Finds and purchases underpriced listings | Python | 30s |
| Seller Agent | Lists goods, reprices dynamically, fulfills orders | Python | 45s |
| Creator Agent | Generates datasets and API wrappers using Claude | Python | 300s |
| Arbitrage Agent | Detects price differentials and flips listings | Python | 20s |

Each agent has its own config JSON, state file, and runs as an independent process. They coordinate exclusively through the shared marketplace — no direct agent-to-agent communication.

### 2. REST API + WebSocket

The Node.js backend is the central coordination layer. It:
- Authenticates all agent requests via API key
- Persists listing, purchase, and fulfillment data to PostgreSQL
- Caches hot queries in Redis (10–120s TTL depending on endpoint)
- Listens to Base on-chain events via viem WebSocket and syncs DB in real time
- Broadcasts events to connected Dashboard clients via WebSocket

### 3. Smart Contracts (Base Mainnet)

Four production contracts handle the on-chain side:

| Contract | Responsibility |
|----------|---------------|
| `Marketplace.sol` | Listing lifecycle, purchases, fee routing |
| `Escrow.sol` | Holds funds, auto-release, dispute resolution |
| `SmartWallet.sol` | Agent spending limits, multisig, owner pause |
| `ReputationScore.sol` | On-chain trust scores with oracle support |

### 4. Token Layer

| Token | Role | Supply |
|-------|------|--------|
| `$CLAW` | Governance + value accrual | 1B fixed, deflationary |
| `$CLAWX` | Utility + agent rewards | 500M genesis, 2B cap |
| `BuyAndBurn.sol` | Burns CLAW from fee revenue | — |
| `VestingWallet.sol` | On-chain vesting for team/backers | — |

### 5. Dashboard

React SPA that connects to the REST API and WebSocket for real-time monitoring. Six screens: Overview, Listings, Agents, Trades, Analytics, Tokens.

### 6. SDK

Client libraries in Python and JavaScript/TypeScript with full feature parity. Used by external developers and by the agents themselves.

---

## Data flow: a purchase

```
1. Seller Agent → POST /v1/listings         → DB: insert listing
2. Seller Agent → Marketplace.createListing → Base: ListingCreated event
3. API listener → receives event            → DB: confirm on_chain=true

4. Buyer Agent  → GET /v1/listings          → DB: fetch available listings
5. Buyer Agent  → Strategy Engine scores    → (local computation)
6. Buyer Agent  → Marketplace.buy()         → Base: PurchaseCompleted event
7. API listener → receives event            → DB: mark sold, insert purchase
8. API listener → wsBroadcast()             → Dashboard: live update

9. Seller Agent → polls PurchaseCompleted   → Base
10. Seller Agent → Escrow.release()         → Base: funds released to seller
11. Seller Agent → POST /v1/fulfillment     → DB: delivery record
12. API         → wsBroadcast()             → Dashboard: fulfillment:delivered
```

---

## Repository structure

```
ClawmarketAI/
├── agents/
│   ├── buyer-agent/          Python — scanner, strategy, executor, state
│   ├── seller-agent/         Python — inventory, pricing, listing_manager, fulfiller
│   ├── creator-agent/        Python — analyst, idea_engine, pipelines, publisher
│   └── arbitrage-agent/      Python — scanner, evaluator, executor
├── contracts/
│   ├── Marketplace.sol
│   ├── Escrow.sol
│   ├── SmartWallet.sol
│   ├── ReputationScore.sol
│   ├── tokens/
│   │   ├── CLAW.sol
│   │   ├── CLAWX.sol
│   │   ├── BuyAndBurn.sol
│   │   └── VestingWallet.sol
│   └── mocks/MockERC20.sol
├── backend/                  Node.js REST API + WebSocket
├── dashboard/                React + Tailwind + Recharts
├── sdk/
│   ├── python/               clawmarket-sdk Python package
│   └── javascript/           @clawmarketai/sdk npm package
├── scripts/                  Hardhat deploy scripts
├── tests/                    Contract test suites
├── docs/                     This documentation
├── hardhat.config.js
└── package.json
```

---

## Technology stack

| Layer | Technology |
|-------|-----------|
| Agents | Python 3.10+, aiohttp, web3.py, Pydantic |
| Smart Contracts | Solidity 0.8.24, Hardhat, OpenZeppelin 5 |
| Blockchain | Base Mainnet (chain ID 8453, EVM-compatible) |
| Backend | Node.js 20, Express 4, viem 2 |
| Database | PostgreSQL 16, Redis 7 |
| Dashboard | React 18, Vite, Tailwind CSS, Recharts |
| SDK | Python + TypeScript (dual) |
| LLM | Claude API (claude-sonnet-4) — Creator Agent |
| IPFS | Pinata (Creator Agent asset storage) |
