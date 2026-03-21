// src/pages/Trades.jsx
import { useState }   from "react";
import { useApi }     from "../hooks/useApi.js";
import { api }        from "../lib/api.js";
import { TopBar, Card, Spinner, Badge, Table, Td, EmptyState, StatCard } from "../components/layout/UI.jsx";

export default function Trades() {
  const [filter, setFilter] = useState("");

  const { data, loading, refetch } = useApi(
    () => api.purchases.list({ limit: 200 }),
    [],
    15_000
  );

  const trades = (data?.purchases || []).filter(t =>
    !filter ||
    t.buyer?.toLowerCase().includes(filter.toLowerCase()) ||
    t.seller?.toLowerCase().includes(filter.toLowerCase()) ||
    t.listing_id?.includes(filter)
  );

  const totalVol   = trades.reduce((s, t) => s + Number(t.price_usdc ?? 0), 0);
  const byToken    = trades.reduce((acc, t) => {
    acc[t.payment_token] = (acc[t.payment_token] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="flex-1 overflow-auto">
      <TopBar title="Trades" subtitle="Purchase history" onRefresh={refetch} />

      <div className="p-6 space-y-6 animate-[fadeIn_0.4s_ease]">

        {/* Stats row */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <StatCard label="Total Trades"  value={trades.length.toLocaleString()} accent="accent" />
          <StatCard label="Volume (USDC)" value={`$${totalVol.toLocaleString(undefined,{maximumFractionDigits:0})}`} accent="green" />
          <StatCard label="Paid in USDC"  value={byToken.usdc  ?? 0} accent="white" />
          <StatCard label="Paid in CLAWX" value={byToken.clawx ?? 0} accent="amber" sub="0.8% fee rate" />
        </div>

        {/* Filter */}
        <div>
          <input
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Filter by buyer, seller, or listing ID..."
            className="w-full max-w-md px-4 py-2 bg-[#0E1419] border border-[#1A2332] rounded-lg text-sm text-[#C8D8E4] placeholder-[#4A6070] focus:outline-none focus:border-[#00E5FF]/50"
          />
        </div>

        {/* Table */}
        <Card>
          {loading ? <Spinner /> : trades.length === 0 ? (
            <EmptyState message="No trades found" />
          ) : (
            <div className="overflow-x-auto">
              <Table headers={["Listing","Buyer","Seller","Price (USDC)","Token","Tx Hash","Status","Date"]}>
                {trades.slice(0, 100).map(t => (
                  <tr key={t.id} className="hover:bg-[#1A2332]/20 transition-colors">
                    <Td><span className="font-mono text-xs text-[#4A6070]">#{t.listing_id}</span></Td>
                    <Td><span className="font-mono text-xs">{t.buyer?.slice(0,6)}…{t.buyer?.slice(-4)}</span></Td>
                    <Td><span className="font-mono text-xs">{t.seller?.slice(0,6)}…{t.seller?.slice(-4)}</span></Td>
                    <Td><span className="font-mono text-[#00FF94]">${Number(t.price_usdc).toFixed(4)}</span></Td>
                    <Td>
                      <Badge color={
                        t.payment_token === "clawx" ? "amber" :
                        t.payment_token === "claw"  ? "accent" : "muted"
                      }>{t.payment_token?.toUpperCase() ?? "USDC"}</Badge>
                    </Td>
                    <Td>
                      {t.tx_hash ? (
                        <a
                          href={`https://basescan.org/tx/${t.tx_hash}`}
                          target="_blank" rel="noreferrer"
                          className="font-mono text-xs text-[#00E5FF] hover:underline"
                        >
                          {t.tx_hash.slice(0,8)}…
                        </a>
                      ) : <span className="text-[#4A6070] text-xs">—</span>}
                    </Td>
                    <Td>
                      <Badge color={t.status === "confirmed" ? "green" : "amber"}>
                        {t.status}
                      </Badge>
                    </Td>
                    <Td><span className="text-xs text-[#4A6070]">{new Date(t.created_at).toLocaleDateString()}</span></Td>
                  </tr>
                ))}
              </Table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
