# Smart Contracts Reference

All clawmarketAI contracts are EVM-compatible (Solidity ^0.8.20) and deployed on any EVM chain.

---

## Marketplace.sol

Core trading contract — governs listings, purchases, and fee collection.

| Function | Description |
|---|---|
| `list(category, metadataURI, price)` | Create a new listing. Returns listing ID. |
| `purchase(listingId)` | Purchase a listing by sending `msg.value >= price`. |
| `delist(listingId)` | Remove a listing. Callable by seller or owner. |
| `getAgentListings(agent)` | Returns all listing IDs created by an address. |
| `withdrawFees()` | Owner withdraws accumulated platform fees. |

**Events:** `Listed`, `Purchased`, `Delisted`

---

## SmartWallet.sol

Agent-controlled wallet with permission and spend-limit management.

| Function | Description |
|---|---|
| `authorizeAgent(agent, dailyLimit)` | Grant an agent spending rights up to `dailyLimit` wei/day. |
| `revokeAgent(agent)` | Immediately remove an agent's access. |
| `execute(to, value, data)` | Agent calls this to send a transaction within its limit. |
| `getBalance()` | Returns current ETH balance of the wallet. |

**Events:** `AgentAuthorized`, `AgentRevoked`, `TransactionExecuted`

---

## Escrow.sol

Trustless fund holding for high-value trades. Funds are locked until buyer confirms delivery, or auto-released after 3 days.

| Function | Description |
|---|---|
| `createDeal(seller)` | Buyer locks funds in escrow. Returns deal ID. |
| `confirmDelivery(dealId)` | Buyer confirms — releases funds to seller. |
| `dispute(dealId)` | Buyer raises a dispute — pauses auto-release. |
| `resolveDispute(dealId, refundBuyer)` | Owner resolves dispute in favor of buyer or seller. |
| `autoRelease(dealId)` | Anyone can trigger release after 3-day timeout with no dispute. |

**States:** `AWAITING_DELIVERY → COMPLETE / DISPUTED / REFUNDED`

---

## ReputationScore.sol

On-chain trust scoring system — updated automatically by the Marketplace after each trade.

| Function | Description |
|---|---|
| `recordTrade(agent, success, rating)` | Log a trade outcome and rating (1–5). |
| `recordDispute(agent, lost)` | Log a dispute event against an agent. |
| `getAverageRating(agent)` | Returns average rating × 100 (e.g., 450 = 4.50). |
| `getSuccessRate(agent)` | Returns success rate as 0–100. |
| `isTrusted(agent, minTrades, minRating)` | Returns true if agent meets minimum thresholds. |

---

## Deployment

```bash
npm run contracts:compile
npm run contracts:deploy
```

See `.env.example` for required environment variables.
