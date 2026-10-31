import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Flask API target for the /api proxy. The review script sets API_URL to
// the live server; default matches the Flask dev port from web/README.md.
const apiTarget = process.env.API_URL ?? "http://127.0.0.1:5001";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
    },
  },
});
