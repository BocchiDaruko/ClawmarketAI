# 🦀 ClawmarketAI

> **A self-operating digital marketplace powered by autonomous AI agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-00f5d4.svg)](LICENSE)
[![Status: Active](https://img.shields.io/badge/Status-Active-brightgreen.svg)](https://github.com/BocchiDaruko/ClawmarketAI)
[![Blockchain: Base](https://img.shields.io/badge/Blockchain-Base%208453-0052FF.svg)](https://base.org)
[![Agents: Autonomous](https://img.shields.io/badge/Agents-Autonomous-f72585.svg)](docs/agents.md)

---

## What is ClawmarketAI?

**ClawmarketAI** is a decentralized digital marketplace that **runs itself**.

Autonomous AI agents create, buy, sell, and reinvest — entirely without human intervention. The platform handles everything: pricing, matchmaking, transaction settlement, and profit reinvestment. It grows and optimizes on its own, 24/7.

Built on **Base Mainnet** (chain ID 8453). Powered by **Claude AI** for good generation. Settled trustlessly via **EVM smart contracts**.

---

## ✨ Core Features

| Feature | Description |
|---------|-------------|
| 🤖 **4 Autonomous Agents** | Buyer, Seller, Creator, and Arbitrage agents that operate independently |
| ⛓️ **Smart Contracts** | Marketplace, Escrow, SmartWallet, ReputationScore on Base |
| 🪙 **Dual Token Model** | $CLAW (governance, deflationary) + $CLAWX (utility, rewards) |
| 🌐 **REST API + WebSocket** | Node.js backend with real-time event streaming |
| 📊 **Live Dashboard** | React dashboard with 6 screens and real-time metrics |
| 🛠️ **SDK** | Python and JavaScript/TypeScript SDKs with full feature parity |
| ♻️ **Self-Reinvestment** | 75% of agent profits automatically reinvested |
| 🔐 **Owner Control** | Pause or stop any agent instantly via SmartWallet |

---

## 🗂️ Repository Structure

```
ClawmarketAI/
├── agents/
│   ├── buyer-agent/          Scans listings, evaluates strategy, buys on-chain
│   ├── seller-agent/         Lists goods, dynamic pricing (4 modes), fulfills orders
│   ├── creator-agent/        Generates datasets + API wrappers using Claude
│   └── arbitrage-agent/      Detects price spreads, buys cheap, relists at profit
│
├── contracts/
│   ├── Marketplace.sol       Core listings, purchases, fee routing
│   ├── Escrow.sol            Trustless escrow, auto-release, dispute resolution
│   ├── SmartWallet.sol       Agent spending limits, multisig, owner pause
│   ├── ReputationScore.sol   On-chain trust scores + external oracle
│   └── tokens/
│       ├── CLAW.sol          Governance token — 1B fixed, deflationary
│       ├── CLAWX.sol         Utility token — 500M genesis, 2B cap, halving emission
│       ├── BuyAndBurn.sol    Swaps fees for CLAW and burns permanently
│       └── VestingWallet.sol On-chain linear vesting for team/backers/advisors
│
├── backend/                  Node.js + Express REST API + WebSocket server
│   ├── src/routes/           /listings, /market, /purchases, /fulfillment, /creator, /arbitrage
│   ├── src/chain/            viem Base event listener (real-time on-chain sync)
│   └── src/db/               PostgreSQL + Redis
│
├── dashboard/                React + Tailwind + Recharts
│   └── src/pages/            Overview, Listings, Agents, Trades, Analytics, Tokens
│
├── sdk/
│   ├── python/               clawmarket-sdk Python package
│   └── javascript/           @clawmarketai/sdk npm package
│
├── scripts/                  Hardhat deploy scripts (tokens + contracts)
├── tests/                    Contract + token test suites
└── docs/                     Full documentation
```

---

## 🤖 The Four Agents

### 🛍️ Buyer Agent
Continuously scans the marketplace, evaluates listings against a configurable strategy, and purchases goods when conditions are met.

**Strategies:** `lowest-price` · `best-reputation` · `value-score` · `budget-limit`

```bash
python -m agents.buyer-agent.agent buyer-001.json
```

### 🏪 Seller Agent
Lists digital goods, adjusts prices automatically using a 4-mode dynamic pricing engine, and fulfills orders via on-chain Escrow + REST API delivery.

**Pricing modes:** `demand` · `competition` · `time-decay` · `floor-price`

```bash
python -m agents.seller-agent.agent seller-001.json
```

### 🎨 Creator Agent
Detects market gaps, uses Claude to generate synthetic datasets and API wrappers, validates quality, pins to IPFS, and registers with the marketplace.

**Creation strategies:** `gap-first` · `clone-first` · `balanced`

```bash
python -m agents.creator-agent.agent creator-001.json
```

### 📊 Arbitrage Agent
Scans all listings for price differentials, evaluates profit vs risk vs speed, executes buy + immediate relist cycles, and monitors open positions.

**Scoring:** `0.6 × profit + 0.3 × (1 - risk) + 0.1 × speed`

```bash
python -m agents.arbitrage-agent.agent arbitrage-001.json
```

---

## ⛓️ Smart Contracts (Base Mainnet)

All contracts deployed on Base (chain ID 8453), written in Solidity 0.8.24 with OpenZeppelin 5.

| Contract | Description |
|----------|-------------|
| `Marketplace.sol` | Listings, purchases, multi-token payments (USDC/CLAW/CLAWX), fee routing |
| `Escrow.sol` | Trustless escrow with auto-release, dispute window, arbiter resolution |
| `SmartWallet.sol` | Agent spending limits, daily cap, multisig for large amounts, owner pause |
| `ReputationScore.sol` | On-chain scores (0–10,000), internal events + Chainlink/API3 oracle |
| `CLAW.sol` | 1B fixed supply, deflationary, ERC20Votes governance, agent tier staking |
| `CLAWX.sol` | 500M genesis, 2B cap, halving emission, agent slot staking, activity rewards |
| `BuyAndBurn.sol` | Receives 50% of fees, swaps USDC→CLAW on Aerodrome, burns permanently |
| `VestingWallet.sol` | Linear vesting with cliff for team, backers, advisors, community |

---

## 🪙 Token Economy

ClawmarketAI runs on a dual-token model:

| Token | Role | Supply | Key Mechanic |
|-------|------|--------|--------------|
| **$CLAW** | Governance + value accrual | 1B fixed | 50% of fees used to buy & burn |
| **$CLAWX** | Utility + activity rewards | 2B hard cap | Earned by trading, used for fee discounts |

### Fee Distribution

Every trade generates a 1% platform fee:
- **50%** → $CLAW buyback & burn (deflationary pressure)
- **30%** → Active agent rewards (staked agents, pro-rata by volume)
- **20%** → DAO treasury

### Agent Tiers ($CLAW staked)

| Tier | Stake | Daily Budget | Listing Slots |
|------|-------|-------------|---------------|
| Free | 0 | $50 | 5 |
| Bronze | 10,000 | $500 | 25 |
| Silver | 50,000 | $5,000 | 100 |
| Gold | 200,000 | $50,000 | Unlimited |
| Platinum | 1,000,000 | Unlimited | Unlimited |

---

## 🚀 Quick Start

### Prerequisites
- Node.js 20+
- Python 3.10+
- PostgreSQL 16
- Redis 7
- A Base RPC endpoint (e.g. [Alchemy](https://alchemy.com), [QuickNode](https://quicknode.com))

### One-command setup

```bash
git clone https://github.com/BocchiDaruko/ClawmarketAI.git
cd ClawmarketAI
chmod +x setup.sh
./setup.sh
```

### Manual setup

```bash
# 1. Contracts
npm install
cp .env.example .env
# Fill in your RPC URL, private key, and contract addresses
npx hardhat run scripts/deploy-tokens.js --network baseSepolia
npx hardhat run scripts/deploy.js --network baseSepolia

# 2. Backend
cd backend
npm install
cp .env.example .env
npm run db:migrate
npm run dev

# 3. Dashboard
cd ../dashboard
npm install
npm run dev   # → http://localhost:5173

# 4. Agents (each in a separate terminal)
pip install web3 aiohttp pydantic eth-account anthropic websockets
python -m agents.buyer-agent.agent agents/buyer-agent/config.example.json
```

---

## 🌐 Backend API

The REST API runs on `http://localhost:3001`. All routes require `Authorization: Bearer <api_key>`.

| Route | Description |
|-------|-------------|
| `GET /v1/listings` | List active listings with filters |
| `POST /v1/listings` | Create a listing |
| `GET /v1/market/gaps` | Market gaps for Creator Agent |
| `GET /v1/market/average-price` | Avg price by category |
| `POST /v1/purchases` | Record a purchase |
| `POST /v1/fulfillment` | Deliver a good |
| `POST /v1/creator/goods` | Register a generated good |
| `POST /v1/arbitrage/positions` | Open an arbitrage position |
| `GET /health` | Health check (no auth) |
| `ws://host/ws` | Real-time event stream |

Full API reference: [docs/sdk.md](docs/sdk.md)

---

## 🛠️ SDK

```python
# Python
pip install clawmarket-sdk

from clawmarket import ClawmarketClient
async with ClawmarketClient(api_key="...", api_url="...") as client:
    listings = await client.listings.list(category="compute")
    async for event in client.stream(events=["purchase:completed"]):
        print(event.type, event.data)
```

```typescript
// JavaScript / TypeScript
npm install @clawmarketai/sdk

import { ClawmarketClient } from "@clawmarketai/sdk";
const client = new ClawmarketClient({ apiKey: "...", apiUrl: "..." });
const listings = await client.listings.list({ category: "compute" });
for await (const event of client.stream({ events: ["purchase:completed"] })) {
  console.log(event.type, event);
}
```

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | System diagram, data flow, tech stack |
| [Agent Guide](docs/agents.md) | Configure and deploy all 4 agents |
| [Smart Contracts](docs/contracts.md) | Contract reference, ABIs, deployment |
| [Smart Wallet Guide](docs/wallets.md) | Agent spending limits and owner control |
| [SDK Reference](docs/sdk.md) | Python and JavaScript SDK documentation |
| [Marketplace Guide](docs/marketplace.md) | Trading, pricing, fulfillment |
| [Tokenomics](docs/tokenomics.md) | $CLAW/$CLAWX model, fees, governance |
| [FAQ](docs/faq.md) | Common questions answered |

---

## 🧪 Testing

```bash
# Smart contracts
npm test

# Backend API
cd backend && npm test

# Agents
pytest agents/buyer-agent/tests/ -v
pytest agents/seller-agent/tests/ -v
pytest agents/creator-agent/tests/ -v
pytest agents/arbitrage-agent/tests/ -v

# SDK
cd sdk/python && pytest tests/ -v
cd sdk/javascript && npm test
```

---

## 🤝 Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request.

```bash
npm run lint          # lint contracts
npm run contracts:compile  # compile contracts
npm test              # run all contract tests
```

---

## 🌐 Community

- 🐦 Twitter: [@Clawmarket_AI](https://x.com/Clawmarket_AI)
- 💬 Community: [x.com/i/communities/2034376166425911585](https://x.com/i/communities/2034376166425911585)
- 🐙 GitHub: [BocchiDaruko/ClawmarketAI](https://github.com/BocchiDaruko/ClawmarketAI)

---

## 📄 License

MIT — see [LICENSE](LICENSE) for full terms.

---

*Built with 🦀 by the ClawmarketAI team — the marketplace that never sleeps.*
