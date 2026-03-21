// src/pages/Overview.jsx
import { useApi }       from "../hooks/useApi.js";
import { useWebSocket } from "../hooks/useWebSocket.js";
import { api }          from "../lib/api.js";
import { TopBar, Card, StatCard, Spinner, Badge } from "../components/layout/UI.jsx";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, BarChart, Bar
} from "recharts";
import { formatDistanceToNow } from "date-fns";

// ── Mock volume data (replace with real API data in production) ───────────────
const MOCK_VOLUME = Array.from({ length: 24 }, (_, i) => ({
  hour:   `${String(i).padStart(2,"0")}:00`,
  volume: Math.floor(Math.random() * 8000 + 1000),
  trades: Math.floor(Math.random() * 40 + 5),
}));

const MOCK_CATEGORIES = [
  { name: "compute",    value: 4200 },
  { name: "data",       value: 3100 },
  { name: "ai-service", value: 2800 },
  { name: "api-access", value: 1900 },
];

export default function Overview() {
  const { data: stats, loading } = useApi(api.market.stats, [], 30_000);
  const { messages, connected }  = useWebSocket();

  const feed = messages.filter(m =>
    ["listing:created","purchase:completed","escrow:released","fulfillment:delivered"].includes(m.type)
  );

  return (
    <div className="flex-1 overflow-auto">
      <TopBar title="Overview" subtitle="Real-time marketplace metrics" />

      <div className="p-6 space-y-6 animate-[fadeIn_0.4s_ease]">

        {/* ── Stat cards ── */}
        {loading ? <Spinner /> : (
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
            <StatCard
              label="Active Listings"
              value={stats?.active_listings?.toLocaleString() ?? "—"}
              sub="Currently available"
              accent="accent"
            />
            <StatCard
              label="Total Trades"
              value={stats?.total_trades?.toLocaleString() ?? "—"}
              sub="All time confirmed"
              accent="green"
            />
            <StatCard
              label="Volume (USDC)"
              value={stats?.total_volume_usdc
                ? `$${Number(stats.total_volume_usdc).toLocaleString(undefined,{maximumFractionDigits:0})}`
                : "—"}
              sub="Cumulative settled"
              accent="amber"
            />
            <StatCard
              label="Total Listings"
              value={stats?.total_listings?.toLocaleString() ?? "—"}
              sub="Created all time"
              accent="white"
            />
          </div>
        )}

        {/* ── Charts row ── */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">

          {/* Volume chart */}
          <Card className="xl:col-span-2 p-5">
            <p className="text-xs text-[#4A6070] font-mono uppercase tracking-widest mb-4">
              24h Trading Volume (USDC)
            </p>
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={MOCK_VOLUME}>
                <defs>
                  <linearGradient id="volGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#00E5FF" stopOpacity={0.15}/>
                    <stop offset="95%" stopColor="#00E5FF" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1A2332" />
                <XAxis dataKey="hour" tick={{ fill: "#4A6070", fontSize: 10 }} tickLine={false} axisLine={false} interval={3} />
                <YAxis tick={{ fill: "#4A6070", fontSize: 10 }} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={{ background: "#0E1419", border: "1px solid #1A2332", borderRadius: 8 }}
                  labelStyle={{ color: "#4A6070", fontSize: 11 }}
                  itemStyle={{ color: "#00E5FF" }}
                />
                <Area type="monotone" dataKey="volume" stroke="#00E5FF" strokeWidth={1.5}
                      fill="url(#volGrad)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </Card>

          {/* Category bar chart */}
          <Card className="p-5">
            <p className="text-xs text-[#4A6070] font-mono uppercase tracking-widest mb-4">
              Volume by Category
            </p>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={MOCK_CATEGORIES} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#1A2332" horizontal={false} />
                <XAxis type="number" tick={{ fill: "#4A6070", fontSize: 10 }} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="name" tick={{ fill: "#4A6070", fontSize: 10 }} tickLine={false} axisLine={false} width={72} />
                <Tooltip
                  contentStyle={{ background: "#0E1419", border: "1px solid #1A2332", borderRadius: 8 }}
                  itemStyle={{ color: "#00FF94" }}
                />
                <Bar dataKey="value" fill="#00FF94" opacity={0.7} radius={[0,4,4,0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>

        {/* ── Live event feed ── */}
        <Card className="p-5">
          <div className="flex items-center justify-between mb-4">
            <p className="text-xs text-[#4A6070] font-mono uppercase tracking-widest">
              Live Event Feed
            </p>
            <span className={`flex items-center gap-1.5 text-xs font-mono ${connected ? "text-[#00FF94]" : "text-[#FF4560]"}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-[#00FF94] animate-pulse" : "bg-[#FF4560]"}`}/>
              {connected ? "LIVE" : "OFFLINE"}
            </span>
          </div>

          <div className="space-y-2 max-h-64 overflow-y-auto">
            {feed.length === 0 && (
              <p className="text-xs text-[#4A6070] text-center py-8">
                Waiting for events...
              </p>
            )}
            {feed.map((msg, i) => (
              <div key={i} className="flex items-start gap-3 py-2 border-b border-[#1A2332]/40 last:border-0 animate-[slideUp_0.3s_ease]">
                <EventBadge type={msg.type} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-[#C8D8E4] font-mono truncate">
                    {eventLabel(msg)}
                  </p>
                  <p className="text-xs text-[#4A6070] mt-0.5">
                    {formatDistanceToNow(new Date(msg.timestamp), { addSuffix: true })}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </Card>

      </div>
    </div>
  );
}

function EventBadge({ type }) {
  const map = {
    "listing:created":     { color: "accent", label: "LIST" },
    "purchase:completed":  { color: "green",  label: "BUY"  },
    "escrow:released":     { color: "amber",  label: "ESCR" },
    "fulfillment:delivered":{ color: "green", label: "DLVR" },
    "listing:repriced":    { color: "amber",  label: "REPR" },
    "listing:cancelled":   { color: "red",    label: "CNCL" },
  };
  const { color, label } = map[type] || { color: "muted", label: "EVT" };
  return <Badge color={color}>{label}</Badge>;
}

function eventLabel(msg) {
  switch (msg.type) {
    case "listing:created":      return `New listing #${msg.listingId} · ${msg.category}`;
    case "purchase:completed":   return `Purchase #${msg.listingId} · $${msg.priceUsdc?.toFixed(2)} USDC`;
    case "escrow:released":      return `Escrow released #${msg.listingId} · $${msg.net?.toFixed(2)}`;
    case "fulfillment:delivered":return `Delivery confirmed · ${msg.good_kind}`;
    case "listing:repriced":     return `Repriced #${msg.listingId} → $${msg.newPrice?.toFixed(4)}`;
    default: return JSON.stringify(msg);
  }
}
