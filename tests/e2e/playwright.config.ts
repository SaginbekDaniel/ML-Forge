import { defineConfig } from "@playwright/test";

import { WEB_URL } from "./servers";

export default defineConfig({
  testDir: "./specs",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1, // one learner, one database: scenarios run in order
  retries: 0,
  reporter: [["list"], ["json", { outputFile: ".artifacts/results.json" }]],
  globalSetup: "./global-setup.ts",
  globalTeardown: "./global-teardown.ts",
  outputDir: ".artifacts/test-output",
  use: {
    baseURL: WEB_URL,
    locale: "ru-RU",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
