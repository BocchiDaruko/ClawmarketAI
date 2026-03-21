// src/middleware/auth.js
import { db }     from "../db/client.js";
import { cacheGet, cacheSet } from "../db/redis.js";
import crypto from "crypto";

/**
 * API key authentication middleware.
 * Agents send: Authorization: Bearer <api_key>
 */
export async function authenticate(req, res, next) {
  const header = req.headers.authorization;
  if (!header?.startsWith("Bearer ")) {
    return res.status(401).json({ error: "Missing API key" });
  }
  const key     = header.slice(7);
  const keyHash = crypto.createHash("sha256").update(key).digest("hex");

  // Check Redis cache first
  const cached = await cacheGet(`apikey:${keyHash}`);
  if (cached === "invalid") return res.status(401).json({ error: "Invalid API key" });
  if (cached) {
    req.agent = cached;
    return next();
  }

  // Query DB
  const { rows } = await db.query(
    `SELECT id, agent_id, wallet_address FROM api_keys
     WHERE key_hash = $1 AND active = true`,
    [keyHash]
  );

  if (!rows.length) {
    await cacheSet(`apikey:${keyHash}`, "invalid", 60);
    return res.status(401).json({ error: "Invalid API key" });
  }

  const agent = rows[0];
  await cacheSet(`apikey:${keyHash}`, agent, 300);

  // Update last_used_at (fire and forget)
  db.query(`UPDATE api_keys SET last_used_at = NOW() WHERE id = $1`, [agent.id]).catch(() => {});

  req.agent = agent;
  next();
}
