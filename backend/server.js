// src/websocket/server.js
import { WebSocketServer, WebSocket } from "ws";

let wss = null;

/**
 * Attaches a WebSocket server to the existing HTTP server.
 * Clients connect to ws://host/ws and receive real-time events:
 *   - listing:created / listing:repriced / listing:cancelled
 *   - purchase:completed
 *   - escrow:released
 *   - fulfillment:delivered
 */
export function startWebSocketServer(httpServer) {
  wss = new WebSocketServer({ server: httpServer, path: "/ws" });

  wss.on("connection", (ws, req) => {
    const ip = req.socket.remoteAddress;
    console.log(`[ws] Client connected from ${ip} (total: ${wss.clients.size})`);

    ws.send(JSON.stringify({ type: "connected", message: "ClawmarketAI live feed" }));

    ws.on("message", (raw) => {
      try {
        const msg = JSON.parse(raw.toString());
        // Clients can subscribe to specific event types
        if (msg.type === "subscribe" && Array.isArray(msg.events)) {
          ws.subscribedEvents = new Set(msg.events);
        }
      } catch { /* ignore malformed messages */ }
    });

    ws.on("close",  () => console.log(`[ws] Client disconnected (total: ${wss.clients.size})`));
    ws.on("error",  (err) => console.error("[ws] Client error:", err.message));
  });

  // Heartbeat — ping all clients every 30s to detect dead connections
  const heartbeat = setInterval(() => {
    if (!wss) return clearInterval(heartbeat);
    for (const client of wss.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.ping();
      }
    }
  }, 30_000);
}

/**
 * Broadcast an event to all connected WebSocket clients.
 * If a client has subscribed to specific events, only send matching ones.
 */
export function wsBroadcast(payload) {
  if (!wss) return;
  const message = JSON.stringify({ ...payload, timestamp: new Date().toISOString() });

  for (const client of wss.clients) {
    if (client.readyState !== WebSocket.OPEN) continue;
    // If client has a subscription filter, respect it
    if (client.subscribedEvents && !client.subscribedEvents.has(payload.type)) continue;
    client.send(message, (err) => {
      if (err) console.error("[ws] Send error:", err.message);
    });
  }
}
