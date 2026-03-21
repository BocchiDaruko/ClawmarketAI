// src/pages/Listings.jsx
import { useState }     from "react";
import { useApi }       from "../hooks/useApi.js";
import { api }          from "../lib/api.js";
import { TopBar, Card, Spinner, Badge, Table, Td, EmptyState } from "../components/layout/UI.jsx";
import { Search, SlidersHorizontal } from "lucide-react";

const CATEGORIES = ["all","compute","data","ai-service","api-access","digital"];

export default function Listings() {
  const [category, setCategory] = useState("all");
  const [search,   setSearch]   = useState("");
  const [available, setAvailable] = useState("true");

  const params = { limit: 200 };
  if (category !== "all") params.category = category;
  if (available !== "all") params.available = available;

  const { data, loading, refetch } = useApi(
    () => api.listings.list(params),
    [category, available],
    20_000
  );

  const listings = (data?.listings || []).filter(l =>
    !search || l.title?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex-1 overflow-auto">
      <TopBar title="Listings" subtitle={`${data?.total ?? 0} total`} onRefresh={refetch} />

      <div className="p-6 space-y-4 animate-[fadeIn_0.4s_ease]">

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="relative">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#4A6070]" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search listings..."
              className="pl-8 pr-3 py-2 bg-[#0E1419] border border-[#1A2332] rounded-lg text-sm text-[#C8D8E4] placeholder-[#4A6070] focus:outline-none focus:border-[#00E5FF]/50 w-52"
            />
          </div>

          {/* Category filter */}
          <div className="flex gap-1">
            {CATEGORIES.map(c => (
              <button
                key={c}
                onClick={() => setCategory(c)}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all ${
                  category === c
                    ? "bg-[#00E5FF]/10 text-[#00E5FF] border border-[#00E5FF]/30"
                    : "text-[#4A6070] hover:text-[#C8D8E4] border border-transparent"
                }`}
              >
                {c}
              </button>
            ))}
          </div>

          {/* Available toggle */}
          <select
            value={available}
            onChange={e => setAvailable(e.target.value)}
            className="px-3 py-2 bg-[#0E1419] border border-[#1A2332] rounded-lg text-xs text-[#C8D8E4] focus:outline-none focus:border-[#00E5FF]/50"
          >
            <option value="true">Available only</option>
            <option value="false">Sold only</option>
            <option value="all">All</option>
          </select>
        </div>

        {/* Table */}
        <Card>
          {loading ? <Spinner /> : listings.length === 0 ? <EmptyState message="No listings found" /> : (
            <div className="overflow-x-auto">
              <Table headers={["ID","Title","Category","Price","Seller","Reputation","Status","Listed"]}>
                {listings.map(l => (
                  <tr key={l.id} className="hover:bg-[#1A2332]/20 transition-colors">
                    <Td><span className="font-mono text-[#4A6070] text-xs">#{l.id}</span></Td>
                    <Td><span className="font-medium text-white truncate max-w-[180px] block">{l.title}</span></Td>
                    <Td><Badge color="accent">{l.category}</Badge></Td>
                    <Td><span className="font-mono text-[#00FF94]">${Number(l.price_usdc).toFixed(2)}</span></Td>
                    <Td><span className="font-mono text-xs text-[#4A6070]">{l.seller?.slice(0,6)}…{l.seller?.slice(-4)}</span></Td>
                    <Td>
                      <div className="flex items-center gap-1.5">
                        <div className="h-1 w-16 bg-[#1A2332] rounded-full overflow-hidden">
                          <div
                            className="h-full bg-[#00E5FF] rounded-full"
                            style={{ width: `${l.reputation_score ?? 50}%` }}
                          />
                        </div>
                        <span className="text-xs font-mono text-[#4A6070]">
                          {Number(l.reputation_score ?? 50).toFixed(0)}
                        </span>
                      </div>
                    </Td>
                    <Td>
                      <Badge color={l.available ? "green" : "muted"}>
                        {l.available ? "active" : l.sold_at ? "sold" : "cancelled"}
                      </Badge>
                    </Td>
                    <Td>
                      <span className="text-xs text-[#4A6070]">
                        {l.listed_at ? new Date(l.listed_at).toLocaleDateString() : "—"}
                      </span>
                    </Td>
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
