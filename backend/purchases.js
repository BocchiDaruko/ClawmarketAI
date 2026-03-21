// src/routes/purchases.js
import { Router } from "express";
import { z }      from "zod";
import { db }     from "../db/client.js";

const router = Router();

const PurchaseSchema = z.object({
  listing_id:    z.string(),
  buyer:         z.string().startsWith("0x"),
  tx_hash:       z.string().optional(),
  price_usdc:    z.number().positive(),
  payment_token: z.enum(["usdc", "claw", "clawx"]).optional(),
});

// POST /v1/purchases — called by Buyer Agent after on-chain confirmation
router.post("/", async (req, res, next) => {
  try {
    const data = PurchaseSchema.parse(req.body);

    // Get seller from listing
    const { rows: listingRows } = await db.query(
      `SELECT seller FROM listings WHERE id = $1`, [data.listing_id]
    );
    if (!listingRows.length) return res.status(404).json({ error: "Listing not found" });

    const { rows } = await db.query(
      `INSERT INTO purchases (listing_id, buyer, seller, price_usdc, payment_token, tx_hash, status, confirmed_at)
       VALUES ($1, $2, $3, $4, $5, $6, 'confirmed', NOW())
       ON CONFLICT DO NOTHING
       RETURNING *`,
      [data.listing_id, data.buyer.toLowerCase(), listingRows[0].seller,
       data.price_usdc, data.payment_token || "usdc", data.tx_hash || null]
    );

    // Mark listing as sold
    await db.query(
      `UPDATE listings SET available = false, sold_at = NOW() WHERE id = $1`, [data.listing_id]
    );

    res.status(201).json(rows[0] || { message: "Purchase already recorded" });
  } catch (err) {
    if (err instanceof z.ZodError) return res.status(400).json({ error: err.errors });
    next(err);
  }
});

// GET /v1/purchases?buyer=0x... or ?seller=0x...
router.get("/", async (req, res, next) => {
  try {
    const { buyer, seller, limit = "50" } = req.query;
    const conditions = [];
    const params     = [];
    let   idx        = 1;
    if (buyer)  { conditions.push(`buyer = $${idx++}`);  params.push(buyer.toLowerCase()); }
    if (seller) { conditions.push(`seller = $${idx++}`); params.push(seller.toLowerCase()); }
    const where = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
    const { rows } = await db.query(
      `SELECT * FROM purchases ${where} ORDER BY created_at DESC LIMIT $${idx}`,
      [...params, parseInt(limit)]
    );
    res.json({ purchases: rows });
  } catch (err) { next(err); }
});

export default router;
