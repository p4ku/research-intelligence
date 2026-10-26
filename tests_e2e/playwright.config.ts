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
  prod: 'https://research-scanner.schwarz',
  production: 'https://research-scanner.schwarz',
  slr: 'https://annotate.soinventive.co.uk',
  'slr.soinventive.co.uk': 'https://annotate.soinventive.co.uk',
  annotate: 'https://annotate.soinventive.co.uk',
  'annotate.soinventive.co.uk': 'https://annotate.soinventive.co.uk',
};

const rawTarget = (process.env.E2E_TARGET_ENV || 'local').trim();
const targetEnv = rawTarget.toLowerCase();

function resolveBaseURL(): string {
  if (process.env.E2E_BASE_URL) return process.env.E2E_BASE_URL.replace(/\/$/, '');
  if (targetEnv in ENV_TARGETS) return ENV_TARGETS[targetEnv];
  if (rawTarget.startsWith('http://') || rawTarget.startsWith('https://')) {
    return rawTarget.replace(/\/$/, '');
  }
  if (rawTarget.includes('.') || rawTarget.includes(':')) {
    const scheme = rawTarget.includes('localhost') || rawTarget.includes('127.0.0.1') ? 'http' : 'https';
    return `${scheme}://${rawTarget.replace(/\/$/, '')}`;
  }
  throw new Error(
    `Unknown E2E_TARGET_ENV "${process.env.E2E_TARGET_ENV}"; expected one of ${Object.keys(ENV_TARGETS).join(', ')} or a custom domain/URL.`,
  );
}

const baseURL = resolveBaseURL();
console.log(`[e2e] target=${rawTarget} baseURL=${baseURL}`);

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
