// vite.config.js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/v1":    { target: "http://localhost:3001", changeOrigin: true },
      "/health":{ target: "http://localhost:3001", changeOrigin: true },
      "/ws":    { target: "ws://localhost:3001",   ws: true },
    },
  },
});
