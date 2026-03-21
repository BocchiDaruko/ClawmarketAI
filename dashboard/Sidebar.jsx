// src/components/layout/Sidebar.jsx
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, List, Bot, ShoppingCart,
  BarChart3, Coins, Activity, Settings
} from "lucide-react";

const NAV = [
  { to: "/",          icon: LayoutDashboard, label: "Overview"  },
  { to: "/listings",  icon: List,            label: "Listings"  },
  { to: "/agents",    icon: Bot,             label: "Agents"    },
  { to: "/trades",    icon: ShoppingCart,    label: "Trades"    },
  { to: "/analytics", icon: BarChart3,       label: "Analytics" },
  { to: "/tokens",    icon: Coins,           label: "Tokens"    },
];

export function Sidebar({ connected }) {
  return (
    <aside className="w-56 min-h-screen bg-[#0A0F14] border-r border-[#1A2332] flex flex-col">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-[#1A2332]">
        <div className="flex items-center gap-2">
          <span className="text-[#00E5FF] text-xl">🦀</span>
          <span className="font-display text-white font-bold tracking-tight text-sm">
            Clawmarket<span className="text-[#00E5FF]">AI</span>
          </span>
        </div>
        <div className={`mt-2 flex items-center gap-1.5 text-xs ${connected ? "text-[#00FF94]" : "text-[#FF4560]"}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-[#00FF94]" : "bg-[#FF4560]"} animate-pulse`}/>
          {connected ? "Live" : "Reconnecting"}
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all
               ${isActive
                 ? "bg-[#00E5FF]/10 text-[#00E5FF] border border-[#00E5FF]/20"
                 : "text-[#4A6070] hover:text-[#C8D8E4] hover:bg-[#1A2332]/60"
               }`
            }
          >
            <Icon size={15} />
            <span className="font-medium">{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-[#1A2332]">
        <p className="text-xs text-[#4A6070] font-mono">Base Mainnet · 8453</p>
      </div>
    </aside>
  );
}
