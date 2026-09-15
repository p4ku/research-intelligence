import { chromium } from '@playwright/test';

const BASE_URL = 'https://research-scanner.schwarz';
const USER = 'admin';
const PASSWORD = 'schwarz123!';
const URL_TEST_1 = 'https://research-scanner.schwarz/briefing/2026-09-10?domain=16032bef-70d9-413d-9059-c5866e4a2cf8&run=38eaa56c-24b9-4c13-807b-0b76876190e3&page=3';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  page.on('request', (r) => { r._start = Date.now(); });
  page.on('response', (r) => {
    const dur = Date.now() - (r.request()._start || Date.now());
    const u = r.url();
    if (u.includes('/briefing') || u.includes('/api/') || u.includes('/bff/')) {
      console.log(`📡 [${r.request().method()}] ${r.status()} ${dur}ms | ${u}`);
    }
  });

  try {
    console.log('Logging in...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
    await page.fill('#login-identifier', USER);
    await page.fill('#login-password', PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForTimeout(2000);
    console.log('Logged in.');

    console.log(`\nNavigating to ${URL_TEST_1}...`);
    const t0 = Date.now();
    await page.goto(URL_TEST_1, { waitUntil: 'networkidle' });
    const totalGoto = Date.now() - t0;
    console.log(`Total goto took: ${totalGoto}ms`);

    const navTiming = await page.evaluate(() => {
      const [nav] = performance.getEntriesByType('navigation');
      return {
        ttfb: nav ? Math.round(nav.responseStart - nav.requestStart) : null,
        download: nav ? Math.round(nav.responseEnd - nav.responseStart) : null,
        domInteractive: nav ? Math.round(nav.domInteractive - nav.startTime) : null,
        duration: nav ? Math.round(nav.duration) : null,
      };
    });
    console.log('Navigation Performance Timing:', JSON.stringify(navTiming));

    // Wait 2 seconds to see if background requests are firing
    console.log('\nObserving background requests for 2s...');
    await page.waitForTimeout(2000);

    // Test clicking pagination button (e.g., page 2)
    console.log('\nTesting pagination click to page 2...');
    const page2Btn = page.locator('button:has-text("2")').first();
    if (await page2Btn.isVisible()) {
      const tPage = Date.now();
      await page2Btn.click();
      await page.waitForSelector('button[aria-current="page"]:has-text("2")', { timeout: 10000 });
      const p2Dur = Date.now() - tPage;
      console.log(`✅ Page 2 transition committed in DOM in ${p2Dur}ms`);
      await page.waitForLoadState('networkidle');
      console.log(`Page 2 networkidle reached in ${Date.now() - tPage}ms`);
    } else {
      console.log('Page 2 button not visible.');
    }

    // Test clicking back to page 1
    console.log('\nTesting pagination click back to page 1...');
    const page1Btn = page.locator('button:has-text("1")').first();
    if (await page1Btn.isVisible()) {
      const tPage1 = Date.now();
      await page1Btn.click();
      await page.waitForSelector('button[aria-current="page"]:has-text("1")', { timeout: 10000 });
      const p1Dur = Date.now() - tPage1;
      console.log(`✅ Page 1 transition committed in DOM in ${p1Dur}ms`);
      await page.waitForLoadState('networkidle');
    }

    // Capture screenshot of final state
    await page.screenshot({ path: 'scratch/briefing_final.png', fullPage: false });
    console.log('Screenshot saved to scratch/briefing_final.png');

  } catch (err) {
    console.error('Error during test:', err);
  } finally {
    await browser.close();
  }
}

main();
