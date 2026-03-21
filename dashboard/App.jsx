// src/App.jsx
import { Routes, Route } from "react-router-dom";
import { Sidebar }   from "./components/layout/Sidebar.jsx";
import { useWebSocket } from "./hooks/useWebSocket.js";

import Overview  from "./pages/Overview.jsx";
import Listings  from "./pages/Listings.jsx";
import Agents    from "./pages/Agents.jsx";
import Trades    from "./pages/Trades.jsx";
import Analytics from "./pages/Analytics.jsx";
import Tokens    from "./pages/Tokens.jsx";

export default function App() {
  const { connected } = useWebSocket();

  return (
    <div className="flex min-h-screen bg-[#080C0F]">
      <Sidebar connected={connected} />
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Routes>
          <Route path="/"          element={<Overview  />} />
          <Route path="/listings"  element={<Listings  />} />
          <Route path="/agents"    element={<Agents    />} />
          <Route path="/trades"    element={<Trades    />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/tokens"    element={<Tokens    />} />
        </Routes>
      </main>
    </div>
  );
}
