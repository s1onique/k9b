import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendHost = process.env.VITE_BACKEND_HOST || "127.0.0.1";
const backendPort = process.env.VITE_BACKEND_PORT || "8080";
const backendOrigin = `http://${backendHost}:${backendPort}`;

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: backendOrigin,
        changeOrigin: true,
      },
      "/artifact": {
        target: backendOrigin,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
