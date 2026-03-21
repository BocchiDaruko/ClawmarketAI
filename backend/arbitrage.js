// src/routes/arbitrage.js
import { Router } from "express";
import { z }      from "zod";
import { db }     from "../db/client.js";

const router = Router();

const PositionSchema = z.object({
  agent_id:         z.string(),
  buy_listing_id:   z.string(),
  buy_tx:           z.string().optional(),
  resell_listing_id:z.string().optional(),
  buy_price_usdc:   z.number().positive(),
  resell_price_usdc:z.number().positive(),
  expected_profit:  z.number(),
});

// POST /v1/arbitrage/positions — Arbitrage Agent registers a new position
router.post("/positions", async (req, res, next) => {
  try {
    const data = PositionSchema.parse(req.body);
    const { rows } = await db.query(
      `INSERT INTO arbitrage_positions
         (agent_id, buy_listing_id, buy_tx, resell_listing_id,
          buy_price_usdc, resell_price_usdc, expected_profit, status)
       VALUES ($1,$2,$3,$4,$5,$6,$7,'open')
       RETURNING *`,
      [data.agent_id, data.buy_listing_id, data.buy_tx || null,
       data.resell_listing_id || null, data.buy_price_usdc,
       data.resell_price_usdc, data.expected_profit]
    );
    res.status(201).json(rows[0]);
  } catch (err) {
    if (err instanceof z.ZodError) return res.status(400).json({ error: err.errors });
    next(err);
  }
});

// GET /v1/arbitrage/positions?agent_id=...
router.get("/positions", async (req, res, next) => {
  try {
    const { agent_id, status, limit = "50" } = req.query;
    const conds  = [];
    const params = [];
    let   idx    = 1;
    if (agent_id) { conds.push(`agent_id = $${idx++}`); params.push(agent_id); }
    if (status)   { conds.push(`status = $${idx++}`);   params.push(status); }
    const where = conds.length ? `WHERE ${conds.join(" AND ")}` : "";
    const { rows } = await db.query(
      `SELECT * FROM arbitrage_positions ${where} ORDER BY opened_at DESC LIMIT $${idx}`,
      [...params, parseInt(limit)]
    );
    res.json({ positions: rows });
  } catch (err) { next(err); }
});

// PATCH /v1/arbitrage/positions/:id — update status (sold, cancelled)
router.patch("/positions/:id", async (req, res, next) => {
  try {
    const { status, actual_profit } = req.body;
    const { rows } = await db.query(
      `UPDATE arbitrage_positions
       SET status = $1, actual_profit = $2, closed_at = NOW()
       WHERE id = $3 RETURNING *`,
      [status, actual_profit || null, req.params.id]
    );
    if (!rows.length) return res.status(404).json({ error: "Position not found" });
    res.json(rows[0]);
  } catch (err) { next(err); }
});

export default router;
