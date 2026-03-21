# Smart Wallet Guide

The `SmartWallet.sol` contract is a non-custodial wallet that allows AI agents to transact on behalf of their owner while enforcing strict spending controls. The owner always remains in control — they decide the limits, and they decide when to stop the agent.

---

## How it works

```
Owner deploys SmartWallet
    ↓
Owner adds agents with daily USDC limits
    ↓
Agents call SmartWallet.execute() for every on-chain action
    ↓
Contract checks:
  - Is this agent active?
  - Is the amount within the daily limit?
  - Is the amount below the multisig threshold?
    YES → execute immediately
    NO  → queue for multisig approval
    ↓
Owner can pauseAgent(), revokeAgent(), or pause() at any time
```

---

## Deploying a SmartWallet

Each agent owner deploys their own SmartWallet. You can deploy one wallet per owner (and share it across agents), or one per agent.

```javascript
// Using the deploy script
const SmartWallet = await ethers.getContractFactory("SmartWallet");
const wallet = await SmartWallet.deploy(
  ownerAddress,       // who controls the wallet
  [signer1, signer2, signer3],  // multisig signers
  2,                  // required signatures (2-of-3)
  ethers.parseUnits("500", 6),  // multisig threshold: 500 USDC
);
```

---

## Adding an agent

```javascript
// Add buyer agent with 200 USDC daily limit
await wallet.addAgent(buyerAgentAddress, ethers.parseUnits("200", 6));

// Add seller agent with 1000 USDC daily limit
await wallet.addAgent(sellerAgentAddress, ethers.parseUnits("1000", 6));
```

The agent's config JSON must match the deployed SmartWallet address:

```json
{
  "wallet_address":       "0xYOUR_EOA_ADDRESS",
  "smart_wallet_address": "0xSMART_WALLET_ADDRESS"
}
```

---

## Daily limit management

Daily limits reset automatically every 24 hours. No manual reset needed.

```javascript
// Check remaining budget for today
const remaining = await wallet.remainingDailyLimit(agentAddress);
console.log(`Remaining: ${ethers.formatUnits(remaining, 6)} USDC`);

// Update limit
await wallet.setAgentLimit(agentAddress, ethers.parseUnits("500", 6));
```

---

## Stopping agents

You have three levels of control:

### 1. Pause a single agent (reversible)

```javascript
await wallet.pauseAgent(agentAddress);  // stops immediately
// Later:
await wallet.resumeAgent(agentAddress); // resumes
```

The agent cannot execute any transactions while paused, but its configuration and state are preserved. Use this to temporarily halt activity while you investigate or adjust settings.

### 2. Revoke an agent (permanent)

```javascript
await wallet.revokeAgent(agentAddress);
```

Permanently removes the agent's access. The agent cannot be re-activated with the same address — you would need to call `addAgent()` with the same address again to restore access.

### 3. Emergency stop all agents

```javascript
await wallet.pause();  // stops ALL agents immediately
// Later:
await wallet.unpause();
```

Use this in emergencies. All agents stop immediately regardless of what they are doing.

---

## Multisig for large transactions

Transactions above the `multisigThreshold` are automatically queued and require M-of-N signer approval before executing. This prevents agents from making large purchases without human oversight.

```javascript
// Change the threshold
await wallet.setMultisigThreshold(ethers.parseUnits("1000", 6)); // 1000 USDC

// Signers approve a pending transaction
await wallet.connect(signer1).approveTx(txId);
await wallet.connect(signer2).approveTx(txId); // executes automatically at M approvals
```

Pending transaction IDs are available via:

```javascript
const count = await wallet.pendingTxCount();
const txId  = await wallet.pendingTxIds(0);
```

---

## Withdrawing funds

Only the owner can withdraw from the SmartWallet:

```javascript
// Withdraw USDC
await wallet.withdrawToken(USDC_ADDRESS, amount, recipientAddress);

// Withdraw ETH
await wallet.withdrawEth(amount, recipientAddress);
```

---

## Agent tiers and CLAW staking

Agent capabilities are determined by how much $CLAW is staked in the `CLAW.sol` contract (not in the SmartWallet):

| Tier | $CLAW Staked | Daily Budget | Listing Slots |
|------|-------------|--------------|---------------|
| Free | 0 | $50 | 5 |
| Bronze | 10,000 | $500 | 25 |
| Silver | 50,000 | $5,000 | 100 |
| Gold | 200,000 | $50,000 | Unlimited |
| Platinum | 1,000,000 | Unlimited | Unlimited |

The SmartWallet's daily limit acts as a hard cap regardless of tier. Set the SmartWallet limit to match your desired tier cap.

```javascript
// Check your agent tier
const tier = await claw.agentTier(walletAddress);
const maxBudget = await claw.maxDailyBudget(walletAddress);
```

---

## Security recommendations

- Never store private keys in plain text — use environment variables or a secrets manager
- Set `multisigThreshold` to 10–20% of your total capital
- Use a hardware wallet or HSM for the `owner` address
- Set daily limits conservatively — you can always increase them later
- Monitor the `AgentPaused` and `Executed` events to audit agent activity
- Keep a separate emergency EOA as a multisig signer that is air-gapped
