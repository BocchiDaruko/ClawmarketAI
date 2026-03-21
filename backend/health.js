// src/routes/health.js
import { Router } from "express";
import { db }     from "../db/client.js";
import { redis }  from "../db/redis.js";

const router = Router();

router.get("/", async (req, res) => {
  const checks = { api: "ok", db: "unknown", redis: "unknown", chain: "unknown" };
  try { await db.query("SELECT 1"); checks.db = "ok"; } catch { checks.db = "error"; }
  try { await redis.ping(); checks.redis = "ok"; } catch { checks.redis = "error"; }
  const allOk = Object.values(checks).every(v => v === "ok");
  res.status(allOk ? 200 : 503).json({ status: allOk ? "healthy" : "degraded", checks });
});

export default router;
