// src/pages/Agents.jsx
import { useApi }       from "../hooks/useApi.js";
import { api }          from "../lib/api.js";
import { TopBar, Card, Spinner, Badge, StatCard, EmptyState } from "../components/layout/UI.jsx";
import { Bot, TrendingUp, ShoppingCart, Zap, Palette } from "lucide-react";

const AGENT_TYPES = [
  { type: "buyer",     label: "Buyer Agent",     icon: ShoppingCart, color: "#00E5FF", desc: "Scans and buys underpriced listings" },
  { type: "seller",    label: "Seller Agent",     icon: TrendingUp,   color: "#00FF94", desc: "Lists, reprices, and fulfills orders" },
  { type: "creator",   label: "Creator Agent",    icon: Palette,      color: "#FFB800", desc: "Generates datasets and API wrappers" },
  { type: "arbitrage", label: "Arbitrage Agent",  icon: Zap,          color: "#FF4560", desc: "Detects and exploits price spreads" },
];

export default function Agents() {
  const { data: purchases,  loading: loadP } = useApi(() => api.purchases.list({ limit: 200 }),  [], 30_000);
  const { data: positions,  loading: loadA } = useApi(() => api.arbitrage.positions({ limit: 100 }), [], 30_000);
  const { data: goods,      loading: loadC } = useApi(() => api.creator.goods({ limit: 100 }),   [], 30_000);

  const loading = loadP || loadA || loadC;

  const buyerTrades  = purchases?.purchases?.filter(p => p.status === "confirmed").length ?? 0;
  const sellerTrades = purchases?.purchases?.length ?? 0;
  const arbOpen      = positions?.positions?.filter(p => p.status === "open").length ?? 0;
  const arbSold      = positions?.positions?.filter(p => p.status === "sold").length ?? 0;
  const createdGoods = goods?.goods?.length ?? 0;

  const arbProfit = positions?.positions
    ?.filter(p => p.status === "sold")
    ?.reduce((sum, p) => sum + Number(p.actual_profit ?? 0), 0) ?? 0;

  return (
    <div className="flex-1 overflow-auto">
      <TopBar title="Agents" subtitle="Monitor all autonomous agents" />

      <div className="p-6 space-y-6 animate-[fadeIn_0.4s_ease]">

        {/* Agent cards */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {AGENT_TYPES.map(({ type, label, icon: Icon, color, desc }) => (
            <Card key={type} className="p-5">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center"
                       style={{ background: `${color}15`, border: `1px solid ${color}30` }}>
                    <Icon size={16} style={{ color }} />
                  </div>
                  <div>
                    <p className="font-display text-white text-sm font-bold">{label}</p>
                    <p className="text-xs text-[#4A6070]">{desc}</p>
                  </div>
                </div>
                <Badge color="green">active</Badge>
              </div>

              {/* Agent-specific stats */}
              {loading ? (
                <div className="h-16 flex items-center justify-center">
                  <div className="w-4 h-4 border border-[#1A2332] border-t-[#00E5FF] rounded-full animate-spin" />
                </div>
              ) : (
                <div className="grid grid-cols-3 gap-3">
                  {type === "buyer" && <>
                    <Metric label="Purchases" value={buyerTrades} color={color} />
                    <Metric label="Strategy"  value="value-score" color={color} />
                    <Metric label="Status"    value="scanning"    color={color} />
                  </>}
                  {type === "seller" && <>
                    <Metric label="Trades"   value={sellerTrades} color={color} />
                    <Metric label="Pricing"  value="4 modes"      color={color} />
                    <Metric label="Status"   value="listing"      color={color} />
                  </>}
                  {type === "creator" && <>
                    <Metric label="Goods"    value={createdGoods} color={color} />
                    <Metric label="Strategy" value="gap-first"    color={color} />
                    <Metric label="Status"   value="analysing"    color={color} />
                  </>}
                  {type === "arbitrage" && <>
                    <Metric label="Open"   value={arbOpen}                    color={color} />
                    <Metric label="Sold"   value={arbSold}                    color={color} />
                    <Metric label="Profit" value={`$${arbProfit.toFixed(2)}`} color={color} />
                  </>}
                </div>
              )}
            </Card>
          ))}
        </div>

        {/* Arbitrage positions table */}
        <Card className="p-5">
          <p className="text-xs text-[#4A6070] font-mono uppercase tracking-widest mb-4">
            Arbitrage Positions
          </p>
          {loadA ? <Spinner /> : !positions?.positions?.length ? (
            <EmptyState message="No arbitrage positions yet" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1A2332]">
                    {["Agent","Buy Listing","Buy Price","Resell Price","Expected Profit","Status","Opened"].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-mono text-[#4A6070] uppercase tracking-widest">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1A2332]/60">
                  {positions.positions.slice(0, 20).map(p => (
                    <tr key={p.id} className="hover:bg-[#1A2332]/20">
                      <td className="px-4 py-3 font-mono text-xs text-[#4A6070]">{p.agent_id}</td>
                      <td className="px-4 py-3 font-mono text-xs text-[#C8D8E4]">#{p.buy_listing_id}</td>
                      <td className="px-4 py-3 font-mono text-[#FF4560]">${Number(p.buy_price_usdc).toFixed(2)}</td>
                      <td className="px-4 py-3 font-mono text-[#00FF94]">${Number(p.resell_price_usdc).toFixed(2)}</td>
                      <td className="px-4 py-3 font-mono text-[#FFB800]">${Number(p.expected_profit).toFixed(4)}</td>
                      <td className="px-4 py-3">
                        <Badge color={
                          p.status === "sold" ? "green" :
                          p.status === "open" ? "accent" :
                          p.status === "cancelled" ? "amber" : "red"
                        }>{p.status}</Badge>
                      </td>
                      <td className="px-4 py-3 text-xs text-[#4A6070]">
                        {new Date(p.opened_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function Metric({ label, value, color }) {
  return (
    <div className="bg-[#080C0F] rounded-lg p-3 border border-[#1A2332]">
      <p className="text-xs text-[#4A6070] mb-1">{label}</p>
      <p className="font-display text-sm font-bold" style={{ color }}>{value}</p>
    </div>
  );
}
