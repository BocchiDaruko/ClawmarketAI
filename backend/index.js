import "dotenv/config";
import express        from "express";
import helmet         from "helmet";
import cors           from "cors";
import rateLimit      from "express-rate-limit";

import { logger }         from "./middleware/logger.js";
import { errorHandler }   from "./middleware/errorHandler.js";
import { authenticate }   from "./middleware/auth.js";
import { db }             from "./db/client.js";
import { redis }          from "./db/redis.js";
import { startChainListener } from "./chain/listener.js";
import { startWebSocketServer } from "./websocket/server.js";

import listingsRouter     from "./routes/listings.js";
import marketRouter       from "./routes/market.js";
import purchasesRouter    from "./routes/purchases.js";
import fulfillmentRouter  from "./routes/fulfillment.js";
import creatorRouter      from "./routes/creator.js";
import arbitrageRouter    from "./routes/arbitrage.js";
import healthRouter       from "./routes/health.js";

const app  = express();
const PORT = process.env.PORT || 3001;

// ── Security middleware ───────────────────────────────────────────────────────
app.use(helmet());
app.use(cors({ origin: process.env.ALLOWED_ORIGINS?.split(",") || "*" }));

// ── Rate limiting ─────────────────────────────────────────────────────────────
app.use(rateLimit({
  windowMs: parseInt(process.env.RATE_LIMIT_WINDOW_MS || "60000"),
  max:      parseInt(process.env.RATE_LIMIT_MAX || "100"),
  message:  { error: "Too many requests — slow down." },
}));

// ── Body parsing ──────────────────────────────────────────────────────────────
app.use(express.json({ limit: "1mb" }));
app.use(express.urlencoded({ extended: true }));

// ── Request logging ───────────────────────────────────────────────────────────
app.use(logger);

// ── Public routes ─────────────────────────────────────────────────────────────
app.use("/health", healthRouter);

// ── Authenticated routes (all agents must send API key) ───────────────────────
app.use("/v1", authenticate);
app.use("/v1/listings",    listingsRouter);
app.use("/v1/market",      marketRouter);
app.use("/v1/purchases",   purchasesRouter);
app.use("/v1/fulfillment", fulfillmentRouter);
app.use("/v1/creator",     creatorRouter);
app.use("/v1/arbitrage",   arbitrageRouter);

// ── Global error handler ──────────────────────────────────────────────────────
app.use(errorHandler);

// ── Start server ──────────────────────────────────────────────────────────────
async function start() {
  try {
    // Verify DB connection
    await db.query("SELECT 1");
    console.log("✓ PostgreSQL connected");

    // Verify Redis connection
    await redis.ping();
    console.log("✓ Redis connected");

    const server = app.listen(PORT, () => {
      console.log(`✓ ClawmarketAI API running on port ${PORT}`);
      console.log(`  Environment: ${process.env.NODE_ENV}`);
      console.log(`  Chain: Base (${process.env.CHAIN_ID})`);
    });

    // Start WebSocket server (for Dashboard real-time updates)
    startWebSocketServer(server);
    console.log("✓ WebSocket server started");

    // Start Base on-chain event listener
    await startChainListener();
    console.log("✓ Chain event listener started");

  } catch (err) {
    console.error("Failed to start server:", err);
    process.exit(1);
  }
}

start();

export default app;
