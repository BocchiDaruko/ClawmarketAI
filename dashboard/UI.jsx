// src/components/layout/TopBar.jsx
import { Bell, RefreshCw } from "lucide-react";

export function TopBar({ title, subtitle, onRefresh }) {
  return (
    <div className="h-14 border-b border-[#1A2332] px-6 flex items-center justify-between">
      <div>
        <h1 className="font-display text-white font-bold text-sm tracking-wide">{title}</h1>
        {subtitle && <p className="text-xs text-[#4A6070] mt-0.5">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-2">
        {onRefresh && (
          <button
            onClick={onRefresh}
            className="p-2 rounded-lg text-[#4A6070] hover:text-[#00E5FF] hover:bg-[#1A2332] transition-all"
          >
            <RefreshCw size={14} />
          </button>
        )}
      </div>
    </div>
  );
}

// ── Shared UI primitives ───────────────────────────────────────────────────────

export function Card({ children, className = "" }) {
  return (
    <div className={`bg-[#0E1419] border border-[#1A2332] rounded-xl ${className}`}>
      {children}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="w-5 h-5 border-2 border-[#1A2332] border-t-[#00E5FF] rounded-full animate-spin" />
    </div>
  );
}

export function StatCard({ label, value, sub, accent = "accent", trend }) {
  const colors = {
    accent: "text-[#00E5FF]",
    green:  "text-[#00FF94]",
    amber:  "text-[#FFB800]",
    red:    "text-[#FF4560]",
    white:  "text-white",
  };
  return (
    <Card className="p-5">
      <p className="text-xs text-[#4A6070] uppercase tracking-widest font-mono mb-2">{label}</p>
      <p className={`font-display text-2xl font-bold ${colors[accent]}`}>{value}</p>
      {sub && <p className="text-xs text-[#4A6070] mt-1">{sub}</p>}
      {trend !== undefined && (
        <p className={`text-xs mt-1 font-mono ${trend >= 0 ? "text-[#00FF94]" : "text-[#FF4560]"}`}>
          {trend >= 0 ? "+" : ""}{trend.toFixed(1)}%
        </p>
      )}
    </Card>
  );
}

export function Badge({ children, color = "muted" }) {
  const cls = {
    green:  "text-[#00FF94] bg-[#00FF94]/10 border-[#00FF94]/20",
    accent: "text-[#00E5FF] bg-[#00E5FF]/10 border-[#00E5FF]/20",
    amber:  "text-[#FFB800] bg-[#FFB800]/10 border-[#FFB800]/20",
    red:    "text-[#FF4560] bg-[#FF4560]/10 border-[#FF4560]/20",
    muted:  "text-[#4A6070] bg-[#1A2332] border-[#1A2332]",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono border ${cls[color]}`}>
      {children}
    </span>
  );
}

export function EmptyState({ message = "No data available" }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-[#4A6070]">
      <p className="text-sm">{message}</p>
    </div>
  );
}

export function Table({ headers, children }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-[#1A2332]">
          {headers.map(h => (
            <th key={h} className="px-4 py-3 text-left text-xs font-mono text-[#4A6070] uppercase tracking-widest">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-[#1A2332]/60">
        {children}
      </tbody>
    </table>
  );
}

export function Td({ children, className = "" }) {
  return <td className={`px-4 py-3 text-[#C8D8E4] ${className}`}>{children}</td>;
}
