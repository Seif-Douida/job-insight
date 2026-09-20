import { defineConfig, devices } from "@playwright/test";

/**
 * Smoke tests run against a production build, not the dev server.
 *
 * The thing worth testing is what visitors get: prerendered pages built from the marts. A
 * dev-server render would exercise different code and would not catch a page that fails
 * only at build time, which is the failure this suite exists to find.
 *
 * `DATABASE_URL` is read from the repository-root `.env` by `lib/env.ts`, so there is
 * nothing extra to configure locally. In CI the same variable comes from the environment.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? "github" : "list",

  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },

  // One browser. The phone-width checks set their own viewport rather than running the
  // whole suite twice for the one thing that differs between them.
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],

  webServer: {
    command: "npm run build && npm run start",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
  },
});
