import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';

const BASE_URL = 'https://research-scanner.schwarz';
const USER = 'admin';
const PASSWORD = 'schwarz123!';
const OUT_DIR = join(process.cwd(), 'docs', 'user_journeys', 'screenshots');

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
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
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
    await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: join(OUT_DIR, '02_dashboard.png'), fullPage: false });

    // 4. Capture Briefings Archive
    console.log('📸 3. Capturing Briefings Archive...');
    await page.goto(`${BASE_URL}/briefing`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: join(OUT_DIR, '03_briefings.png'), fullPage: false });

    // 5. Capture Selected Document (Paper detail) — Top, Scroll Sequence, and Fullpage
    console.log('📸 4. Capturing Selected Document Details...');
    const paperId = '1dab6d06-d931-423d-9472-95a1eba3b616';
    await page.goto(`${BASE_URL}/papers/${paperId}`, { waitUntil: 'networkidle' });
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
      await page.waitForTimeout(500);
      await page.screenshot({ path: join(OUT_DIR, `04_selected_document_part${partIndex}.png`), fullPage: false });
      if (currentScroll + viewportHeight >= scrollHeight) break;
      currentScroll += scrollStep;
      if (currentScroll + viewportHeight > scrollHeight) currentScroll = scrollHeight - viewportHeight;
      partIndex++;
    }
    await page.screenshot({ path: join(OUT_DIR, '04_selected_document_fullpage.png'), fullPage: true });

    // 6. Capture Pipeline Runs List
    console.log('📸 5. Capturing Pipeline Runs List...');
    await page.goto(`${BASE_URL}/runs`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: join(OUT_DIR, '05_pipeline_runs.png'), fullPage: false });

    // 7. Capture Run Details
    console.log('📸 6. Capturing Run Details...');
    const runId = '1243db08-42bd-44a3-95fc-f5ee4664c181';
    await page.goto(`${BASE_URL}/runs/${runId}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: join(OUT_DIR, '06_run_details.png'), fullPage: false });

    // 7. Capture Ask Document (interactive chat drawer on paper page)
    console.log('📸 7. Capturing Ask Document / Chat drawer...');
    await page.goto(`${BASE_URL}/papers/${paperId}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);
    const railInput = page.locator('input[name="rail-question"]');
    if (await railInput.isVisible()) {
      await railInput.fill('What is the primary contribution of RushHour architecture?');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(5000);
    }
    await page.screenshot({ path: join(OUT_DIR, '07_ask_document.png'), fullPage: false });

    console.log('🎉 All 7 distinct screenshots successfully captured in:', OUT_DIR);
  } catch (err) {
    console.error('❌ Error during capture:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
