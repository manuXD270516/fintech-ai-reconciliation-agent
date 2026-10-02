/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The browser only talks to this origin; `/api` is proxied to the loopback API so no CORS
// is needed and the API stays unexposed. Loopback ports follow the repo's 181xx range.
const target = process.env.RECON_API_TARGET ?? "http://127.0.0.1:18180";
const proxy = {
  "/api": {
    target,
    rewrite: (path: string) => path.replace(/^\/api/, ""),
  },
};

export default defineConfig({
  // GitHub Pages serves the static demo under /<repo>/ (VITE_BASE); local builds use "/".
  base: process.env.VITE_BASE ?? "/",
  plugins: [react()],
  server: { host: "127.0.0.1", port: 18181, strictPort: true, proxy },
  preview: { host: "127.0.0.1", port: 18181, strictPort: true, proxy },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
