import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./local",
  workers: 1,
  retries: 0,
  timeout: 30_000,
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:5210",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
