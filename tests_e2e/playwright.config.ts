import { defineConfig, devices } from '@playwright/test';

/**
 * Environment target resolution.
 *
 * Defaults to the local Next.js dev server (`bun run dev` in frontend/, port 3000)
 * so a bare `playwright test` never drives production. Pick another target with
 * E2E_TARGET_ENV=staging|prod, or point at any origin with E2E_BASE_URL.
 */
const ENV_TARGETS: Record<string, string> = {
  local: 'http://localhost:3000',
  staging: 'https://sri.soinventive.co.uk',
  prod: 'https://sri-prod.apps.01.cf.eu01.onstackit.cloud',
  production: 'https://sri-prod.apps.01.cf.eu01.onstackit.cloud',
};

const targetEnv = (process.env.E2E_TARGET_ENV || 'local').toLowerCase();
if (!(targetEnv in ENV_TARGETS)) {
  // A typo must not quietly land on a different environment than the one meant.
  throw new Error(
    `Unknown E2E_TARGET_ENV "${process.env.E2E_TARGET_ENV}"; expected one of ${Object.keys(ENV_TARGETS).join(', ')}`,
  );
}
const baseURL = process.env.E2E_BASE_URL || ENV_TARGETS[targetEnv];
console.log(`[e2e] target=${targetEnv} baseURL=${baseURL}`);

export default defineConfig({
  testDir: './specs',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false, // Run scenarios sequentially for stable shared session
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    ignoreHTTPSErrors: true,
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
