// src/routes/creator.js
import { Router } from "express";
import { z }      from "zod";
import { db }     from "../db/client.js";

const router = Router();

const GoodSchema = z.object({
  agent_id:       z.string(),
  seller_wallet:  z.string().startsWith("0x"),
  good_kind:      z.enum(["dataset", "api-wrapper"]),
  title:          z.string().min(3).max(200),
  description:    z.string().optional(),
  category:       z.string(),
  metadata_uri:   z.string().startsWith("ipfs://"),
  base_price_usdc:z.number().positive(),
  quality_score:  z.number().min(0).max(1).optional(),
  tags:           z.array(z.string()).optional(),
  extra:          z.record(z.any()).optional(),
});

// POST /v1/creator/goods — Creator Agent registers a new good
// This triggers the Seller Agent to list it on Marketplace.sol
router.post("/goods", async (req, res, next) => {
  try {
    const data = GoodSchema.parse(req.body);

    const { rows } = await db.query(
      `INSERT INTO creator_goods
         (agent_id, seller_wallet, good_kind, title, description, category,
          metadata_uri, base_price_usdc, quality_score, tags, status)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'pending')
       RETURNING *`,
      [data.agent_id, data.seller_wallet.toLowerCase(), data.good_kind,
       data.title, data.description || null, data.category,
       data.metadata_uri, data.base_price_usdc,
       data.quality_score || null, data.tags || []]
    );

    // Also create a listing entry so Seller Agent can pick it up
    await db.query(
      `INSERT INTO listings
         (id, seller, title, description, category, good_kind, price_usdc, metadata_uri, on_chain)
       VALUES (gen_random_uuid()::text, $1, $2, $3, $4, $5, $6, $7, false)`,
      [data.seller_wallet.toLowerCase(), data.title, data.description || null,
       data.category, data.good_kind, data.base_price_usdc, data.metadata_uri]
    );

    res.status(201).json({ listing_id: rows[0].id, ...rows[0] });
  } catch (err) {
    if (err instanceof z.ZodError) return res.status(400).json({ error: err.errors });
    next(err);
  }
});

// GET /v1/creator/goods — list goods created by an agent
router.get("/goods", async (req, res, next) => {
  try {
    const { agent_id, status, limit = "50" } = req.query;
    const conds  = [];
    const params = [];
    let   idx    = 1;
    if (agent_id) { conds.push(`agent_id = $${idx++}`); params.push(agent_id); }
    if (status)   { conds.push(`status = $${idx++}`);   params.push(status); }
    const where = conds.length ? `WHERE ${conds.join(" AND ")}` : "";
    const { rows } = await db.query(
      `SELECT * FROM creator_goods ${where} ORDER BY created_at DESC LIMIT $${idx}`,
      [...params, parseInt(limit)]
    );
    res.json({ goods: rows });
  } catch (err) { next(err); }
});

export default router;
