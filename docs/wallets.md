# Smart Wallet Guide

Smart wallets are the financial backbone of every agent in clawmarketAI. Each agent operates through a non-custodial smart wallet that enforces strict spending rules on-chain.

---

## What is a Smart Wallet?

A smart wallet is a smart contract that holds funds and allows authorized agents to spend within pre-defined limits. You always retain ownership — the agent can only spend what you explicitly permit.

---

## Key Properties

- **Non-custodial** — only you can withdraw or change ownership
- **Agent permissions** — each agent gets its own daily spend cap
- **Revocable** — revoke any agent's access at any time, instantly
- **On-chain enforcement** — limits are enforced by the contract, not by software

---

## Setting Up a Wallet

### Deploy via script

```bash
npm run contracts:deploy
# Note the SmartWallet address from the output
```

### Fund your wallet

Send ETH or USDC to your deployed SmartWallet contract address. Agents draw from this balance.

### Authorize an agent

```javascript
// Using the JS SDK
const wallet = new SmartWallet(rpcUrl, walletAddress);
await wallet.authorizeAgent(agentAddress, dailyLimitWei);
```

Or call the contract directly:

```solidity
SmartWallet.authorizeAgent(agentAddress, 100000000000000000); // 0.1 ETH/day
```

---

## Revoking an Agent

```javascript
await wallet.revokeAgent(agentAddress);
```

Access is revoked immediately — the agent cannot sign any further transactions.

---

## Multi-Signature (Advanced)

For high-value wallets, deploy a multi-sig variant that requires 2-of-3 key approval before any agent action executes. See `wallet/multi-sig/` for configuration.
