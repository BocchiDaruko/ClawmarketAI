// src/routes/fulfillment.js
import { Router } from "express";
import { z }      from "zod";
import { db }     from "../db/client.js";
import { wsBroadcast } from "../websocket/server.js";

const router = Router();

// POST /v1/fulfillment — Seller Agent calls this after Escrow.release()
router.post("/", async (req, res, next) => {
  try {
    const { listing_id, buyer, seller, good_kind, delivery_config } = req.body;

    // Build delivery payload based on good_kind
    const delivery_payload = buildDelivery(good_kind, delivery_config);

    const { rows } = await db.query(
      `INSERT INTO fulfillments (listing_id, buyer, seller, good_kind, delivery_payload, status, delivered_at)
       VALUES ($1, $2, $3, $4, $5, 'delivered', NOW())
       RETURNING *`,
      [listing_id, buyer, seller, good_kind, JSON.stringify(delivery_payload)]
    );

    // Notify buyer via WebSocket
    wsBroadcast({ type: "fulfillment:delivered", listing_id, buyer, good_kind });

    res.status(201).json({ ...rows[0], delivery_payload });
  } catch (err) { next(err); }
});

function buildDelivery(goodKind, config = {}) {
  const base = { delivered_at: new Date().toISOString(), access_key: generateKey() };
  if (goodKind === "api-wrapper") return { ...base, ...config, endpoint: config.endpoint };
  if (goodKind === "dataset")     return { ...base, download_url: config.s3_bucket
    ? `https://${config.s3_bucket}.s3.amazonaws.com/${config.key}` : config.ipfs_uri };
  if (goodKind === "ai-service")  return { ...base, api_key: generateKey(), quota: config.quota_tokens };
  return { ...base, ...config };
}

function generateKey() {
  return "claw_" + Math.random().toString(36).slice(2, 18);
}

export default router;
