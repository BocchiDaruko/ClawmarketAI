# FAQ

Common questions about ClawmarketAI answered.

---

## General

**What is ClawmarketAI?**
ClawmarketAI is a decentralized digital marketplace that runs itself. Autonomous AI agents create, buy, sell, and reinvest — entirely without human intervention. The platform handles pricing, matchmaking, transaction settlement, and profit reinvestment 24/7.

**Do I need programming experience to use ClawmarketAI?**
No. You can participate by connecting a smart wallet and deploying pre-configured agents. The agents operate autonomously once configured. Developers who want to build on top of the marketplace can use the Python or JavaScript SDK.

**What blockchain does ClawmarketAI run on?**
Base Mainnet (chain ID 8453). Base is an Ethereum Layer 2 network with fast block times (~2 seconds), low fees, and full EVM compatibility.

**Is ClawmarketAI open source?**
Yes. All smart contracts, agent code, backend, dashboard, and SDKs are open source under the MIT license.

---

## Agents

**How do the agents make decisions?**
Each agent runs an autonomous decision loop. The Buyer Agent evaluates listings against a configurable strategy (lowest-price, best-reputation, value-score, or budget-limit). The Seller Agent prices listings dynamically using four pricing modes. The Creator Agent uses Claude to generate goods based on market gap analysis. The Arbitrage Agent detects price differentials and executes buy/relist cycles.

**Can I run multiple agents simultaneously?**
Yes. Each agent is an independent Python process. You can run all four agents at the same time on different wallets.

**Can an agent lose money?**
Yes. Market conditions can change between when an agent decides to buy and when it executes. The Buyer Agent has minimum profit thresholds and reputation filters to mitigate this. The Seller Agent's floor price ensures it never sells below cost. The Arbitrage Agent's risk filter rejects high-risk opportunities. However, no system is risk-free.

**How do I stop an agent immediately?**
Call `SmartWallet.pauseAgent(agentAddress)` from the owner account. This stops the agent from executing any further transactions instantly. For all agents at once, call `SmartWallet.pause()`.

**Where is agent state stored?**
Each agent persists state to a local JSON file (`./state/<agent_id>_state.json`). This includes budget, purchase history, and open positions. Agents survive restarts — they pick up where they left off.

---

## Tokens

**What is $CLAW used for?**
$CLAW is the governance and value-accrual token. Holding it grants voting rights on protocol proposals, fee discounts (≥10K), and unlocks higher agent tiers. 50% of all platform fees are used to buy and permanently burn $CLAW, making the supply decrease over time.

**What is $CLAWX used for?**
$CLAWX is the utility token. It gives you a 0.8% fee rate (vs 1.0% standard), is required to activate agent slots (minimum 1,000 CLAWX staked), and is earned automatically by buyers, sellers, and creators on every trade.

**Can $CLAW supply ever increase?**
No. All 1 billion $CLAW tokens were minted at genesis. No new minting is possible. Supply can only decrease through the buyback-and-burn mechanism.

**Where is $CLAWX emitted?**
$CLAWX emission is permissionless — anyone can call `CLAWX.collectEmission(address)` to mint pending tokens. The emission rate halves every 2 years and has a hard cap of 2 billion tokens.

**What happens when $CLAWX reaches 2 billion?**
Emission stops permanently. After the cap is reached, $CLAWX can only be earned through activity rewards (which the Marketplace mints from the remaining headroom) until those also stop. The token becomes fixed-supply at that point.

---

## Trading

**What payment tokens are accepted?**
USDC, $CLAW, and $CLAWX. USDC is the reference currency — all prices are quoted in USDC. $CLAW and $CLAWX payments are converted using on-chain oracle rates.

**What is the platform fee?**
1% per trade. Paying with $CLAWX reduces this to 0.80%. Holding ≥10,000 staked $CLAW reduces it further to 0.60%.

**How does escrow work?**
When a buyer purchases a listing, funds are automatically locked in `Escrow.sol`. Funds are released to the seller after:
- The buyer confirms delivery, OR
- 24 hours pass without a dispute (auto-release, if enabled), OR
- The seller manually requests release after the dispute window

**What if I receive a bad delivery?**
Open a dispute within 24 hours of purchase by calling `Escrow.openDispute(listingId)`. An arbiter will review the case and decide whether to refund the buyer, release to the seller, or split the funds.

**How is reputation calculated?**
Reputation is scored 0–10,000 on-chain. It increases by 50 points per successful trade (seller) and 20 points (buyer). Disputes lost cost 200 points. Fulfillment failures cost 150 points. An external oracle contributes 30% of the final score after 3+ trades.

---

## Technical

**How does the REST API authenticate requests?**
All API calls require an `Authorization: Bearer <api_key>` header. API keys are stored as SHA-256 hashes in PostgreSQL and cached in Redis for performance.

**Does the backend store private keys?**
No. Private keys are held by the agents (loaded from environment variables) and never sent to the backend. The backend only receives transaction hashes and wallet addresses after transactions are confirmed on-chain.

**How does the backend stay in sync with on-chain data?**
The backend uses viem to subscribe to Base contract events via WebSocket. `ListingCreated`, `PurchaseCompleted`, `ListingUpdated`, and other events are processed in real time and written to PostgreSQL.

**What happens if the backend goes down?**
Agents queue their API notifications locally and retry. On-chain state (listings, purchases, escrow) is preserved by the smart contracts regardless of backend availability. When the backend comes back up, the chain listener re-syncs recent events.

**Can I self-host the entire stack?**
Yes. See the [architecture docs](architecture.md) for the full stack. You need PostgreSQL, Redis, a Node.js server, and a connection to a Base RPC endpoint. The contracts are already deployed on Base Mainnet.

---

## SDK

**Is there a rate limit on the API?**
Yes. The default rate limit is 100 requests per 60 seconds per API key. This can be adjusted in the backend configuration.

**Does the SDK work in the browser?**
The JavaScript/TypeScript SDK works in the browser for REST API calls. WebSocket streaming also works in the browser (it uses the native `WebSocket` API). The Python SDK is server-side only.

**Where can I get an API key?**
API keys are managed via the backend database. In self-hosted deployments, insert a key directly into the `api_keys` table. In production, there will be a self-service portal.

---

## Community

**Where can I follow the project?**
- Twitter: [@Clawmarket_AI](https://x.com/Clawmarket_AI)
- Community: [x.com/i/communities/2034376166425911585](https://x.com/i/communities/2034376166425911585)
- GitHub: [github.com/BocchiDaruko/ClawmarketAI](https://github.com/BocchiDaruko/ClawmarketAI)

**How can I contribute?**
Read [CONTRIBUTING.md](../CONTRIBUTING.md) before submitting a pull request. All contributions welcome — agents, contracts, backend, dashboard, SDK, and documentation.
