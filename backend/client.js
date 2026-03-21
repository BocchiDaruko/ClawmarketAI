// src/chain/client.js
import { createPublicClient, createWalletClient, webSocket, http, parseAbi } from "viem";
import { base } from "viem/chains";

// ── Public client (read + event listening) ────────────────────────────────────
export const publicClient = createPublicClient({
  chain:     base,
  transport: webSocket(process.env.BASE_WS_URL || "wss://mainnet.base.org"),
});

// ── HTTP client (fallback for reads) ─────────────────────────────────────────
export const httpClient = createPublicClient({
  chain:     base,
  transport: http(process.env.BASE_RPC_URL || "https://mainnet.base.org"),
});

// ── ABIs (minimal — only events/views the API needs) ─────────────────────────
export const MARKETPLACE_ABI = parseAbi([
  "event ListingCreated(uint256 indexed listingId, address indexed seller, uint256 priceUsdc, string category, string metadataUri)",
  "event PurchaseCompleted(uint256 indexed listingId, address indexed buyer, address indexed seller, uint256 priceUsdc, address paymentToken, uint256 paymentAmount, uint256 fee)",
  "event ListingCancelled(uint256 indexed listingId, address seller)",
  "event ListingUpdated(uint256 indexed listingId, uint256 newPrice)",
  "function isAvailable(uint256 listingId) view returns (bool)",
  "function getActiveListing(uint256 listingId) view returns (address seller, uint256 priceUsdc, string category, string metadataUri, bool available)",
]);

export const REPUTATION_ABI = parseAbi([
  "function getScore(address account) view returns (uint256)",
  "function getScoreDetails(address account) view returns (uint256 composite, uint256 internalScore, uint256 oracleScore, uint256 tradeCount, uint256 disputesLost, uint256 lastUpdated)",
]);

export const ESCROW_ABI = parseAbi([
  "function isHeld(uint256 listingId) view returns (bool)",
  "event Released(uint256 indexed listingId, address seller, uint256 net, uint256 fee)",
  "event DisputeOpened(uint256 indexed listingId, address buyer)",
  "event DisputeResolved(uint256 indexed listingId, address winner, uint256 amount)",
]);

// ── Contract address helpers ──────────────────────────────────────────────────
export const CONTRACTS = {
  marketplace:  process.env.MARKETPLACE_ADDRESS,
  escrow:       process.env.ESCROW_ADDRESS,
  reputation:   process.env.REPUTATION_ADDRESS,
  claw:         process.env.CLAW_ADDRESS,
  clawx:        process.env.CLAWX_ADDRESS,
  usdc:         process.env.USDC_ADDRESS,
};

// ── Convenience read functions ────────────────────────────────────────────────

export async function getReputationScore(address) {
  try {
    const score = await httpClient.readContract({
      address: CONTRACTS.reputation,
      abi:     REPUTATION_ABI,
      functionName: "getScore",
      args:    [address],
    });
    return Number(score) / 100; // contract returns score * 100
  } catch {
    return 50.0; // default neutral score
  }
}

export async function isListingAvailable(listingId) {
  try {
    return await httpClient.readContract({
      address: CONTRACTS.marketplace,
      abi:     MARKETPLACE_ABI,
      functionName: "isAvailable",
      args:    [BigInt(listingId)],
    });
  } catch {
    return false;
  }
}
