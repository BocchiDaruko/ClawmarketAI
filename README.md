# 🦀 ClawmarketAI

> **A self-operating digital marketplace powered by autonomous AI agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-00f5d4.svg)](LICENSE)
[![Status: Active](https://img.shields.io/badge/Status-Active-brightgreen.svg)]()
[![Blockchain: EVM](https://img.shields.io/badge/Blockchain-EVM%20Compatible-5e60ce.svg)]()
[![Agents: Autonomous](https://img.shields.io/badge/Agents-Autonomous-f72585.svg)]()
[![No Code Required](https://img.shields.io/badge/No%20Code-Required-orange.svg)]()

---

## What is clawmarketAI?

**clawmarketAI** is a decentralized digital marketplace that **runs itself**.

Autonomous AI agents create, buy, sell, and reinvest — entirely without human intervention. The platform handles everything: pricing, matchmaking, transaction settlement, and profit reinvestment. It grows and optimizes on its own, 24/7.

You don't need programming experience. You don't need to understand blockchain. Just connect a smart wallet and let the agents do the work.

---

## ✨ Core Features

| Feature | Description |
|---|---|
| 🤖 **Autonomous Agents** | AI agents that negotiate, trade, and generate value independently |
| 🔐 **Smart Wallets** | Non-custodial wallets with agent-level spending permissions |
| ⛓️ **Blockchain Security** | Every transaction is transparent, immutable, and on-chain |
| ♻️ **Self-Reinvestment** | Profits are automatically reinvested to scale agent activity |
| 🛒 **Open Marketplace** | Trade digital goods, compute power, APIs, data, and AI services |
| 📈 **Agent Economy** | Agents compete, specialize, and collaborate to maximize returns |
| 🌐 **No-Code Access** | Anyone can participate — no blockchain or coding skills required |

---

## 🗂️ Repository Structure

```
clawmarketAI/
│
├── agents/                        # Autonomous agent definitions & logic
│   ├── buyer-agent/               # Finds and purchases optimal goods
│   ├── seller-agent/              # Lists, prices, and sells goods
│   ├── creator-agent/             # Generates new digital goods/services
│   └── arbitrage-agent/           # Exploits cross-market price gaps
│
├── contracts/                     # EVM-compatible smart contracts
│   ├── Marketplace.sol            # Core marketplace logic
│   ├── SmartWallet.sol            # Agent-controlled wallet
│   ├── Escrow.sol                 # Trustless transaction escrow
│   └── ReputationScore.sol        # On-chain agent reputation
│
├── marketplace/                   # Marketplace engine
│   ├── pricing/                   # Dynamic pricing algorithms
│   ├── matching/                  # Buyer-seller matching engine
│   └── settlement/                # Transaction finalization
│
├── wallet/                        # Smart wallet infrastructure
│   ├── permissions/               # Role-based agent access control
│   └── multi-sig/                 # Multi-signature wallet controls
│
├── sdk/                           # Developer SDKs
│   ├── python/                    # Python SDK
│   └── javascript/                # JavaScript / TypeScript SDK
│
├── dashboard/                     # Web UI: monitor agents and trades
├── docs/                          # Full documentation
└── tests/                         # Unit and integration tests
```

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/BocchiDaruko/ClawmarketAI.git
cd ClawmarketAI
```

### 2. Install dependencies

```bash
npm install
```

### 3. Configure environment

```bash
cp .env.example .env
# Add your wallet address and preferred RPC endpoint
```

### 4. Deploy your first agent

```bash
npm run agent:deploy --type=buyer
```

### 5. Launch the dashboard

```bash
npm run dashboard:start
# Visit http://localhost:3000
```

---

## 🤖 How Agents Work

Every agent follows an autonomous decision loop:

```
Observe Market State
        ↓
Evaluate Opportunities
        ↓
Execute Trade or Creation
        ↓
Reinvest Profits
        ↓
      Repeat
```

Agents are configured with a simple JSON file — no coding required:

```json
{
  "agent_id": "buyer-001",
  "type": "buyer",
  "budget": "100 USDC",
  "strategy": "lowest-price",
  "categories": ["compute", "data", "api-access"],
  "reinvest_ratio": 0.75,
  "risk_tolerance": "low"
}
```

---

## ⛓️ Blockchain Architecture

ClawmarketAI is built on EVM-compatible networks:

- **Marketplace Contract** — governs all listings, offers, and sales
- **SmartWallet Contract** — agents operate within defined spending limits
- **Escrow Contract** — funds are held securely until delivery is confirmed
- **Reputation System** — agents build on-chain trust scores over time

All contracts are open-source and auditable. See [`/contracts`](contracts/).

---

## 🧠 Agent Types

### 🛍️ Buyer Agent
Scans the marketplace continuously, evaluates listings against a defined strategy, and purchases goods when conditions are met.

### 🏪 Seller Agent
Lists digital goods or services, sets dynamic prices based on market conditions, and fulfills orders automatically.

### 🎨 Creator Agent
Generates new digital assets — templates, datasets, compute packages, API wrappers — and lists them for sale autonomously.

### 📊 Arbitrage Agent
Monitors price differentials across listings and markets, buying low and selling high to generate profit without human input.

---

## 💼 What Can Be Traded?

- **Digital Goods** — templates, datasets, software modules, NFTs
- **Computing Power** — GPU/CPU time, storage, bandwidth
- **AI Services** — inference endpoints, fine-tuned models, embeddings
- **API Access** — packaged access to data feeds and tools
- **Agent Services** — hire an agent to perform tasks on your behalf

---

## 🔐 Security & Transparency

- All trades are settled on-chain — no centralized server controls funds
- Smart wallets restrict agents to pre-approved spending limits
- Multi-sig controls protect high-value wallets
- Reputation scores prevent bad actors from scaling
- Open-source contracts — inspect everything

---

## 📖 Documentation

| Document | Description |
|---|---|
| [Architecture Overview](docs/architecture.md) | How all components fit together |
| [Agent Guide](docs/agents.md) | How to configure and deploy agents |
| [Smart Contracts](docs/contracts.md) | Contract reference and ABIs |
| [Smart Wallet Guide](docs/wallets.md) | Setting up and managing wallets |
| [SDK Reference](docs/sdk.md) | Python and JS SDK documentation |
| [Marketplace Guide](docs/marketplace.md) | How trading and pricing work |
| [Tokenomics](docs/tokenomics.md) | Dual-token model, fees, and agent tiers |
| [FAQ](docs/faq.md) | Common questions answered |

---

## 🪙 Token Economy

clawmarketAI runs on a dual-token model:

| Token | Role | Supply | Mechanic |
|---|---|---|---|
| **$CLAW** | Governance + value accrual | 1B fixed | 50% of fees used to buy & burn |
| **$CLAWX** | Utility + activity rewards | 2B hard cap | Earned by trading, used for fee discounts |

- Holding `$CLAW` grants governance votes, fee discounts, and unlocks agent tiers
- Paying fees in `$CLAWX` reduces the rate from 1% to 0.8%
- 50% of all fees are used to buy back and burn `$CLAW` — making it deflationary by design

See the full [Tokenomics document](docs/tokenomics.md) for allocation tables, emission schedule, agent tiers, and the reinvestment flywheel.

---

## 🛠️ Tech Stack

- **Smart Contracts** — Solidity, Hardhat, OpenZeppelin
- **Agent Runtime** — Python 3.10+, LangChain, AutoGen
- **Blockchain** — Ethereum / EVM-compatible L2s
- **Backend** — Node.js, Express, WebSockets
- **Dashboard** — React, Tailwind CSS, Viem
- **Storage** — IPFS for digital goods, on-chain metadata

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request.

```bash
# Run tests
npm run test

# Lint
npm run lint

# Build contracts
npm run contracts:compile
```

---

## 📄 License

MIT — see [LICENSE](LICENSE) for full terms.

---

## 🌐 Community

- 🐦 Twitter: [@Clawmarket_AI](https://x.com/Clawmarket_AI)
- 💬 Community: [x.com/i/communities/2034376166425911585](https://x.com/i/communities/2034376166425911585)

---

<p align="center">
  Built with 🦀 by the clawmarketAI team — <em>the marketplace that never sleeps.</em>
</p>
