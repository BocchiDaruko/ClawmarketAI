// src/db/migrate.js
// Run with: node src/db/migrate.js
import "dotenv/config";
import { db } from "./client.js";

const SCHEMA = `
-- ── Listings ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS listings (
  id              TEXT PRIMARY KEY,          -- on-chain listing ID
  seller          TEXT NOT NULL,             -- seller wallet address
  title           TEXT NOT NULL,
  description     TEXT,
  category        TEXT NOT NULL,
  good_kind       TEXT NOT NULL DEFAULT 'digital',
  price_usdc      NUMERIC(18,6) NOT NULL,
  metadata_uri    TEXT,
  available       BOOLEAN NOT NULL DEFAULT TRUE,
  on_chain        BOOLEAN NOT NULL DEFAULT TRUE,
  reputation_score NUMERIC(6,2)  DEFAULT 50.0,
  demand_count    INTEGER NOT NULL DEFAULT 0,
  listed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  sold_at         TIMESTAMPTZ,
  cancelled_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_listings_category  ON listings(category);
CREATE INDEX IF NOT EXISTS idx_listings_available ON listings(available);
CREATE INDEX IF NOT EXISTS idx_listings_seller    ON listings(seller);
CREATE INDEX IF NOT EXISTS idx_listings_price     ON listings(price_usdc);

-- ── Purchases ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS purchases (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_id      TEXT NOT NULL REFERENCES listings(id),
  buyer           TEXT NOT NULL,
  seller          TEXT NOT NULL,
  price_usdc      NUMERIC(18,6) NOT NULL,
  payment_token   TEXT NOT NULL DEFAULT 'usdc',
  tx_hash         TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',  -- pending|confirmed|failed
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  confirmed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_purchases_buyer      ON purchases(buyer);
CREATE INDEX IF NOT EXISTS idx_purchases_seller     ON purchases(seller);
CREATE INDEX IF NOT EXISTS idx_purchases_listing_id ON purchases(listing_id);

-- ── Fulfillments ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fulfillments (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_id      TEXT NOT NULL,
  purchase_id     UUID REFERENCES purchases(id),
  buyer           TEXT NOT NULL,
  seller          TEXT NOT NULL,
  good_kind       TEXT NOT NULL,
  delivery_payload JSONB,
  status          TEXT NOT NULL DEFAULT 'pending',  -- pending|delivered|failed
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  delivered_at    TIMESTAMPTZ
);

-- ── Market analytics (for gap detection + top sellers) ───────────────────────
CREATE TABLE IF NOT EXISTS market_analytics (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  category        TEXT NOT NULL,
  good_kind       TEXT NOT NULL,
  search_count    INTEGER NOT NULL DEFAULT 0,
  listing_count   INTEGER NOT NULL DEFAULT 0,
  avg_price_usdc  NUMERIC(18,6),
  total_volume    NUMERIC(18,6) NOT NULL DEFAULT 0,
  period_start    TIMESTAMPTZ NOT NULL,
  period_end      TIMESTAMPTZ NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analytics_category ON market_analytics(category);

-- ── Arbitrage positions ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS arbitrage_positions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id          TEXT NOT NULL,
  buy_listing_id    TEXT NOT NULL,
  buy_tx            TEXT,
  resell_listing_id TEXT,
  buy_price_usdc    NUMERIC(18,6) NOT NULL,
  resell_price_usdc NUMERIC(18,6) NOT NULL,
  expected_profit   NUMERIC(18,6) NOT NULL,
  actual_profit     NUMERIC(18,6),
  status            TEXT NOT NULL DEFAULT 'open',  -- open|sold|cancelled|failed
  opened_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  closed_at         TIMESTAMPTZ
);

-- ── API keys ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_keys (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key_hash        TEXT UNIQUE NOT NULL,
  agent_id        TEXT NOT NULL,
  wallet_address  TEXT,
  active          BOOLEAN NOT NULL DEFAULT TRUE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_used_at    TIMESTAMPTZ
);

-- ── Creator goods (handoff from Creator Agent) ────────────────────────────────
CREATE TABLE IF NOT EXISTS creator_goods (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id        TEXT NOT NULL,
  seller_wallet   TEXT NOT NULL,
  good_kind       TEXT NOT NULL,
  title           TEXT NOT NULL,
  description     TEXT,
  category        TEXT NOT NULL,
  metadata_uri    TEXT,
  base_price_usdc NUMERIC(18,6) NOT NULL,
  quality_score   NUMERIC(4,3),
  tags            TEXT[],
  listing_id      TEXT,          -- set after Seller Agent lists on-chain
  status          TEXT NOT NULL DEFAULT 'pending',  -- pending|listed|sold
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
`;

async function migrate() {
  console.log("Running migrations...");
  try {
    await db.query(SCHEMA);
    console.log("✓ Schema applied successfully");
  } catch (err) {
    console.error("Migration failed:", err);
    process.exit(1);
  } finally {
    await db.end();
  }
}

migrate();
