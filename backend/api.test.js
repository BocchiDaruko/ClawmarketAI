// tests/api.test.js
import request from "supertest";
import { jest } from "@jest/globals";

// ── Mock DB and Redis before importing app ────────────────────────────────────
jest.unstable_mockModule("../src/db/client.js", () => ({
  db: {
    query: jest.fn(),
    end:   jest.fn(),
    on:    jest.fn(),
  },
}));

jest.unstable_mockModule("../src/db/redis.js", () => ({
  redis:       { ping: jest.fn().mockResolvedValue("PONG"), on: jest.fn() },
  cacheGet:    jest.fn().mockResolvedValue(null),
  cacheSet:    jest.fn().mockResolvedValue(null),
  cacheDel:    jest.fn().mockResolvedValue(null),
  cacheIncrBy: jest.fn().mockResolvedValue(1),
}));

jest.unstable_mockModule("../src/chain/client.js", () => ({
  getReputationScore:  jest.fn().mockResolvedValue(75.0),
  isListingAvailable:  jest.fn().mockResolvedValue(true),
  publicClient:        { watchContractEvent: jest.fn() },
  httpClient:          { readContract: jest.fn() },
  CONTRACTS:           { marketplace: null, escrow: null, reputation: null },
  MARKETPLACE_ABI:     [],
  ESCROW_ABI:          [],
  REPUTATION_ABI:      [],
}));

jest.unstable_mockModule("../src/chain/listener.js", () => ({
  startChainListener: jest.fn().mockResolvedValue(undefined),
}));

jest.unstable_mockModule("../src/websocket/server.js", () => ({
  startWebSocketServer: jest.fn(),
  wsBroadcast:          jest.fn(),
}));

jest.unstable_mockModule("../src/middleware/auth.js", () => ({
  authenticate: (req, res, next) => {
    req.agent = { agent_id: "test-agent", wallet_address: "0xTEST" };
    next();
  },
}));

const { default: app } = await import("../src/index.js");
const { db }           = await import("../src/db/client.js");

// ── Helpers ───────────────────────────────────────────────────────────────────
const API = (path) => `/v1${path}`;
const AUTH = { Authorization: "Bearer test-key" };

function mockQuery(rows, count) {
  db.query.mockResolvedValue({ rows, rowCount: rows.length });
}

// ─── Health ───────────────────────────────────────────────────────────────────
describe("GET /health", () => {
  it("returns 200 when all services are up", async () => {
    db.query.mockResolvedValue({ rows: [{ "?column?": 1 }] });
    const res = await request(app).get("/health");
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("healthy");
  });
});

// ─── Listings ─────────────────────────────────────────────────────────────────
describe("GET /v1/listings", () => {
  it("returns listings array", async () => {
    const mockListings = [
      { id: "1", title: "GPU 1h", category: "compute", price_usdc: "10.00",
        available: true, seller: "0xABC" },
    ];
    db.query
      .mockResolvedValueOnce({ rows: mockListings })
      .mockResolvedValueOnce({ rows: [{ count: "1" }] });

    const res = await request(app).get(API("/listings")).set(AUTH);
    expect(res.status).toBe(200);
    expect(res.body.listings).toHaveLength(1);
    expect(res.body.listings[0].id).toBe("1");
  });

  it("filters by category", async () => {
    db.query
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ count: "0" }] });

    const res = await request(app)
      .get(API("/listings?category=compute"))
      .set(AUTH);
    expect(res.status).toBe(200);
    expect(res.body.listings).toHaveLength(0);
  });

  it("filters by availability", async () => {
    db.query
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ count: "0" }] });

    const res = await request(app)
      .get(API("/listings?available=false"))
      .set(AUTH);
    expect(res.status).toBe(200);
  });
});

describe("GET /v1/listings/:id", () => {
  it("returns 404 for unknown listing", async () => {
    db.query.mockResolvedValue({ rows: [] });
    const res = await request(app).get(API("/listings/999")).set(AUTH);
    expect(res.status).toBe(404);
  });

  it("returns listing and increments demand", async () => {
    const listing = { id: "42", title: "Test", category: "data",
                      price_usdc: "5.00", available: true };
    db.query.mockResolvedValue({ rows: [listing] });
    const res = await request(app).get(API("/listings/42")).set(AUTH);
    expect(res.status).toBe(200);
    expect(res.body.id).toBe("42");
  });
});

describe("POST /v1/listings", () => {
  it("creates a listing successfully", async () => {
    const newListing = {
      id: "100", seller: "0xABC", title: "Test Dataset",
      category: "data", price_usdc: "8.00", available: true,
    };
    db.query.mockResolvedValue({ rows: [newListing] });

    const res = await request(app)
      .post(API("/listings"))
      .set(AUTH)
      .send({
        seller: "0xABC123",
        title:  "Test Dataset",
        category: "data",
        price_usdc: 8.0,
        metadata_uri: "ipfs://QmTest",
      });
    expect(res.status).toBe(201);
  });

  it("rejects invalid listing (missing price)", async () => {
    const res = await request(app)
      .post(API("/listings"))
      .set(AUTH)
      .send({ seller: "0xABC", title: "No Price", category: "data" });
    expect(res.status).toBe(400);
  });

  it("rejects invalid category", async () => {
    const res = await request(app)
      .post(API("/listings"))
      .set(AUTH)
      .send({ seller: "0xABC", title: "Bad", category: "invalid", price_usdc: 5 });
    expect(res.status).toBe(400);
  });
});

describe("PATCH /v1/listings/:id", () => {
  it("updates price successfully", async () => {
    db.query.mockResolvedValue({ rows: [{ id: "1", price_usdc: "15.00" }] });
    const res = await request(app)
      .patch(API("/listings/1"))
      .set(AUTH)
      .send({ price_usdc: 15.0 });
    expect(res.status).toBe(200);
    expect(res.body.price_usdc).toBe("15.00");
  });

  it("rejects negative price", async () => {
    const res = await request(app)
      .patch(API("/listings/1"))
      .set(AUTH)
      .send({ price_usdc: -1 });
    expect(res.status).toBe(400);
  });
});

describe("DELETE /v1/listings/:id", () => {
  it("cancels a listing", async () => {
    db.query.mockResolvedValue({ rows: [] });
    const res = await request(app).delete(API("/listings/1")).set(AUTH);
    expect(res.status).toBe(204);
  });
});

// ─── Market ───────────────────────────────────────────────────────────────────
describe("GET /v1/market/gaps", () => {
  it("returns gaps array", async () => {
    db.query.mockResolvedValue({ rows: [] });
    const res = await request(app).get(API("/market/gaps")).set(AUTH);
    expect(res.status).toBe(200);
    expect(res.body.gaps).toBeDefined();
    expect(Array.isArray(res.body.gaps)).toBe(true);
  });

  it("includes synthetic gaps when DB is empty", async () => {
    db.query.mockResolvedValue({ rows: [] });
    const res = await request(app).get(API("/market/gaps")).set(AUTH);
    expect(res.body.gaps.length).toBeGreaterThan(0);
  });
});

describe("GET /v1/market/average-price", () => {
  it("returns average price for category", async () => {
    db.query.mockResolvedValue({
      rows: [{ average_price_usdc: "8.50", min_price_usdc: "5.00",
               max_price_usdc: "12.00", listing_count: "10" }]
    });
    const res = await request(app)
      .get(API("/market/average-price?category=compute"))
      .set(AUTH);
    expect(res.status).toBe(200);
    expect(res.body.average_price_usdc).toBe("8.50");
  });

  it("returns 400 without category param", async () => {
    const res = await request(app).get(API("/market/average-price")).set(AUTH);
    expect(res.status).toBe(400);
  });
});

describe("GET /v1/market/stats", () => {
  it("returns marketplace stats", async () => {
    db.query
      .mockResolvedValueOnce({ rows: [{ total: "100", active: "60" }] })
      .mockResolvedValueOnce({ rows: [{ total: "250" }] })
      .mockResolvedValueOnce({ rows: [{ total_volume: "5000.00" }] });
    const res = await request(app).get(API("/market/stats")).set(AUTH);
    expect(res.status).toBe(200);
    expect(res.body.total_listings).toBe(100);
    expect(res.body.active_listings).toBe(60);
  });
});

// ─── Purchases ────────────────────────────────────────────────────────────────
describe("POST /v1/purchases", () => {
  it("records a purchase", async () => {
    db.query
      .mockResolvedValueOnce({ rows: [{ seller: "0xSELLER" }] })  // listing lookup
      .mockResolvedValueOnce({ rows: [{ id: "uuid-1", listing_id: "1" }] }) // insert
      .mockResolvedValueOnce({ rows: [] }); // mark sold

    const res = await request(app)
      .post(API("/purchases"))
      .set(AUTH)
      .send({ listing_id: "1", buyer: "0xBUYER", price_usdc: 10.0, tx_hash: "0xTX" });
    expect(res.status).toBe(201);
  });

  it("rejects purchase without buyer address", async () => {
    const res = await request(app)
      .post(API("/purchases"))
      .set(AUTH)
      .send({ listing_id: "1", price_usdc: 10.0 });
    expect(res.status).toBe(400);
  });
});

// ─── Creator ──────────────────────────────────────────────────────────────────
describe("POST /v1/creator/goods", () => {
  it("registers a new good from Creator Agent", async () => {
    db.query
      .mockResolvedValueOnce({ rows: [{ id: "good-1" }] })
      .mockResolvedValueOnce({ rows: [] });

    const res = await request(app)
      .post(API("/creator/goods"))
      .set(AUTH)
      .send({
        agent_id:       "creator-001",
        seller_wallet:  "0xSELLER",
        good_kind:      "dataset",
        title:          "Crypto Price History",
        category:       "crypto-prices",
        metadata_uri:   "ipfs://QmTest123",
        base_price_usdc: 8.0,
        quality_score:  0.85,
        tags:           ["crypto", "prices"],
      });
    expect(res.status).toBe(201);
  });
});

// ─── Arbitrage ────────────────────────────────────────────────────────────────
describe("POST /v1/arbitrage/positions", () => {
  it("records an arbitrage position", async () => {
    db.query.mockResolvedValue({ rows: [{ id: "pos-1", status: "open" }] });
    const res = await request(app)
      .post(API("/arbitrage/positions"))
      .set(AUTH)
      .send({
        agent_id:          "arbitrage-001",
        buy_listing_id:    "42",
        resell_listing_id: "43",
        buy_price_usdc:    10.0,
        resell_price_usdc: 12.5,
        expected_profit:   2.3,
      });
    expect(res.status).toBe(201);
  });
});

describe("PATCH /v1/arbitrage/positions/:id", () => {
  it("updates position status to sold", async () => {
    db.query.mockResolvedValue({ rows: [{ id: "pos-1", status: "sold", actual_profit: 2.3 }] });
    const res = await request(app)
      .patch(API("/arbitrage/positions/pos-1"))
      .set(AUTH)
      .send({ status: "sold", actual_profit: 2.3 });
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("sold");
  });
});
