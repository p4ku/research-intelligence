import { chromium } from '../frontend/node_modules/playwright';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync, mkdirSync } from 'node:fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT_DIR = resolve(__dirname, '..');
const BASE_URL = 'https://research-scanner.schwarz/admin';
const OUT_DIR = resolve(ROOT_DIR, 'docs/user_documentation/images');

if (!existsSync(OUT_DIR)) {
  mkdirSync(OUT_DIR, { recursive: true });
}

async function run() {
  console.log('🚀 Connecting to production Django Admin to capture screenshots...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();

  // 1. Login page (before authentication)
  console.log('📸 01_login_page.png');
  await page.goto(`${BASE_URL}/login/?next=/admin/`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '01_login_page.png'), fullPage: false });

  // Perform login
  console.log('🔑 Logging in as admin on production...');
  await page.fill('input[name="username"]', 'admin');
  await page.fill('input[name="password"]', 'schwarz123!');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('input[type="submit"]'),
  ]);

  // 2. Admin dashboard
  console.log('📸 02_admin_dashboard.png');
  await page.goto(`${BASE_URL}/`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '02_admin_dashboard.png'), fullPage: true });

  // 3. Workspaces list
  console.log('📸 03_workspaces_list.png');
  await page.goto(`${BASE_URL}/research_intelligence/workspace/`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '03_workspaces_list.png'), fullPage: true });

  // Find first workspace link or specific workspace
  const workspaceLinks = await page.$$eval('#result_list tbody tr th a', els => els.map(e => (e as HTMLAnchorElement).href));
  const firstWsUrl = workspaceLinks[0] || `${BASE_URL}/research_intelligence/workspace/`;

  // 4. Add workspace form
  console.log('📸 04_add_workspace_form.png');
  await page.goto(`${BASE_URL}/research_intelligence/workspace/add/`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '04_add_workspace_form.png'), fullPage: false });

  // 5. Workspace detail
  console.log(`📸 04_workspace_detail.png (${firstWsUrl})`);
  await page.goto(firstWsUrl, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '04_workspace_detail.png'), fullPage: true });

  // 6. Scrapers list
  console.log('📸 05_scrapers_list.png');
  await page.goto(`${BASE_URL}/research_intelligence/scraper/`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '05_scrapers_list.png'), fullPage: true });

  // 7. Scraper add form
  console.log('📸 05b_add_scraper_form.png');
  await page.goto(`${BASE_URL}/research_intelligence/scraper/add/`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '05b_add_scraper_form.png'), fullPage: true });

  // 8. Extraction definitions list
  console.log('📸 06_extraction_definitions_list.png');
  await page.goto(`${BASE_URL}/research_intelligence/extractiondefinition/`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '06_extraction_definitions_list.png'), fullPage: true });

  const edLinks = await page.$$eval('#result_list tbody tr th a', els => els.map(e => (e as HTMLAnchorElement).href));
  const firstEdUrl = edLinks[0] || `${BASE_URL}/research_intelligence/extractiondefinition/`;

  // 9. Add Extraction Definition form
  console.log('📸 06b_add_extraction_def_form.png');
  await page.goto(`${BASE_URL}/research_intelligence/extractiondefinition/add/`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '06b_add_extraction_def_form.png'), fullPage: false });

  // 10. Extraction definition detail
  console.log(`📸 06b_extraction_def_detail.png (${firstEdUrl})`);
  await page.goto(firstEdUrl, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '06b_extraction_def_detail.png'), fullPage: true });

  // 11. Pipeline run add form (Add research agent / run form)
  console.log('📸 07b_add_research_agent_form.png');
  await page.goto(`${BASE_URL}/research_intelligence/pipelinerun/add/`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '07b_add_research_agent_form.png'), fullPage: false });

  // 12. Pipeline runs list
  console.log('📸 08_pipeline_runs_list.png');
  await page.goto(`${BASE_URL}/research_intelligence/pipelinerun/`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '08_pipeline_runs_list.png'), fullPage: true });

  const runLinks = await page.$$eval('#result_list tbody tr th a', els => els.map(e => (e as HTMLAnchorElement).href));
  const firstRunUrl = runLinks[0] || `${BASE_URL}/research_intelligence/pipelinerun/`;

  // 13. Pipeline run detail
  console.log(`📸 08b_pipeline_run_detail.png (${firstRunUrl})`);
  await page.goto(firstRunUrl, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '08b_pipeline_run_detail.png'), fullPage: true });

  // 14. Papers list
  console.log('📸 09_papers_list.png');
  await page.goto(`${BASE_URL}/research_intelligence/paper/`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '09_papers_list.png'), fullPage: true });

  const paperLinks = await page.$$eval('#result_list tbody tr th a', els => els.map(e => (e as HTMLAnchorElement).href));
  const firstPaperUrl = paperLinks[0] || `${BASE_URL}/research_intelligence/paper/`;

  // 15. Paper detail
  console.log(`📸 10_paper_detail.png (${firstPaperUrl})`);
  await page.goto(firstPaperUrl, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '10_paper_detail.png'), fullPage: true });

  // 16. Extractions list
  console.log('📸 11_extractions_list.png');
  await page.goto(`${BASE_URL}/research_intelligence/extraction/`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '11_extractions_list.png'), fullPage: true });

  const extLinks = await page.$$eval('#result_list tbody tr th a', els => els.map(e => (e as HTMLAnchorElement).href));
  const firstExtUrl = extLinks[0] || `${BASE_URL}/research_intelligence/extraction/`;

  // 17. Extraction detail
  console.log(`📸 11b_extraction_detail.png (${firstExtUrl})`);
  await page.goto(firstExtUrl, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '11b_extraction_detail.png'), fullPage: true });

  // 18. Storage browser
  console.log('📸 12_storage_browser.png');
  await page.goto(`${BASE_URL}/storage-browser/`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: resolve(OUT_DIR, '12_storage_browser.png'), fullPage: false });

  await browser.close();
  console.log('🎉 Successfully captured all production Django Admin screenshots!');
}

run().catch((err) => {
  console.error('❌ Failed capturing production screenshots:', err);
  process.exit(1);
});
