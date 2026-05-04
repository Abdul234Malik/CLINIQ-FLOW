import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    strictPort: true,
    proxy: {
      "/record-officer": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/admin": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/api": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/nlp": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/openapi.json": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/docs": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/redoc": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/health": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/patients": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/visits": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/ai": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/asr": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/translate": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/conversation": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/nurse": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/doctor": process.env.VITE_API_URL || "http://127.0.0.1:8000",
      "/med-orders": process.env.VITE_API_URL || "http://127.0.0.1:8000",
    },
  },
});
