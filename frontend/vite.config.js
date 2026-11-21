import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En desarrollo, /api y /health se redirigen a la API (uvicorn en :8000), incluido
// el WebSocket. Así el navegador habla con un solo origen y no hace falta CORS.
const API = process.env.VALKERY_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: API, ws: true, changeOrigin: true },
      "/health": { target: API, changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{js,jsx}"],
  },
});
