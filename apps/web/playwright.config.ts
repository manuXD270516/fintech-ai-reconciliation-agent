import { defineConfig, devices } from "@playwright/test";

// E2E against the real Compose stack (driven by scripts/web_e2e.py, which prepares data and
// tokens). The built app is served by `vite preview`, proxying /api to the loopback API.
export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "test-results/e2e-report.json" }]],
  use: {
    baseURL: "http://127.0.0.1:18181",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run preview",
    url: "http://127.0.0.1:18181",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
