/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: process.env.DEALGATE_DEV_API_URL ? {
      "/api": {
        target: process.env.DEALGATE_DEV_API_URL,
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, ""),
      },
    } : undefined,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    css: false,
  },
});
