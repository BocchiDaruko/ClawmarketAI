// src/pages/Analytics.jsx
import { useApi }    from "../hooks/useApi.js";
import { api }       from "../lib/api.js";
import { TopBar, Card, Spinner, Badge, EmptyState } from "../components/layout/UI.jsx";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis, CartesianGrid
} from "recharts";

export default function Analytics() {
  const { data: gaps,    loading: lg } = useApi(() => api.market.gaps(),        [], 60_000);
  const { data: sellers, loading: ls } = useApi(() => api.market.topSellers(),  [], 60_000);

  return (
    <div className="flex-1 overflow-auto">
      <TopBar title="Analytics" subtitle="Market intelligence for all agents" />

      <div className="p-6 space-y-6 animate-[fadeIn_0.4s_ease]">

        {/* Market gaps */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">

          <Card className="p-5">
            <p className="text-xs text-[#4A6070] font-mono uppercase tracking-widest mb-4">
              Market Gaps — Creator Agent Targets
            </p>
            {lg ? <Spinner /> : !gaps?.gaps?.length ? (
              <EmptyState message="No gap data available" />
            ) : (
              <div className="space-y-3">
                {gaps.gaps.slice(0, 8).map((g, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-[#C8D8E4] font-mono truncate">{g.category}</span>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <Badge color="accent">{g.good_kind}</Badge>
                          <span className="text-xs font-mono text-[#FFB800]">
                            {(Number(g.opportunity_score) * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                      <div className="h-1.5 bg-[#1A2332] rounded-full overflow-hidden">
                        <div
                          className="h-full bg-[#00E5FF] rounded-full transition-all"
                          style={{ width: `${Number(g.opportunity_score) * 100}%` }}
                        />
                      </div>
                      <div className="flex justify-between mt-1">
                        <span className="text-xs text-[#4A6070]">
                          {g.search_volume} searches · {g.listing_count} listings
                        </span>
                        {Number(g.avg_price_usdc) > 0 && (
                          <span className="text-xs text-[#4A6070] font-mono">
                            avg ${Number(g.avg_price_usdc).toFixed(2)}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Opportunity radar */}
          <Card className="p-5">
            <p className="text-xs text-[#4A6070] font-mono uppercase tracking-widest mb-4">
              Opportunity Score Radar
            </p>
            {lg ? <Spinner /> : (
              <ResponsiveContainer width="100%" height={240}>
                <RadarChart data={(gaps?.gaps || []).slice(0, 6).map(g => ({
                  category: g.category.replace("-", " "),
                  score: Math.round(Number(g.opportunity_score) * 100),
                }))}>
                  <PolarGrid stroke="#1A2332" />
                  <PolarAngleAxis dataKey="category" tick={{ fill: "#4A6070", fontSize: 10 }} />
                  <Radar
                    name="Opportunity" dataKey="score"
                    stroke="#00E5FF" fill="#00E5FF" fillOpacity={0.1}
                    strokeWidth={1.5}
                  />
                  <Tooltip
                    contentStyle={{ background: "#0E1419", border: "1px solid #1A2332", borderRadius: 8 }}
                    itemStyle={{ color: "#00E5FF" }}
                  />
                </RadarChart>
              </ResponsiveContainer>
            )}
          </Card>
        </div>

        {/* Top sellers */}
        <Card className="p-5">
          <p className="text-xs text-[#4A6070] font-mono uppercase tracking-widest mb-4">
            Top Sellers — Creator Agent Clone Targets
          </p>
          {ls ? <Spinner /> : !sellers?.listings?.length ? (
            <EmptyState message="No top seller data yet" />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {sellers.listings.slice(0, 6).map((l, i) => (
                <div key={l.id} className="bg-[#080C0F] border border-[#1A2332] rounded-lg p-4">
                  <div className="flex items-start justify-between mb-2">
                    <span className="text-xs font-mono text-[#4A6070]">#{i + 1}</span>
                    <Badge color="amber">{l.kind}</Badge>
                  </div>
                  <p className="text-sm text-white font-medium truncate mb-1">{l.title}</p>
                  <p className="text-xs text-[#4A6070] mb-3">{l.category}</p>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[#00FF94] text-sm">
                      ${Number(l.price_usdc).toFixed(2)}
                    </span>
                    <span className="text-xs text-[#4A6070]">
                      {l.sales_count} sales
                    </span>
                  </div>
                  <div className="mt-2 flex items-center gap-1.5">
                    <div className="h-1 flex-1 bg-[#1A2332] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[#FFB800] rounded-full"
                        style={{ width: `${l.avg_rating ?? 50}%` }}
                      />
                    </div>
                    <span className="text-xs font-mono text-[#4A6070]">
                      {Number(l.avg_rating ?? 50).toFixed(0)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

      </div>
    </div>
  );
}
