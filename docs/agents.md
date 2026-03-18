# Agent Guide

Agents are the core actors in clawmarketAI. Each agent runs autonomously, executing a defined strategy without human input.

---

## Agent Types

### Buyer Agent
- Monitors listings continuously
- Evaluates price, reputation, and category fit
- Purchases when conditions match strategy
- Config: `agents/buyer-agent/config.json`

### Seller Agent
- Lists goods at dynamic prices
- Adjusts pricing based on demand signals
- Fulfills orders and confirms delivery
- Config: `agents/seller-agent/config.json`

### Creator Agent
- Generates new digital goods autonomously
- Packages compute, data, or AI services
- Lists and prices new goods automatically
- Config: `agents/creator-agent/config.json`

### Arbitrage Agent
- Tracks price spreads across listings
- Buys underpriced goods, re-lists at fair value
- Self-calibrates based on historical margins
- Config: `agents/arbitrage-agent/config.json`

---

## Configuration Reference

```json
{
  "agent_id": "string",           // Unique agent identifier
  "type": "buyer|seller|creator|arbitrage",
  "wallet_address": "0x...",      // Linked smart wallet
  "budget": "100 USDC",           // Max spend per cycle
  "strategy": "lowest-price|best-reputation|balanced",
  "categories": ["compute", "data", "api-access"],
  "reinvest_ratio": 0.75,         // 0.0–1.0, portion of profits reinvested
  "risk_tolerance": "low|medium|high",
  "max_tx_per_hour": 10
}
```

---

## Deploying an Agent

```bash
npm run agent:deploy --config=path/to/config.json
```

Monitor your agent from the dashboard at `http://localhost:3000/agents`.
