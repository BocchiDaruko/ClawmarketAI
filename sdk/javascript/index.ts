/**
 * clawmarketAI JavaScript / TypeScript SDK
 * Interact with the marketplace, deploy agents, and manage smart wallets.
 */

import { createPublicClient, createWalletClient, http, parseAbi } from "viem";

// ─── Types ───────────────────────────────────────────────────────────────────

export type AgentType = "buyer" | "seller" | "creator" | "arbitrage";
export type Strategy = "lowest-price" | "best-reputation" | "balanced";

export interface AgentConfig {
  agentId: string;
  type: AgentType;
  walletAddress: `0x${string}`;
  budgetWei: bigint;
  strategy: Strategy;
  categories: string[];
  reinvestRatio: number;
  riskTolerance: "low" | "medium" | "high";
}

export interface Listing {
  id: bigint;
  seller: `0x${string}`;
  category: string;
  metadataURI: string;
  price: bigint;
  active: boolean;
}

// ─── Marketplace ABI (abbreviated) ───────────────────────────────────────────

const MARKETPLACE_ABI = parseAbi([
  "function list(string category, string metadataURI, uint256 price) returns (uint256)",
  "function purchase(uint256 listingId) payable",
  "function delist(uint256 listingId)",
  "function listings(uint256 id) view returns (uint256, address, string, string, uint256, bool)",
  "function listingCount() view returns (uint256)",
  "event Listed(uint256 indexed id, address indexed seller, uint256 price)",
  "event Purchased(uint256 indexed id, address indexed buyer, address indexed seller, uint256 price)",
]);

// ─── ClawMarket SDK ──────────────────────────────────────────────────────────

export class ClawMarketSDK {
  private publicClient;
  private walletClient;
  private marketplaceAddress: `0x${string}`;

  constructor(rpcUrl: string, marketplaceAddress: `0x${string}`) {
    this.marketplaceAddress = marketplaceAddress;
    this.publicClient = createPublicClient({ transport: http(rpcUrl) });
    this.walletClient = createWalletClient({ transport: http(rpcUrl) });
  }

  /** Fetch a listing by ID */
  async getListing(id: bigint): Promise<Listing> {
    const result = await this.publicClient.readContract({
      address: this.marketplaceAddress,
      abi: MARKETPLACE_ABI,
      functionName: "listings",
      args: [id],
    }) as [bigint, `0x${string}`, string, string, bigint, boolean];

    return {
      id: result[0],
      seller: result[1],
      category: result[2],
      metadataURI: result[3],
      price: result[4],
      active: result[5],
    };
  }

  /** Get total number of listings */
  async getListingCount(): Promise<bigint> {
    return await this.publicClient.readContract({
      address: this.marketplaceAddress,
      abi: MARKETPLACE_ABI,
      functionName: "listingCount",
    }) as bigint;
  }

  /** Get all active listings */
  async getAllListings(): Promise<Listing[]> {
    const count = await this.getListingCount();
    const listings: Listing[] = [];

    for (let i = 1n; i <= count; i++) {
      const listing = await this.getListing(i);
      if (listing.active) listings.push(listing);
    }

    return listings;
  }

  /** Filter listings by category */
  async getListingsByCategory(category: string): Promise<Listing[]> {
    const all = await this.getAllListings();
    return all.filter((l) => l.category === category);
  }

  /** Subscribe to new listings via event polling */
  watchListings(onListing: (listing: { id: bigint; seller: string; price: bigint }) => void) {
    return this.publicClient.watchContractEvent({
      address: this.marketplaceAddress,
      abi: MARKETPLACE_ABI,
      eventName: "Listed",
      onLogs: (logs) => {
        for (const log of logs) {
          const { id, seller, price } = log.args as any;
          onListing({ id, seller, price });
        }
      },
    });
  }
}

// ─── Agent Factory ────────────────────────────────────────────────────────────

export function createAgentConfig(overrides: Partial<AgentConfig> & Pick<AgentConfig, "agentId" | "walletAddress">): AgentConfig {
  return {
    type: "buyer",
    budgetWei: BigInt("100000000000000000"), // 0.1 ETH
    strategy: "balanced",
    categories: ["compute", "data", "api-access"],
    reinvestRatio: 0.75,
    riskTolerance: "low",
    ...overrides,
  };
}
