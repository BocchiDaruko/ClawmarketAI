// src/routes/listings.js
import { Router }   from "express";
import { z }        from "zod";
import { db }       from "../db/client.js";
import { cacheGet, cacheSet, cacheDel, cacheIncrBy } from "../db/redis.js";
import { getReputationScore } from "../chain/client.js";

const router = Router();

// ── Validation schemas ────────────────────────────────────────────────────────
const CreateListingSchema = z.object({
  seller:       z.string().startsWith("0x"),
  title:        z.string().min(3).max(200),
  description:  z.string().optional(),
  category:     z.enum(["compute", "data", "ai-service", "api-access", "digital"]),
  good_kind:    z.enum(["dataset", "api-wrapper", "compute", "digital"]).optional(),
  price_usdc:   z.number().positive(),
  metadata_uri: z.string().startsWith("ipfs://").optional(),
});

const UpdatePriceSchema = z.object({
  price_usdc: z.number().positive(),
});

// ── GET /v1/listings ──────────────────────────────────────────────────────────
// Agents use: GET /listings?available=true&category=compute&limit=50
router.get("/", async (req, res, next) => {
  try {
    const {
      available = "true",
      category,
      seller,
      limit = "100",
      offset = "0",
      sort = "listed_at",
      order = "desc",
    } = req.query;

    const cacheKey = `listings:${JSON.stringify(req.query)}`;
    const cached   = await cacheGet(cacheKey);
    if (cached) return res.json(cached);

    const conditions = [];
    const params     = [];
    let   idx        = 1;

    if (available !== "all") {
      conditions.push(`available = $${idx++}`);
      params.push(available === "true");
    }
    if (category) {
      const cats = category.split(",");
      conditions.push(`category = ANY($${idx++})`);
      params.push(cats);
    }
    if (seller) {
      conditions.push(`seller = $${idx++}`);
      params.push(seller.toLowerCase());
    }

    const where    = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
    const sortCol  = ["price_usdc", "listed_at", "reputation_score", "demand_count"]
                       .includes(sort) ? sort : "listed_at";
    const sortDir  = order === "asc" ? "ASC" : "DESC";
    const limitVal = Math.min(parseInt(limit), 500);

    const { rows } = await db.query(
      `SELECT * FROM listings ${where}
       ORDER BY ${sortCol} ${sortDir}
       LIMIT $${idx++} OFFSET $${idx++}`,
      [...params, limitVal, parseInt(offset)]
    );

    const countRes = await db.query(
      `SELECT COUNT(*) FROM listings ${where}`, params
    );

    const result = { listings: rows, total: parseInt(countRes.rows[0].count) };
    await cacheSet(cacheKey, result, 10);  // 10s cache for listing queries
    res.json(result);
  } catch (err) { next(err); }
});

// ── GET /v1/listings/:id ──────────────────────────────────────────────────────
router.get("/:id", async (req, res, next) => {
  try {
    const cacheKey = `listing:${req.params.id}`;
    const cached   = await cacheGet(cacheKey);
    if (cached) return res.json(cached);

    const { rows } = await db.query(
      `SELECT * FROM listings WHERE id = $1`, [req.params.id]
    );
    if (!rows.length) return res.status(404).json({ error: "Listing not found" });

    // Increment demand counter (used by Seller Agent's demand-based pricing)
    await cacheIncrBy(`demand:${req.params.id}`, 1, 3600);
    await db.query(
      `UPDATE listings SET demand_count = demand_count + 1 WHERE id = $1`, [req.params.id]
    );

    await cacheSet(cacheKey, rows[0], 15);
    res.json(rows[0]);
  } catch (err) { next(err); }
});

// ── POST /v1/listings ─────────────────────────────────────────────────────────
// Called by Seller Agent and Creator Agent handoff
router.post("/", async (req, res, next) => {
  try {
    const data = CreateListingSchema.parse(req.body);

    // Fetch on-chain reputation score for the seller
    const repScore = await getReputationScore(data.seller);

    const { rows } = await db.query(
      `INSERT INTO listings
         (id, seller, title, description, category, good_kind,
          price_usdc, metadata_uri, reputation_score, on_chain)
       VALUES (
         COALESCE($1, gen_random_uuid()::text),
         $2, $3, $4, $5, $6, $7, $8, $9, $10
       )
       RETURNING *`,
      [
        req.body.id || null,
        data.seller.toLowerCase(),
        data.title,
        data.description || null,
        data.category,
        data.good_kind   || "digital",
        data.price_usdc,
        data.metadata_uri || null,
        repScore,
        req.body.on_chain !== false,
      ]
    );

    await cacheDel(`listings:*`);  // invalidate list cache
    res.status(201).json(rows[0]);
  } catch (err) {
    if (err instanceof z.ZodError) return res.status(400).json({ error: err.errors });
    next(err);
  }
});

// ── PATCH /v1/listings/:id ────────────────────────────────────────────────────
// Seller Agent calls this to update price
router.patch("/:id", async (req, res, next) => {
  try {
    const { price_usdc } = UpdatePriceSchema.parse(req.body);
    const { rows } = await db.query(
      `UPDATE listings
       SET price_usdc = $1, updated_at = NOW()
       WHERE id = $2 AND available = true
       RETURNING *`,
      [price_usdc, req.params.id]
    );
    if (!rows.length) return res.status(404).json({ error: "Listing not found or not available" });
    await cacheDel(`listing:${req.params.id}`);
    res.json(rows[0]);
  } catch (err) {
    if (err instanceof z.ZodError) return res.status(400).json({ error: err.errors });
    next(err);
  }
});

// ── DELETE /v1/listings/:id ───────────────────────────────────────────────────
// Seller Agent calls this to cancel a listing
router.delete("/:id", async (req, res, next) => {
  try {
    await db.query(
      `UPDATE listings SET available = false, cancelled_at = NOW() WHERE id = $1`,
      [req.params.id]
    );
    await cacheDel(`listing:${req.params.id}`);
    res.status(204).send();
  } catch (err) { next(err); }
});

export default router;
