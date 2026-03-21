// src/lib/api.js
const BASE = "/v1";
const KEY  = localStorage.getItem("claw_api_key") || "";

const headers = () => ({
  "Content-Type":  "application/json",
  "Authorization": `Bearer ${KEY}`,
});

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, { ...opts, headers: headers() });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

export const api = {
  listings:  {
    list:   (p = {}) => req(`/listings?${new URLSearchParams(p)}`),
    get:    (id)     => req(`/listings/${id}`),
    create: (d)      => req("/listings",      { method: "POST", body: JSON.stringify(d) }),
    update: (id, d)  => req(`/listings/${id}`,{ method: "PATCH",body: JSON.stringify(d) }),
    cancel: (id)     => req(`/listings/${id}`,{ method: "DELETE" }),
  },
  market: {
    stats:    ()      => req("/market/stats"),
    gaps:     (p = {})=> req(`/market/gaps?${new URLSearchParams(p)}`),
    topSellers:(p={}) => req(`/market/top-sellers?${new URLSearchParams(p)}`),
    avgPrice: (cat)   => req(`/market/average-price?category=${cat}`),
  },
  purchases: {
    list: (p = {}) => req(`/purchases?${new URLSearchParams(p)}`),
  },
  arbitrage: {
    positions: (p = {}) => req(`/arbitrage/positions?${new URLSearchParams(p)}`),
  },
  creator: {
    goods: (p = {}) => req(`/creator/goods?${new URLSearchParams(p)}`),
  },
  health: () => fetch("/health").then(r => r.json()),
};
