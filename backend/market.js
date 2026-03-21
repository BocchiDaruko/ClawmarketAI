// src/routes/market.js
import { Router } from "express";
import { db }     from "../db/client.js";
import { cacheGet, cacheSet } from "../db/redis.js";

const router = Router();

// ── GET /v1/market/gaps ───────────────────────────────────────────────────────
// Creator Agent uses this to find under-supplied categories
router.get("/gaps", async (req, res, next) => {
  try {
    const { kinds = "dataset,api-wrapper", limit = "10" } = req.query;
    const cacheKey = `market:gaps:${kinds}`;
    const cached   = await cacheGet(cacheKey);
    if (cached) return res.json(cached);

    // Categories with high demand (view count) but few active listings
    const { rows } = await db.query(`
      WITH demand AS (
        SELECT
          category,
          good_kind,
          SUM(demand_count) AS search_volume,
          COUNT(*)          AS listing_count,
          AVG(price_usdc)   AS avg_price_usdc
        FROM listings
        WHERE available = true
          AND good_kind = ANY($1)
        GROUP BY category, good_kind
      )
      SELECT
        category,
        good_kind,
        COALESCE(search_volume, 0)::int AS search_volume,
        COALESCE(listing_count, 0)::int AS listing_count,
        ROUND(COALESCE(avg_price_usdc, 0)::numeric, 4) AS avg_price_usdc,
        ROUND(
          CASE
            WHEN COALESCE(listing_count, 0) = 0 THEN 1.0
            ELSE LEAST(search_volume::numeric / (listing_count * 10), 1.0)
          END, 4
        ) AS opportunity_score
      FROM demand
      ORDER BY opportunity_score DESC, search_volume DESC
      LIMIT $2
    `, [kinds.split(","), parseInt(limit)]);

    // Add synthetic gaps for categories with zero listings but known demand
    const knownCategories = [
      { category: "crypto-prices",    kind: "dataset",     score: 0.92 },
      { category: "weather-history",  kind: "dataset",     score: 0.85 },
      { category: "fx-rates",         kind: "api-wrapper", score: 0.88 },
      { category: "country-data",     kind: "api-wrapper", score: 0.78 },
      { category: "llm-training",     kind: "dataset",     score: 0.80 },
    ];

    const existingCats = new Set(rows.map(r => r.category));
    const synthetic    = knownCategories
      .filter(c => !existingCats.has(c.category))
      .map(c => ({
        category:          c.category,
        good_kind:         c.kind,
        search_volume:     0,
        listing_count:     0,
        avg_price_usdc:    "0",
        opportunity_score: c.score.toString(),
      }));

    const result = { gaps: [...rows, ...synthetic] };
    await cacheSet(cacheKey, result, 60);  // 1min cache
    res.json(result);
  } catch (err) { next(err); }
});

// ── GET /v1/market/top-sellers ────────────────────────────────────────────────
// Creator Agent uses this to find goods worth cloning
router.get("/top-sellers", async (req, res, next) => {
  try {
    const { kinds = "dataset,api-wrapper", limit = "10", sort = "sales" } = req.query;
    const cacheKey = `market:top-sellers:${kinds}:${sort}`;
    const cached   = await cacheGet(cacheKey);
    if (cached) return res.json(cached);

    const { rows } = await db.query(`
      SELECT
        l.id,
        l.title,
        l.category,
        l.good_kind AS kind,
        l.seller,
        l.price_usdc,
        l.metadata_uri,
        l.reputation_score,
        COUNT(p.id)::int AS sales_count,
        COALESCE(AVG(l.reputation_score), 50)::numeric(5,2) AS avg_rating
      FROM listings l
      LEFT JOIN purchases p ON p.listing_id = l.id AND p.status = 'confirmed'
      WHERE l.good_kind = ANY($1)
      GROUP BY l.id
      ORDER BY sales_count DESC, l.reputation_score DESC
      LIMIT $2
    `, [kinds.split(","), parseInt(limit)]);

    const result = { listings: rows };
    await cacheSet(cacheKey, result, 120);  // 2min cache
    res.json(result);
  } catch (err) { next(err); }
});

// ── GET /v1/market/average-price ──────────────────────────────────────────────
// Seller Agent's pricing engine uses this for competition-based pricing
router.get("/average-price", async (req, res, next) => {
  try {
    const { category } = req.query;
    if (!category) return res.status(400).json({ error: "category required" });

    const cacheKey = `market:avg-price:${category}`;
    const cached   = await cacheGet(cacheKey);
    if (cached) return res.json(cached);

    const { rows } = await db.query(`
      SELECT
        ROUND(AVG(price_usdc)::numeric, 4) AS average_price_usdc,
        ROUND(MIN(price_usdc)::numeric, 4) AS min_price_usdc,
        ROUND(MAX(price_usdc)::numeric, 4) AS max_price_usdc,
        COUNT(*)::int                      AS listing_count
      FROM listings
      WHERE category = $1 AND available = true
    `, [category]);

    const result = rows[0] || { average_price_usdc: 0, min_price_usdc: 0,
                                 max_price_usdc: 0, listing_count: 0 };
    await cacheSet(cacheKey, result, 30);
    res.json(result);
  } catch (err) { next(err); }
});

// ── GET /v1/market/stats ──────────────────────────────────────────────────────
// Dashboard uses this for overview metrics
router.get("/stats", async (req, res, next) => {
  try {
    const cacheKey = "market:stats";
    const cached   = await cacheGet(cacheKey);
    if (cached) return res.json(cached);

    const [listings, purchases, volume] = await Promise.all([
      db.query(`SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE available=true) AS active FROM listings`),
      db.query(`SELECT COUNT(*) AS total FROM purchases WHERE status='confirmed'`),
      db.query(`SELECT COALESCE(SUM(price_usdc),0) AS total_volume FROM purchases WHERE status='confirmed'`),
    ]);

    const result = {
      total_listings:  parseInt(listings.rows[0].total),
      active_listings: parseInt(listings.rows[0].active),
      total_trades:    parseInt(purchases.rows[0].total),
      total_volume_usdc: parseFloat(volume.rows[0].total_volume),
    };
    await cacheSet(cacheKey, result, 30);
    res.json(result);
  } catch (err) { next(err); }
});

export default router;
