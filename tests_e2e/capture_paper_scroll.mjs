import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';

const BASE_URL = 'https://sri-prod.apps.01.cf.eu01.onstackit.cloud';
const USER = 'admin';
const PASSWORD = 'schwarz123!';
const OUT_DIR = join(process.cwd(), 'docs', 'user_journeys', 'screenshots');
const PAPER_ID = '1dab6d06-d931-423d-9472-95a1eba3b616';

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  console.log('🚀 Launching Playwright browser...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();

  try {
    console.log('🔑 Performing authentication...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.fill('#login-identifier', USER);
    await page.fill('#login-password', PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForTimeout(4000);

    console.log('📄 Navigating to Paper Detail page...');
    await page.goto(`${BASE_URL}/papers/${PAPER_ID}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);

    // Get total scrollable height
    const scrollHeight = await page.evaluate(() => document.documentElement.scrollHeight);
    const viewportHeight = 900;
    console.log(`📏 Page scrollHeight: ${scrollHeight}px, Viewport: ${viewportHeight}px`);

    // Capture sequentially: screenshot, scroll, screenshot ... until end of page
    let currentScroll = 0;
    let index = 1;
    const scrollStep = 650; // overlapping scroll step to ensure no gaps

    while (currentScroll < scrollHeight) {
      await page.evaluate((y) => window.scrollTo({ top: y, behavior: 'instant' }), currentScroll);
      await page.waitForTimeout(1000);

      const filename = `04_selected_document_part${index}.png`;
      console.log(`📸 Capturing scroll step ${index} at Y=${currentScroll}px -> ${filename}`);
      await page.screenshot({ path: join(OUT_DIR, filename), fullPage: false });

      if (currentScroll + viewportHeight >= scrollHeight) {
        break;
      }

      currentScroll += scrollStep;
      if (currentScroll + viewportHeight > scrollHeight) {
        currentScroll = scrollHeight - viewportHeight;
      }
      index++;
    }

    // Also take a full page screenshot as reference
    console.log('📸 Capturing complete full-page screenshot...');
    await page.screenshot({ path: join(OUT_DIR, '04_selected_document_fullpage.png'), fullPage: true });

    console.log(`🎉 Captured ${index} scroll screenshots plus full-page in: ${OUT_DIR}`);
  } catch (err) {
    console.error('❌ Error during capture:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
