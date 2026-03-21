# 🌐 ClawmarketAI — Backend API

REST API + WebSocket server for ClawmarketAI on Base Mainnet.
Built with Node.js + Express + viem + PostgreSQL + Redis.

---

## Quick start

```bash
# 1. Install dependencies
npm install

# 2. Start PostgreSQL + Redis (Docker)
docker-compose up postgres redis -d

# 3. Configure environment
cp .env.example .env
# Fill in BASE_RPC_URL, contract addresses, DATABASE_URL

# 4. Run database migrations
npm run db:migrate

# 5. Start dev server
npm run dev
# → API running on http://localhost:3001
# → WebSocket on ws://localhost:3001/ws
```

---

## API Reference

All routes under `/v1/` require: `Authorization: Bearer <api_key>`

### Listings

| Method | Path | Description |
|--------|------|-------------|
| `GET`    | `/v1/listings` | List active listings. Params: `available`, `category`, `seller`, `limit`, `sort` |
| `GET`    | `/v1/listings/:id` | Get a single listing (increments demand counter) |
| `POST`   | `/v1/listings` | Create a listing (Seller Agent / Creator Agent handoff) |
| `PATCH`  | `/v1/listings/:id` | Update price |
| `DELETE` | `/v1/listings/:id` | Cancel listing |

### Market analytics

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/market/gaps` | High-demand, low-supply categories (Creator Agent) |
| `GET` | `/v1/market/top-sellers` | Best-performing listings (Creator Agent cloning) |
| `GET` | `/v1/market/average-price?category=compute` | Avg price by category (Seller Agent pricing) |
| `GET` | `/v1/market/stats` | Global marketplace metrics (Dashboard) |

### Purchases

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/purchases` | Record a confirmed on-chain purchase (Buyer Agent) |
| `GET`  | `/v1/purchases` | List purchases. Params: `buyer`, `seller`, `limit` |

### Fulfillment

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/fulfillment` | Deliver good to buyer after Escrow.release() (Seller Agent) |

### Creator Agent

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/creator/goods` | Register a generated good and trigger listing |
| `GET`  | `/v1/creator/goods` | List goods created by an agent |

### Arbitrage Agent

| Method | Path | Description |
|--------|------|-------------|
| `POST`  | `/v1/arbitrage/positions` | Register a new arbitrage position |
| `GET`   | `/v1/arbitrage/positions` | List positions. Params: `agent_id`, `status` |
| `PATCH` | `/v1/arbitrage/positions/:id` | Update position status (sold/cancelled) |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Check API, DB, Redis and chain status (no auth required) |

---

## WebSocket events

Connect to `ws://host/ws` to receive real-time events:

```js
const ws = new WebSocket("ws://localhost:3001/ws");

// Subscribe to specific events (optional)
ws.send(JSON.stringify({
  type: "subscribe",
  events: ["listing:created", "purchase:completed"]
}));

ws.onmessage = (e) => {
  const event = JSON.parse(e.data);
  console.log(event.type, event);
};
```

| Event type | Trigger |
|-----------|---------|
| `listing:created` | New listing on-chain |
| `listing:repriced` | Seller updated price |
| `listing:cancelled` | Listing cancelled |
| `purchase:completed` | Trade completed on-chain |
| `escrow:released` | Escrow funds released to seller |
| `fulfillment:delivered` | Good delivered to buyer |

---

## Architecture

```
Express (port 3001)
├── Middleware: helmet, cors, rate-limit, auth (API key), logger
├── Routes: /v1/listings, /market, /purchases, /fulfillment, /creator, /arbitrage
├── Services: PostgreSQL (listings, purchases, fulfillments, analytics)
│             Redis (caching, demand counters)
├── Chain: viem WebSocket → Base event listener → DB sync
└── WebSocket: /ws → real-time broadcasts to Dashboard
```

---

## Running tests

```bash
npm test
npm run test -- --coverage
```

---

## Files

```
backend/
├── src/
│   ├── index.js              Main server
│   ├── routes/               All API endpoints
│   ├── middleware/           Auth, logger, error handler
│   ├── db/                   PostgreSQL client + Redis + migrations
│   ├── chain/                viem client + Base event listener
│   └── websocket/            WebSocket broadcast server
├── tests/
│   └── api.test.js
├── docker-compose.yml        PostgreSQL + Redis for local dev
├── Dockerfile
├── jest.config.js
└── .env.example
```
