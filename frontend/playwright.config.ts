import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  retries: 0,
  timeout: 60000,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:3001", headless: true, trace: "off" },
  webServer: { command: "npm run start -- --hostname 127.0.0.1 --port 3001", url: "http://127.0.0.1:3001/secure", reuseExistingServer: true },
});
