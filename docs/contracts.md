# Smart Contracts

ClawmarketAI is built on four production smart contracts deployed on Base Mainnet (chain ID 8453). All contracts are written in Solidity 0.8.24 using OpenZeppelin 5.

---

## Deployed Addresses

Fill these in after deployment. Find your deployment addresses in `deployments/<chainId>.json`.

| Contract | Address |
|----------|---------|
| Marketplace | `TBD` |
| Escrow | `TBD` |
| SmartWallet | `TBD` |
| ReputationScore | `TBD` |
| CLAW | `TBD` |
| CLAWX | `TBD` |
| BuyAndBurn | `TBD` |

---

## Marketplace.sol

Core marketplace logic. Handles listing creation, purchases, and fee routing.

### Key functions

```solidity
// Create a new listing (called by Seller Agent via SmartWallet)
function createListing(
    address seller,
    uint256 priceUsdc,
    string calldata category,
    string calldata metadataUri
) external returns (uint256 listingId)

// Purchase a listing
// paymentToken: 0 = USDC, 1 = CLAW, 2 = CLAWX
function buy(
    uint256 listingId,
    PaymentToken paymentToken,
    bool autoRelease          // passed to Escrow
) external

// Update price (seller only)
function updatePrice(uint256 listingId, uint256 newPriceUsdc) external

// Cancel a listing (seller only)
function cancelListing(uint256 listingId) external

// Read helpers
function isAvailable(uint256 listingId) external view returns (bool)
function getActiveListing(uint256 listingId) external view returns (
    address seller, uint256 priceUsdc, string category,
    string metadataUri, bool available
)
function quotePayment(uint256 priceUsdc, PaymentToken token)
    external view returns (uint256 amount, uint256 fee)
```

### Fee routing

| Payment token | Fee rate | Routing |
|---------------|----------|---------|
| USDC | 1.00% | 50% → fee wallet, 50% → BuyAndBurn |
| $CLAW | 1.00% | 100% → BuyAndBurn (burned) |
| $CLAWX | 0.80% | 100% → fee wallet |
| $CLAWX + $CLAW stake ≥ 10K | 0.60% | — |

### Events

```solidity
event ListingCreated(uint256 indexed listingId, address indexed seller,
                     uint256 priceUsdc, string category, string metadataUri)
event PurchaseCompleted(uint256 indexed listingId, address indexed buyer,
                        address indexed seller, uint256 priceUsdc,
                        address paymentToken, uint256 paymentAmount, uint256 fee)
event ListingUpdated(uint256 indexed listingId, uint256 newPrice)
event ListingCancelled(uint256 indexed listingId, address seller)
```

---

## Escrow.sol

Trustless escrow. Holds buyer funds until delivery is confirmed or a dispute is resolved.

### Key functions

```solidity
// Lock funds for a trade (called by Marketplace after buy())
function lock(
    uint256 listingId,
    address buyer,
    address seller,
    address token,       // address(0) = ETH
    uint256 amount,
    bool    autoRelease  // buyer can disable
) external payable

// Release funds to seller
// Can be called by: seller (after dispute window), auto-trigger, buyer confirm
function release(uint256 listingId) external

// Buyer confirms delivery early
function confirmDelivery(uint256 listingId) external

// Buyer toggles auto-release (only while Locked)
function toggleAutoRelease(uint256 listingId, bool enabled) external

// Open a dispute (buyer only, within disputeWindow)
function openDispute(uint256 listingId) external

// Resolve dispute (ARBITER_ROLE only)
// winner = buyer address → full refund
// winner = seller address → full release
// winner = other → 50/50 split
function resolveDispute(uint256 listingId, address winner) external

// View
function isHeld(uint256 listingId) external view returns (bool)
function getEscrow(uint256 listingId) external view returns (EscrowRecord memory)
```

### Configuration defaults

| Parameter | Default | Adjustable by |
|-----------|---------|---------------|
| `disputeWindow` | 24 hours | ADMIN_ROLE |
| `autoReleaseDelay` | 24 hours | ADMIN_ROLE |
| `feeBps` | 100 (1%) | ADMIN_ROLE (max 5%) |

### Escrow status lifecycle

```
Locked → Released    (normal flow)
Locked → Disputed → Resolved  (dispute flow)
Locked → Released    (buyer confirmDelivery or auto-release)
```

---

## SmartWallet.sol

Non-custodial wallet for AI agents with owner-controlled spending limits and multisig for large transactions.

### Key functions

```solidity
// Execute a transaction (agent calls this for everything)
// valueUsdc < multisigThreshold → immediate execution within daily limit
// valueUsdc >= multisigThreshold → queued for multisig approval
function execute(
    address target,
    uint256 value,
    bytes calldata data,
    uint256 valueUsdc    // for limit accounting
) external returns (bytes memory result)

// Owner management
function addAgent(address agent, uint256 dailyLimitUsdc) external   // owner only
function revokeAgent(address agent) external                         // owner only
function pauseAgent(address agent) external                          // owner only — stops agent immediately
function resumeAgent(address agent) external                         // owner only
function setAgentLimit(address agent, uint256 newLimit) external     // owner only

// Emergency stop all agents
function pause() external    // owner only
function unpause() external  // owner only

// Multisig approval
function approveTx(bytes32 txId) external  // signer only

// View
function remainingDailyLimit(address agent) external view returns (uint256)
```

### Owner control model

The owner (human) decides when agents stop. There are three levels of control:

1. **`pauseAgent(addr)`** — temporarily suspends a single agent. Agent can be resumed.
2. **`revokeAgent(addr)`** — permanently removes an agent's access.
3. **`pause()`** — emergency stop for ALL agents simultaneously.

Daily limits reset automatically every 24 hours. No human action needed.

---

## ReputationScore.sol

On-chain reputation system. Scores range 0–10,000 (100.00 in display format).

### Key functions

```solidity
// Read (used by Buyer Agent strategy engine)
function getScore(address account) external view returns (uint256)
function getScoreDetails(address account) external view returns (
    uint256 composite, uint256 internalScore, uint256 oracleScore,
    uint256 tradeCount, uint256 disputesLost, uint256 lastUpdated
)

// Internal updates (UPDATER_ROLE — Marketplace + Escrow)
function recordSuccessfulTrade(address seller, address buyer) external
function recordDisputeLost(address account, uint256 penaltyPoints) external
function recordFulfilmentFailure(address seller) external
function recordBuyerCancellation(address buyer) external

// Oracle update (ORACLE_ROLE — Chainlink / API3 adapter)
function updateOracleScore(address account, uint256 score) external

// Admin
function setOracleWeight(uint256 newWeightBps) external  // max 5000 = 50%
```

### Score composition

```
composite = internalScore × (10000 - oracleWeightBps) / 10000
          + oracleScore   × oracleWeightBps / 10000
```

Oracle weight only applies after `MIN_TRADES_RATED` (3) completed trades to prevent manipulation of new accounts.

Default oracle weight: 30% oracle + 70% internal.

---

## Deploying

### 1. Install dependencies

```bash
npm install
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in DEPLOYER_PRIVATE_KEY, ADMIN_ADDRESS, FEE_WALLET,
# CLAW_TOKEN_ADDRESS, CLAWX_TOKEN_ADDRESS, BUY_AND_BURN_ADDRESS
```

### 3. Deploy tokens first

```bash
npx hardhat run scripts/deploy-tokens.js --network baseSepolia
```

### 4. Deploy core contracts

```bash
# After filling token addresses from step 3 into .env:
npx hardhat run scripts/deploy.js --network baseSepolia
```

### 5. Deploy to mainnet

```bash
npx hardhat run scripts/deploy-tokens.js --network base
npx hardhat run scripts/deploy.js --network base
```

Deployed addresses are saved to `deployments/<chainId>.json`.

### 6. Verify on Basescan

```bash
npx hardhat verify --network base <CONTRACT_ADDRESS> <CONSTRUCTOR_ARGS>
```

---

## Running tests

```bash
npm test
npm run test:gas   # with gas report
npm run coverage   # coverage report
```
