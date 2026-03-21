// src/chain/listener.js
import { publicClient, MARKETPLACE_ABI, ESCROW_ABI, CONTRACTS } from "./client.js";
import { db }     from "../db/client.js";
import { wsBroadcast } from "../websocket/server.js";

/**
 * Subscribes to Marketplace and Escrow events on Base.
 * Updates the local DB on every event and broadcasts to WebSocket clients.
 */
export async function startChainListener() {
  if (!CONTRACTS.marketplace) {
    console.warn("MARKETPLACE_ADDRESS not set — chain listener inactive");
    return;
  }

  // ── ListingCreated ────────────────────────────────────────────────────────
  publicClient.watchContractEvent({
    address:   CONTRACTS.marketplace,
    abi:       MARKETPLACE_ABI,
    eventName: "ListingCreated",
    onLogs: async (logs) => {
      for (const log of logs) {
        const { listingId, seller, priceUsdc, category, metadataUri } = log.args;
        try {
          await db.query(
            `INSERT INTO listings (id, seller, title, category, price_usdc, metadata_uri, on_chain, listed_at)
             VALUES ($1, $2, $3, $4, $5, $6, true, NOW())
             ON CONFLICT (id) DO UPDATE
               SET price_usdc = EXCLUDED.price_usdc, available = true`,
            [listingId.toString(), seller, `Listing #${listingId}`, category,
             Number(priceUsdc) / 1e6, metadataUri]
          );
          wsBroadcast({ type: "listing:created", listingId: listingId.toString(), seller, category });
          console.log(`[chain] ListingCreated: #${listingId} by ${seller}`);
        } catch (err) {
          console.error("[chain] ListingCreated DB error:", err.message);
        }
      }
    },
    onError: (err) => console.error("[chain] ListingCreated watch error:", err.message),
  });

  // ── PurchaseCompleted ─────────────────────────────────────────────────────
  publicClient.watchContractEvent({
    address:   CONTRACTS.marketplace,
    abi:       MARKETPLACE_ABI,
    eventName: "PurchaseCompleted",
    onLogs: async (logs) => {
      for (const log of logs) {
        const { listingId, buyer, seller, priceUsdc, paymentToken, paymentAmount, fee } = log.args;
        const lid = listingId.toString();
        try {
          // Mark listing as sold
          await db.query(
            `UPDATE listings SET available = false, sold_at = NOW() WHERE id = $1`,
            [lid]
          );
          // Record purchase
          await db.query(
            `INSERT INTO purchases (listing_id, buyer, seller, price_usdc, payment_token, tx_hash, status, confirmed_at)
             VALUES ($1, $2, $3, $4, $5, $6, 'confirmed', NOW())
             ON CONFLICT DO NOTHING`,
            [lid, buyer, seller, Number(priceUsdc) / 1e6, paymentToken, log.transactionHash]
          );
          // Update market analytics
          await db.query(
            `INSERT INTO market_analytics (category, good_kind, total_volume, period_start, period_end)
             SELECT category, good_kind, $1::numeric, date_trunc('hour', NOW()), date_trunc('hour', NOW()) + interval '1 hour'
             FROM listings WHERE id = $2
             ON CONFLICT DO NOTHING`,
            [Number(priceUsdc) / 1e6, lid]
          );

          wsBroadcast({ type: "purchase:completed", listingId: lid, buyer, seller,
                        priceUsdc: Number(priceUsdc) / 1e6 });
          console.log(`[chain] PurchaseCompleted: #${lid} buyer=${buyer}`);
        } catch (err) {
          console.error("[chain] PurchaseCompleted DB error:", err.message);
        }
      }
    },
    onError: (err) => console.error("[chain] PurchaseCompleted watch error:", err.message),
  });

  // ── ListingUpdated (price change) ─────────────────────────────────────────
  publicClient.watchContractEvent({
    address:   CONTRACTS.marketplace,
    abi:       MARKETPLACE_ABI,
    eventName: "ListingUpdated",
    onLogs: async (logs) => {
      for (const log of logs) {
        const { listingId, newPrice } = log.args;
        try {
          await db.query(
            `UPDATE listings SET price_usdc = $1, updated_at = NOW() WHERE id = $2`,
            [Number(newPrice) / 1e6, listingId.toString()]
          );
          wsBroadcast({ type: "listing:repriced", listingId: listingId.toString(),
                        newPrice: Number(newPrice) / 1e6 });
        } catch (err) {
          console.error("[chain] ListingUpdated DB error:", err.message);
        }
      }
    },
    onError: (err) => console.error("[chain] ListingUpdated watch error:", err.message),
  });

  // ── ListingCancelled ──────────────────────────────────────────────────────
  publicClient.watchContractEvent({
    address:   CONTRACTS.marketplace,
    abi:       MARKETPLACE_ABI,
    eventName: "ListingCancelled",
    onLogs: async (logs) => {
      for (const log of logs) {
        const { listingId } = log.args;
        try {
          await db.query(
            `UPDATE listings SET available = false, cancelled_at = NOW() WHERE id = $1`,
            [listingId.toString()]
          );
          wsBroadcast({ type: "listing:cancelled", listingId: listingId.toString() });
        } catch (err) {
          console.error("[chain] ListingCancelled DB error:", err.message);
        }
      }
    },
    onError: (err) => console.error("[chain] ListingCancelled watch error:", err.message),
  });

  // ── Escrow Released ───────────────────────────────────────────────────────
  publicClient.watchContractEvent({
    address:   CONTRACTS.escrow,
    abi:       ESCROW_ABI,
    eventName: "Released",
    onLogs: async (logs) => {
      for (const log of logs) {
        const { listingId, seller, net } = log.args;
        wsBroadcast({ type: "escrow:released", listingId: listingId.toString(),
                      seller, net: Number(net) / 1e6 });
        console.log(`[chain] Escrow released: #${listingId} → ${seller}`);
      }
    },
    onError: (err) => console.error("[chain] Released watch error:", err.message),
  });

  console.log("[chain] Listening to Base events on:", CONTRACTS.marketplace);
}
