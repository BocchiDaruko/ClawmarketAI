// src/db/redis.js
import Redis from "ioredis";

export const redis = new Redis(process.env.REDIS_URL || "redis://localhost:6379", {
  maxRetriesPerRequest: 3,
  lazyConnect: true,
});

redis.on("error", (err) => console.error("Redis error:", err));

// ── Cache helpers ─────────────────────────────────────────────────────────────

export async function cacheGet(key) {
  const val = await redis.get(key);
  return val ? JSON.parse(val) : null;
}

export async function cacheSet(key, value, ttlSeconds = 30) {
  await redis.set(key, JSON.stringify(value), "EX", ttlSeconds);
}

export async function cacheDel(key) {
  await redis.del(key);
}

export async function cacheIncrBy(key, amount = 1, ttlSeconds = 3600) {
  const val = await redis.incrby(key, amount);
  await redis.expire(key, ttlSeconds);
  return val;
}
