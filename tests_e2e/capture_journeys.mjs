import { chromium } from '../frontend/node_modules/playwright/index.mjs';
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


    // 5. Capture Selected Document (Paper detail) — 4 clean semantic parts and fullpage
    console.log(`📸 4. Capturing Selected Document Details (${paperPath})...`);
    await gotoWithRetry(page, `${BASE_URL}${paperPath}`);
    await page.waitForTimeout(3000);
    await page.screenshot({ path: join(OUT_DIR, '04_selected_document.png'), fullPage: false });
    await page.screenshot({ path: join(OUT_DIR, '04_selected_document_fullpage.png'), fullPage: true });

    // Part 1: Top (Masthead, Authors, Badges, TLDR, Scorecard)
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await page.waitForTimeout(500);
    await page.screenshot({ path: join(OUT_DIR, '04_selected_document_part1.png'), fullPage: false });

    // Part 2: Technology Readiness Level (TRL)
    const trlPos = await page.evaluate(() => {
      const el = Array.from(document.querySelectorAll('h2')).find(h => h.innerText.includes('TECHNOLOGY READINESS LEVEL'));
      return el ? Math.round(el.getBoundingClientRect().top + window.scrollY) - 36 : 890;
    });
    await page.evaluate((y) => window.scrollTo({ top: y, behavior: 'instant' }), trlPos);
    await page.waitForTimeout(500);
    await page.screenshot({ path: join(OUT_DIR, '04_selected_document_part2.png'), fullPage: false });

    // Part 3: Schwarz Fit Synergies & Enterprise Applicability
    const fitPos = await page.evaluate(() => {
      const el = Array.from(document.querySelectorAll('h2')).find(h => h.innerText.includes('SCHWARZ FIT'));
      return el ? Math.round(el.getBoundingClientRect().top + window.scrollY) - 36 : 1260;
    });
    await page.evaluate((y) => window.scrollTo({ top: y, behavior: 'instant' }), fitPos);
    await page.waitForTimeout(500);
    await page.screenshot({ path: join(OUT_DIR, '04_selected_document_part3.png'), fullPage: false });

    // Part 4: Research Metric & Provenance Footer
    await page.evaluate(() => {
      document.body.style.paddingBottom = '220px';
      const el = Array.from(document.querySelectorAll('h2')).find(h => h.innerText.includes('RESEARCH METRIC'));
      const y = el ? Math.round(el.getBoundingClientRect().top + window.scrollY) - 36 : 2060;
      window.scrollTo({ top: y, behavior: 'instant' });
    });
    await page.waitForTimeout(500);
    await page.screenshot({ path: join(OUT_DIR, '04_selected_document_part4.png'), fullPage: false });

    // Reset scroll & padding
    await page.evaluate(() => {
      document.body.style.paddingBottom = '';
      window.scrollTo({ top: 0, behavior: 'instant' });
    });
    await page.waitForTimeout(800);

    // 6. Capture Ask Document (interactive chat drawer on paper page)
    console.log(`📸 5. Capturing Ask Document / Chat drawer on ${paperPath}...`);
    const newChatBtn = page.locator('button[aria-label="New chat"], button[title="New chat"]');
    if (await newChatBtn.isVisible()) {
      await newChatBtn.click();
      await page.waitForTimeout(800);
    }
    const railInput = page.locator('input[placeholder*="What would you like to know"], input[name="rail-question"]');
    if (await railInput.isVisible()) {
      await railInput.fill('What is the primary contribution of this research?');
      const sendBtn = page.locator('button[aria-label="Send"], button:has-text("Send"), button[title="Send"]').first();
      if (await sendBtn.isVisible()) {
        await sendBtn.click();
      } else {
        await page.keyboard.press('Enter');
      }
      for (let i = 0; i < 40; i++) {
        await page.waitForTimeout(1000);
        const bodyText = await page.innerText('body');
        const isAnswering = bodyText.includes('Answering…');
        const stopVisible = await page.locator('button:has-text("Stop"), button[aria-label="Stop"]').isVisible().catch(() => false);
        if (!isAnswering && !stopVisible && i > 4) break;
      }
      await page.waitForTimeout(1000);
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

    // 9. Capture Paper Comments & Collaboration (Journey 08)
    console.log('📸 8. Capturing Paper Comments & Annotator Collaboration...');
    const commentsTargetUrl = `${BASE_URL}/papers/e44ebd1f-badb-4a42-b48c-646e40cef878?run=156d9041-7c83-4127-82a6-e6329a568d95`;
    try {
      await gotoWithRetry(page, commentsTargetUrl);
    } catch {
      await gotoWithRetry(page, `${BASE_URL}${paperPath}`);
    }
    await page.waitForTimeout(3000);

    // Expand comments console if collapsed
    let isConsoleOpen = await page.locator('div[data-shape="paper-comments-console"]').isVisible().catch(() => false);
    if (!isConsoleOpen) {
      console.log('📂 Opening paper comments console via #comments button...');
      const expandCommentsBtn = page.locator('#comments button, [data-shape="paper-comments-card"] button').first();
      if (await expandCommentsBtn.isVisible()) {
        await expandCommentsBtn.click();
        await page.waitForTimeout(2000);
      }
    }

    // Post 3 structured demo comments
    const commentsToAdd = [
      '**Architecture Observation:** ASPIRE state preparation significantly reduces circuit depth compared to standard gate synthesis.',
      'Key advantages for enterprise deployment:\n* 7.7x shallower circuit depth\n* Native hardware connectivity preservation\n* Validated against Oxford quantum clusters',
      'Should we upgrade the TRL level from 4 to 5 based on the hardware validation in Section IV?',
    ];

    const composerTextarea = page.locator('div[data-shape="paper-comments-console"] textarea, textarea[placeholder*="comment" i]').first();
    const commentSubmitBtn = page.locator('div[data-shape="paper-comments-console"] button[type="submit"], button:has-text("Comment")').first();

    if (await composerTextarea.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log('✍️ Posting demo comments with Markdown...');
      for (const msg of commentsToAdd) {
        await composerTextarea.fill(msg);
        await commentSubmitBtn.click();
        await page.waitForTimeout(1500);
      }

      // Add emoji reactions to comments
      console.log('😀 Adding emoji reactions to demo comments...');
      const emojis = ['👍', '🚀', '💡'];
      const articles = await page.locator('div[data-shape="paper-comments-console"] article').all();
      for (let i = 0; i < Math.min(articles.length, emojis.length); i++) {
        try {
          const reactBtn = articles[i].locator('button[aria-label="Add reaction"], button[title="Add reaction"]').first();
          if (await reactBtn.isVisible()) {
            await reactBtn.click();
            await page.waitForTimeout(500);
            const emojiBtn = page.locator(`button:has-text("${emojis[i]}")`).first();
            if (await emojiBtn.isVisible()) {
              await emojiBtn.click();
              await page.waitForTimeout(600);
            }
          }
        } catch (e) {
          console.log(`Note on reaction ${i}: ${e.message}`);
        }
      }

      await page.waitForTimeout(1500);
      // Capture 08_paper_comments.png showing open comments with reactions
      console.log('📸 Snapping 08_paper_comments.png with expanded comments and reactions...');
      await page.screenshot({ path: join(OUT_DIR, '08_paper_comments.png'), fullPage: false });

      // Clean up demo comments
      console.log('🧹 Cleaning up demo comments...');
      for (let i = 0; i < commentsToAdd.length; i++) {
        const deleteBtn = page.locator('button[aria-label="Delete comment"]').first();
        if (await deleteBtn.isVisible()) {
          await deleteBtn.click();
          await page.waitForTimeout(500);
          const confirmBtn = page.locator('button:has-text("Delete comment"), button:has-text("Delete")').last();
          if (await confirmBtn.isVisible()) {
            await confirmBtn.click();
            await page.waitForTimeout(1000);
          }
        }
      }
    } else {
      console.log('⚠️ Composer textarea was not visible, snapping current state...');
      await page.screenshot({ path: join(OUT_DIR, '08_paper_comments.png'), fullPage: false });
    }

    // 10. Capture All Papers Directory / Corpus (Journey 09)
    console.log('📸 9. Capturing All Papers Directory (/papers)...');
    await gotoWithRetry(page, `${BASE_URL}/papers`);
    console.log('⏳ Waiting at least 18 seconds for /papers corpus data to arrive...');
    await page.waitForTimeout(18000);
    await page.waitForSelector('a[href^="/papers/"]', { timeout: 30000 }).catch(() => {
      console.log('⚠️ Paper links selector still resolving after 18s...');
    });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: join(OUT_DIR, '09_all_papers.png'), fullPage: false });
    await page.screenshot({ path: join(OUT_DIR, '09_all_papers_fullpage.png'), fullPage: true });

    // Clean up stale part5 screenshot if present
    const { unlink } = await import('node:fs/promises');
    await unlink(join(OUT_DIR, '04_selected_document_part5.png')).catch(() => {});

    console.log('🎉 All screenshots successfully captured in:', OUT_DIR);
  } catch (err) {
    console.error('❌ Error during capture:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
