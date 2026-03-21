// src/db/client.js
import pg from "pg";
const { Pool } = pg;

export const db = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 20,
  idleTimeoutMillis: 30_000,
  connectionTimeoutMillis: 2_000,
});

db.on("error", (err) => {
  console.error("Unexpected DB error:", err);
});
