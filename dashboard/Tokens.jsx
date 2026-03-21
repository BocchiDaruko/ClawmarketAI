// src/pages/Tokens.jsx
import { TopBar, Card, StatCard } from "../components/layout/UI.jsx";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, LineChart, Line
} from "recharts";

// Mock token data — replace with real on-chain reads via viem in production
const CLAW_SUPPLY_HISTORY = Array.from({ length: 30 }, (_, i) => ({
  day:     `Day ${i + 1}`,
  supply:  1_000_000_000 - (i * 12_000 + Math.random() * 5000),
  burned:  i * 12_000 + Math.random() * 5000,
}));

const CLAWX_EMISSION = Array.from({ length: 30 }, (_, i) => ({
  day:      `Day ${i + 1}`,
  emitted:  500_000_000 + (i * 547_945),
  staked:   Math.floor((500_000_000 + i * 547_945) * 0.35),
}));

const ALLOCATION = [
  { label: "Community",   pct: 40, color: "#00E5FF", tokens: "400M" },
  { label: "Treasury",    pct: 20, color: "#00FF94", tokens: "200M" },
  { label: "Team",        pct: 18, color: "#FFB800", tokens: "180M" },
  { label: "Backers",     pct: 12, color: "#FF4560", tokens: "120M" },
  { label: "Liquidity",   pct:  5, color: "#A78BFA", tokens: "50M"  },
  { label: "Advisors",    pct:  5, color: "#4A6070", tokens: "50M"  },
];

export default function Tokens() {
  const latestClaw  = CLAW_SUPPLY_HISTORY[CLAW_SUPPLY_HISTORY.length - 1];
  const latestClawx = CLAWX_EMISSION[CLAWX_EMISSION.length - 1];

  return (
    <div className="flex-1 overflow-auto">
      <TopBar title="Tokens" subtitle="$CLAW and $CLAWX on-chain metrics" />

      <div className="p-6 space-y-6 animate-[fadeIn_0.4s_ease]">

        {/* CLAW section */}
        <div>
          <p className="text-xs text-[#4A6070] font-mono uppercase tracking-widest mb-3">
            $CLAW — Governance Token
          </p>
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-4">
            <StatCard label="Circulating Supply" value={`${(latestClaw.supply / 1e6).toFixed(1)}M`}    accent="accent" />
            <StatCard label="Total Burned"        value={`${(latestClaw.burned / 1e3).toFixed(0)}K`}   accent="red"   sub="via BuyAndBurn" />
            <StatCard label="Burn Rate"           value="~12K / day"  accent="amber" sub="from protocol fees" />
            <StatCard label="Governance Votes"    value="1B → ∞"     accent="white" sub="1 token = 1 vote" />
          </div>

          <Card className="p-5">
            <p className="text-xs text-[#4A6070] font-mono uppercase tracking-widest mb-4">
              Circulating Supply (30 days)
            </p>
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={CLAW_SUPPLY_HISTORY}>
                <defs>
                  <linearGradient id="clawGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#FF4560" stopOpacity={0.15}/>
                    <stop offset="95%" stopColor="#FF4560" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1A2332" />
                <XAxis dataKey="day" tick={{ fill: "#4A6070", fontSize: 9 }} tickLine={false} axisLine={false} interval={4} />
                <YAxis tick={{ fill: "#4A6070", fontSize: 9 }} tickLine={false} axisLine={false}
                       tickFormatter={v => `${(v/1e6).toFixed(0)}M`} />
                <Tooltip
                  contentStyle={{ background: "#0E1419", border: "1px solid #1A2332", borderRadius: 8 }}
                  labelStyle={{ color: "#4A6070", fontSize: 11 }}
                  formatter={(v) => [`${(v/1e6).toFixed(2)}M CLAW`, "Supply"]}
                />
                <Area type="monotone" dataKey="supply" stroke="#FF4560" strokeWidth={1.5}
                      fill="url(#clawGrad)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </Card>
        </div>

        {/* CLAW allocation */}
        <Card className="p-5">
          <p className="text-xs text-[#4A6070] font-mono uppercase tracking-widest mb-4">
            $CLAW Allocation
          </p>
          <div className="space-y-3">
            {ALLOCATION.map(a => (
              <div key={a.label} className="flex items-center gap-3">
                <span className="text-xs text-[#C8D8E4] w-24 font-mono">{a.label}</span>
                <div className="flex-1 h-2 bg-[#1A2332] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{ width: `${a.pct}%`, background: a.color }}
                  />
                </div>
                <span className="text-xs font-mono w-8 text-right" style={{ color: a.color }}>
                  {a.pct}%
                </span>
                <span className="text-xs text-[#4A6070] font-mono w-12 text-right">{a.tokens}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* CLAWX section */}
        <div>
          <p className="text-xs text-[#4A6070] font-mono uppercase tracking-widest mb-3">
            $CLAWX — Utility Token
          </p>
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-4">
            <StatCard label="Total Emitted"   value={`${(latestClawx.emitted / 1e6).toFixed(1)}M`}  accent="green" />
            <StatCard label="Hard Cap"        value="2,000M"     accent="white" sub="never exceeded" />
            <StatCard label="Staked"          value={`${(latestClawx.staked / 1e6).toFixed(1)}M`}   accent="amber" sub="35% of supply" />
            <StatCard label="Current Era"     value="Era 0"      accent="accent" sub="200M/yr emission" />
          </div>

          <Card className="p-5">
            <p className="text-xs text-[#4A6070] font-mono uppercase tracking-widest mb-4">
              Emission vs Staked (30 days)
            </p>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={CLAWX_EMISSION}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1A2332" />
                <XAxis dataKey="day" tick={{ fill: "#4A6070", fontSize: 9 }} tickLine={false} axisLine={false} interval={4} />
                <YAxis tick={{ fill: "#4A6070", fontSize: 9 }} tickLine={false} axisLine={false}
                       tickFormatter={v => `${(v/1e6).toFixed(0)}M`} />
                <Tooltip
                  contentStyle={{ background: "#0E1419", border: "1px solid #1A2332", borderRadius: 8 }}
                  labelStyle={{ color: "#4A6070", fontSize: 11 }}
                  formatter={(v, n) => [`${(v/1e6).toFixed(2)}M`, n]}
                />
                <Line type="monotone" dataKey="emitted" stroke="#00FF94" strokeWidth={1.5} dot={false} name="Emitted" />
                <Line type="monotone" dataKey="staked"  stroke="#FFB800" strokeWidth={1.5} dot={false} name="Staked" strokeDasharray="4 4" />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </div>

      </div>
    </div>
  );
}
