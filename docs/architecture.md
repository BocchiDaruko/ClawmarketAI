# Architecture Overview

clawmarketAI is composed of four primary layers that work together to create a fully autonomous marketplace.

---

## System Layers

```
┌─────────────────────────────────────────────┐
│             USER / WALLET LAYER             │
│   Smart Wallets  ·  No-Code Dashboard       │
├─────────────────────────────────────────────┤
│               AGENT LAYER                   │
│  Buyer · Seller · Creator · Arbitrage       │
├─────────────────────────────────────────────┤
│            MARKETPLACE ENGINE               │
│   Pricing · Matching · Settlement           │
├─────────────────────────────────────────────┤
│           BLOCKCHAIN LAYER                  │
│  Marketplace.sol · Escrow.sol · Wallet.sol  │
└─────────────────────────────────────────────┘
```

---

## Data Flow

1. **Agent observes** the marketplace state via on-chain events and off-chain indexers
2. **Agent decides** based on its strategy configuration
3. **Agent signs** a transaction using its smart wallet (within permitted limits)
4. **Marketplace contract** validates and settles the trade
5. **Escrow contract** holds funds until delivery is confirmed
6. **Profits are reinvested** automatically by the agent's reinvestment module

---

## Key Design Principles

- **Trustless** — no central party can block or reverse transactions
- **Permissionless** — anyone can deploy an agent or list a good
- **Composable** — agents and contracts can be combined and extended
- **Self-sustaining** — the system generates its own operational revenue
