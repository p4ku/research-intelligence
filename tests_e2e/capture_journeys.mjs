import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';

const BASE_URL = 'https://research-scanner.schwarz';
const USER = 'admin';
const PASSWORD = 'schwarz123!';
const OUT_DIR = join(process.cwd(), 'docs', 'user_journeys', 'screenshots');

async function gotoWithRetry(page, url, maxRetries = 4) {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const res = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(1000);
      const body = await page.innerText('body').catch(() => '');
      if (res && res.status() < 400 && !body.includes('502 Bad Gateway') && !body.includes('503 Service Unavailable')) {
        return res;
      }
      console.log(`⚠️ Attempt ${attempt} on ${url} gave status ${res?.status()} or 502. Retrying in 3s...`);
    } catch (e) {
      console.log(`⚠️ Attempt ${attempt} on ${url} failed: ${e.message}. Retrying in 3s...`);
    }
    await page.waitForTimeout(3000);
  }
  throw new Error(`Failed to load ${url} after ${maxRetries} attempts`);
}

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
    // 1. Capture Login screen
    console.log('📸 1. Capturing Login Page...');
    await gotoWithRetry(page, `${BASE_URL}/login`);
    await page.waitForTimeout(2000);
    await page.screenshot({ path: join(OUT_DIR, '01_login.png'), fullPage: false });

    // 2. Perform Login and establish session
    console.log('🔑 Performing authentication...');
    await page.fill('#login-identifier', USER);
    await page.fill('#login-password', PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForTimeout(4000);

    // 3. Capture Dashboard
    console.log('📸 2. Capturing Dashboard...');
    await gotoWithRetry(page, `${BASE_URL}/dashboard`);
    await page.waitForTimeout(2000);
    const retryBtn = page.locator('button:has-text("Retry"), button:has-text("Erneut versuchen")');
    if (await retryBtn.isVisible()) {
      console.log('🔄 Dashboard showed retry, clicking retry...');
      await retryBtn.click();
      await page.waitForTimeout(3000);
    }
    await page.screenshot({ path: join(OUT_DIR, '02_dashboard.png'), fullPage: false });

    // 4. Capture Briefings Archive and discover real paper
    console.log('📸 3. Capturing Briefings Archive...');
    await gotoWithRetry(page, `${BASE_URL}/briefing`);
    await page.waitForTimeout(2000);
    await page.screenshot({ path: join(OUT_DIR, '03_briefings.png'), fullPage: false });

    let paperPath = '';
    const briefingLinks = await page.locator('a[href*="briefing/"]').all();
    if (briefingLinks.length > 0) {
      const bHref = await briefingLinks[0].getAttribute('href');
      console.log(`📄 Navigating to briefing '${bHref}' to locate paper...`);
      await gotoWithRetry(page, `${BASE_URL}${bHref}`);
      await page.waitForTimeout(2000);
      const paperLinks = await page.locator('a[href^="/papers/"]').all();
      if (paperLinks.length > 0) {
        paperPath = await paperLinks[0].getAttribute('href');
        console.log(`🎯 Discovered active paper route: ${paperPath}`);
      }
    }

    if (!paperPath) {
      console.log('🔍 Fallback paper discovery via /papers...');
      await gotoWithRetry(page, `${BASE_URL}/papers`);
      await page.waitForTimeout(2000);
      const paperLinks = await page.locator('a[href^="/papers/"]').all();
      if (paperLinks.length > 0) {
        paperPath = await paperLinks[0].getAttribute('href');
      }
    }

    // 5. Capture Selected Document (Paper detail) — Top, Scroll Sequence, and Fullpage
    console.log(`📸 4. Capturing Selected Document Details (${paperPath})...`);
    await gotoWithRetry(page, `${BASE_URL}${paperPath}`);
    await page.waitForTimeout(3000);
    await page.screenshot({ path: join(OUT_DIR, '04_selected_document.png'), fullPage: false });

    // Sequential scroll capture
    const scrollHeight = await page.evaluate(() => document.documentElement.scrollHeight);
    const viewportHeight = 900;
    let currentScroll = 0;
    let partIndex = 1;
    const scrollStep = 650;
    while (currentScroll < scrollHeight) {
      await page.evaluate((y) => window.scrollTo({ top: y, behavior: 'instant' }), currentScroll);
      await page.waitForTimeout(600);
      await page.screenshot({ path: join(OUT_DIR, `04_selected_document_part${partIndex}.png`), fullPage: false });
      if (currentScroll + viewportHeight >= scrollHeight) break;
      currentScroll += scrollStep;
      if (currentScroll + viewportHeight > scrollHeight) currentScroll = scrollHeight - viewportHeight;
      partIndex++;
    }
    await page.screenshot({ path: join(OUT_DIR, '04_selected_document_fullpage.png'), fullPage: true });

    // Scroll back to top
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await page.waitForTimeout(1000);

    // 6. Capture Ask Document (interactive chat drawer on paper page)
    console.log(`📸 5. Capturing Ask Document / Chat drawer on ${paperPath}...`);
    const railInput = page.locator('input[placeholder*="What would you like to know"], input[name="rail-question"]');
    if (await railInput.isVisible()) {
      await railInput.fill('What is the primary contribution of this research?');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(6000);
    }
    await page.screenshot({ path: join(OUT_DIR, '07_ask_document.png'), fullPage: false });

    // 7. Capture Pipeline Runs List and discover real run
    console.log('📸 6. Capturing Pipeline Runs List...');
    await gotoWithRetry(page, `${BASE_URL}/runs`);
    await page.waitForTimeout(3000);
    await page.screenshot({ path: join(OUT_DIR, '05_pipeline_runs.png'), fullPage: false });

    let runPath = '/runs/64e8eeec-1c75-4e50-ac95-54a8c99ac175';
    const runLinks = await page.locator('a[href^="/runs/"]').all();
    if (runLinks.length > 0) {
      runPath = await runLinks[0].getAttribute('href');
      console.log(`🎯 Discovered active run route: ${runPath}`);
    }

    // 8. Capture Run Details
    console.log(`📸 7. Capturing Run Details (${runPath})...`);
    await gotoWithRetry(page, `${BASE_URL}${runPath}`);
    await page.waitForTimeout(3000);
    await page.screenshot({ path: join(OUT_DIR, '06_run_details.png'), fullPage: false });
    await page.screenshot({ path: join(OUT_DIR, '06_run_details_fullpage.png'), fullPage: true });

    // Clean up stale part screenshots if total parts was less than 5
    if (partIndex <= 4) {
      const { unlink } = await import('node:fs/promises');
      await unlink(join(OUT_DIR, '04_selected_document_part5.png')).catch(() => {});
    }

    console.log('🎉 All screenshots successfully captured in:', OUT_DIR);
  } catch (err) {
    console.error('❌ Error during capture:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
