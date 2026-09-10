import { readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { chromium } from '@playwright/test';
import { marked } from 'marked';

const BASE_DIR = join(process.cwd(), 'docs', 'user_journeys');
const OUT_PDF = join(BASE_DIR, 'Schwarz_Research_Intelligence_User_Journeys.pdf');
const OUT_HTML = join(BASE_DIR, 'preview_user_journeys.html');

// Helper to convert image paths to base64 data URIs
function inlineImages(markdown, docDir) {
  return markdown.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, alt, src) => {
    // Only handle local relative image paths
    if (src.startsWith('http://') || src.startsWith('https://')) return match;
    
    // Clean query params or anchors if any
    const cleanSrc = src.split('?')[0].split('#')[0];
    const absPath = join(docDir, cleanSrc);
    
    if (existsSync(absPath)) {
      const ext = absPath.endsWith('.png') ? 'png' : absPath.endsWith('.jpg') || absPath.endsWith('.jpeg') ? 'jpeg' : 'svg+xml';
      const base64 = readFileSync(absPath).toString('base64');
      return `![${alt}](data:image/${ext};base64,${base64})`;
    } else {
      console.warn(`⚠️ Warning: Image file not found: ${absPath}`);
      return match;
    }
  });
}

// Transform GitHub style blockquote alerts: > [!NOTE], > [!IMPORTANT]
function transformAlerts(markdown) {
  return markdown.replace(
    /^>\s*\[!(NOTE|IMPORTANT|TIP|WARNING|CAUTION)\]\s*\n((?:>.*\n?)*)/gim,
    (match, type, content) => {
      const cleanContent = content.replace(/^>\s?/gm, '');
      const lowerType = type.toLowerCase();
      return `<div class="callout callout-${lowerType}"><div class="callout-title">${type}</div><div class="callout-body">\n\n${cleanContent}\n\n</div></div>\n\n`;
    }
  );
}

// Convert markdown file to processed HTML
function renderMarkdownFile(filename) {
  const filePath = join(BASE_DIR, filename);
  if (!existsSync(filePath)) {
    console.error(`Missing file: ${filePath}`);
    return '';
  }
  let md = readFileSync(filePath, 'utf-8');
  md = inlineImages(md, BASE_DIR);
  md = transformAlerts(md);
  return marked.parse(md);
}

async function main() {
  console.log('🔄 Building combined HTML for User Journeys...');

  const sections = [
    { title: 'Executive Introduction & Overview', file: 'README.md', id: 'overview' },
    { title: 'User Journey 01: Authentication & Login', file: '01_login.md', id: 'journey-01' },
    { title: 'User Journey 02: Executive Dashboard', file: '02_dashboard.md', id: 'journey-02' },
    { title: 'User Journey 03: Briefings Archive', file: '03_briefings.md', id: 'journey-03' },
    { title: 'User Journey 04: Selected Document Deep-Dive', file: '04_selected_document.md', id: 'journey-04' },
    { title: 'User Journey 05: Pipeline Runs Overview', file: '05_pipeline_runs.md', id: 'journey-05' },
    { title: 'User Journey 06: Pipeline Run Details & Execution DAG', file: '06_run_details.md', id: 'journey-06' },
    { title: 'User Journey 07: Ask Document Grounded AI Interrogation', file: '07_ask_document.md', id: 'journey-07' },
    { title: 'Appendix A: User Personas & Access Boundaries', file: 'personas.md', id: 'appendix-a' },
    { title: 'Appendix B: Route Hierarchy & Context Resolution Matrix', file: 'route_matrix.md', id: 'appendix-b' },
  ];

  let bodyHtml = '';

  for (const sec of sections) {
    console.log(`  📄 Processing ${sec.file}...`);
    const contentHtml = renderMarkdownFile(sec.file);
    bodyHtml += `
      <section class="doc-section" id="${sec.id}">
        ${contentHtml}
      </section>
    `;
  }

  const fullHtml = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Schwarz Research Intelligence (SRI) — Web Interface User Journeys</title>
  <style>
    @page {
      size: A4;
      margin: 18mm 16mm 18mm 16mm;
    }

    *, *::before, *::after {
      box-sizing: border-box;
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: #1e293b;
      background: #ffffff;
      line-height: 1.55;
      font-size: 11pt;
      margin: 0;
      padding: 0;
      -webkit-font-smoothing: antialiased;
    }

    /* Cover Page */
    .cover-page {
      page-break-after: always;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-height: 250mm;
      padding: 30mm 10mm 15mm 10mm;
      border-bottom: 3px solid #0284c7;
    }

    .cover-brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 13pt;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #0284c7;
    }

    .cover-brand svg {
      width: 32px;
      height: 32px;
      fill: none;
      stroke: #0284c7;
      stroke-width: 2;
    }

    .cover-hero {
      margin-top: 40mm;
    }

    .cover-title {
      font-size: 30pt;
      font-weight: 800;
      line-height: 1.15;
      color: #0f172a;
      margin: 0 0 16px 0;
      letter-spacing: -0.02em;
    }

    .cover-subtitle {
      font-size: 14pt;
      line-height: 1.4;
      color: #475569;
      margin: 0 0 32px 0;
      font-weight: 400;
    }

    .meta-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;
      margin-top: 24px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 20px;
    }

    .meta-item {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .meta-label {
      font-size: 8.5pt;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #64748b;
      font-weight: 600;
    }

    .meta-value {
      font-size: 11pt;
      font-weight: 600;
      color: #0f172a;
    }

    .cover-footer {
      margin-top: auto;
      font-size: 9pt;
      color: #94a3b8;
      display: flex;
      justify-content: space-between;
      border-top: 1px solid #e2e8f0;
      padding-top: 14px;
    }

    /* Table of Contents */
    .toc-page {
      page-break-after: always;
      padding-top: 10mm;
    }

    .toc-title {
      font-size: 20pt;
      font-weight: 700;
      color: #0f172a;
      margin-bottom: 24px;
      border-bottom: 2px solid #0284c7;
      padding-bottom: 8px;
    }

    .toc-list {
      list-style: none;
      padding: 0;
      margin: 0;
    }

    .toc-item {
      display: flex;
      justify-content: space-between;
      padding: 12px 0;
      border-bottom: 1px dashed #cbd5e1;
      font-size: 11pt;
    }

    .toc-item a {
      color: #0f172a;
      text-decoration: none;
      font-weight: 500;
    }

    .toc-tag {
      color: #0284c7;
      font-weight: 600;
      font-size: 9.5pt;
      margin-right: 8px;
    }

    /* Content Layout */
    .doc-section {
      page-break-before: always;
      padding-top: 4mm;
    }

    h1 {
      font-size: 20pt;
      font-weight: 700;
      color: #0f172a;
      letter-spacing: -0.02em;
      margin-top: 0;
      margin-bottom: 18px;
      border-bottom: 2px solid #e2e8f0;
      padding-bottom: 10px;
    }

    h2 {
      font-size: 14pt;
      font-weight: 600;
      color: #1e293b;
      margin-top: 26px;
      margin-bottom: 12px;
      page-break-after: avoid;
    }

    h3 {
      font-size: 12pt;
      font-weight: 600;
      color: #334155;
      margin-top: 20px;
      margin-bottom: 10px;
      page-break-after: avoid;
    }

    h4 {
      font-size: 11pt;
      font-weight: 600;
      color: #475569;
      margin-top: 16px;
      margin-bottom: 8px;
      page-break-after: avoid;
    }

    p {
      margin-top: 0;
      margin-bottom: 12px;
    }

    ul, ol {
      margin-top: 0;
      margin-bottom: 14px;
      padding-left: 24px;
    }

    li {
      margin-bottom: 5px;
    }

    /* Images and Screenshots */
    img {
      max-width: 100%;
      height: auto;
      max-height: 480px;
      object-fit: contain;
      display: block;
      margin: 18px auto;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
      page-break-inside: avoid;
    }

    /* Code and Preformatted */
    code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 9.5pt;
      background: #f1f5f9;
      color: #0369a1;
      padding: 2px 5px;
      border-radius: 4px;
      border: 1px solid #e2e8f0;
    }

    pre {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 8.5pt;
      background: #0f172a;
      color: #f8fafc;
      padding: 14px 16px;
      border-radius: 6px;
      overflow-x: auto;
      margin: 16px 0;
      line-height: 1.45;
      page-break-inside: avoid;
    }

    pre code {
      background: transparent;
      color: inherit;
      padding: 0;
      border: none;
    }

    /* Tables */
    table {
      width: 100%;
      border-collapse: collapse;
      margin: 18px 0;
      font-size: 9.5pt;
      page-break-inside: avoid;
    }

    th, td {
      border: 1px solid #cbd5e1;
      padding: 8px 12px;
      text-align: left;
      vertical-align: top;
    }

    th {
      background: #f1f5f9;
      color: #0f172a;
      font-weight: 600;
    }

    tr:nth-child(even) td {
      background: #f8fafc;
    }

    /* Blockquotes & Callouts */
    blockquote {
      margin: 16px 0;
      padding: 12px 18px;
      border-left: 4px solid #0284c7;
      background: #f0f9ff;
      color: #0369a1;
      border-radius: 0 6px 6px 0;
      font-size: 10pt;
      page-break-inside: avoid;
    }

    .callout {
      margin: 18px 0;
      padding: 14px 18px;
      border-radius: 6px;
      page-break-inside: avoid;
      font-size: 10pt;
    }

    .callout-important {
      border-left: 4px solid #f59e0b;
      background: #fffbeb;
      color: #92400e;
    }

    .callout-note {
      border-left: 4px solid #0284c7;
      background: #f0f9ff;
      color: #0369a1;
    }

    .callout-title {
      font-weight: 700;
      text-transform: uppercase;
      font-size: 8.5pt;
      letter-spacing: 0.05em;
      margin-bottom: 6px;
    }

    .callout-body p {
      margin-bottom: 6px;
    }
    .callout-body p:last-child {
      margin-bottom: 0;
    }

    /* Horizontal Rules */
    hr {
      border: none;
      border-top: 1px solid #e2e8f0;
      margin: 24px 0;
    }
  </style>
</head>
<body>

  <!-- Cover Page -->
  <div class="cover-page">
    <div class="cover-brand">
      <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/></svg>
      Schwarz Research Intelligence
    </div>

    <div class="cover-hero">
      <h1 class="cover-title">Web Interface User Journeys</h1>
      <div class="cover-subtitle">
        Comprehensive End-to-End Workflows, Interaction Topologies & Production Screen Specifications
      </div>

      <div class="meta-grid">
        <div class="meta-item">
          <span class="meta-label">Target Platform</span>
          <span class="meta-value">https://research-scanner.schwarz</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">System Deployment</span>
          <span class="meta-value">v0.1.358 (Production)</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Publication Date</span>
          <span class="meta-value">10 September 2026</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Scope</span>
          <span class="meta-value">Journeys 01–07 & Architecture Appendices</span>
        </div>
      </div>
    </div>

    <div class="cover-footer">
      <span>SCHWARZ DIGITS · RESEARCH & INNOVATION LAB</span>
      <span>CONFIDENTIAL & PROPRIETARY</span>
    </div>
  </div>

  <!-- Table of Contents Page -->
  <div class="toc-page">
    <div class="toc-title">Document Structure & Table of Contents</div>
    <ul class="toc-list">
      <li class="toc-item">
        <span><span class="toc-tag">OVERVIEW</span> Executive Introduction & Topology Index</span>
        <span>Section 0</span>
      </li>
      <li class="toc-item">
        <span><span class="toc-tag">JOURNEY 01</span> Authentication & Credentialed Entry</span>
        <span>Route: /login</span>
      </li>
      <li class="toc-item">
        <span><span class="toc-tag">JOURNEY 02</span> Executive Dashboard & Workspace Hub</span>
        <span>Route: /dashboard</span>
      </li>
      <li class="toc-item">
        <span><span class="toc-tag">JOURNEY 03</span> Briefings Archive & Multi-Run History</span>
        <span>Route: /briefing</span>
      </li>
      <li class="toc-item">
        <span><span class="toc-tag">JOURNEY 04</span> Selected Document Deep-Dive & Scoring (RushHour)</span>
        <span>Route: /papers/[id]</span>
      </li>
      <li class="toc-item">
        <span><span class="toc-tag">JOURNEY 05</span> Pipeline Runs Overview & Telemetry Ledger</span>
        <span>Route: /runs</span>
      </li>
      <li class="toc-item">
        <span><span class="toc-tag">JOURNEY 06</span> Pipeline Run Details & 9-Stage Execution DAG</span>
        <span>Route: /runs/[id]</span>
      </li>
      <li class="toc-item">
        <span><span class="toc-tag">JOURNEY 07</span> Ask Document Grounded AI Interrogation Drawer</span>
        <span>Route: /papers/[id]</span>
      </li>
      <li class="toc-item">
        <span><span class="toc-tag">APPENDIX A</span> User Personas & Access Boundaries (Manager vs Researcher)</span>
        <span>Specification</span>
      </li>
      <li class="toc-item">
        <span><span class="toc-tag">APPENDIX B</span> Route Hierarchy & Context Resolution Matrix</span>
        <span>Specification</span>
      </li>
    </ul>
  </div>

  <!-- Main Body Content -->
  ${bodyHtml}

</body>
</html>
  `;

  const { writeFileSync } = await import('node:fs');
  writeFileSync(OUT_HTML, fullHtml, 'utf-8');
  console.log(`💾 Saved intermediate standalone HTML: ${OUT_HTML}`);

  console.log('🚀 Launching Playwright to render high-resolution PDF...');
  const execPath = existsSync('/Users/piotr/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell')
    ? '/Users/piotr/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell'
    : '/Users/piotr/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
  
  console.log(`  Using browser binary: ${execPath}`);
  const browser = await chromium.launch({ executablePath: execPath, headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.setContent(fullHtml, { waitUntil: 'load' });
  await page.waitForTimeout(2000);

  console.log('🖨️ Printing PDF document...');
  await page.pdf({
    path: OUT_PDF,
    format: 'A4',
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: `
      <div style="font-size: 7.5pt; color: #94a3b8; font-family: -apple-system, BlinkMacSystemFont, sans-serif; width: 100%; display: flex; justify-content: space-between; padding: 0 16mm;">
        <span>Schwarz Research Intelligence (SRI)</span>
        <span>Web Interface User Journeys & Screen Specifications</span>
      </div>
    `,
    footerTemplate: `
      <div style="font-size: 7.5pt; color: #94a3b8; font-family: -apple-system, BlinkMacSystemFont, sans-serif; width: 100%; display: flex; justify-content: space-between; padding: 0 16mm;">
        <span>CONFIDENTIAL · SCHWARZ DIGITS</span>
        <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
      </div>
    `,
    margin: {
      top: '16mm',
      bottom: '16mm',
      left: '16mm',
      right: '16mm',
    },
  });

  await browser.close();
  console.log(`🎉 Successfully generated complete unified PDF:`);
  console.log(`📍 ${OUT_PDF}`);
}

main().catch((err) => {
  console.error('❌ Error generating PDF:', err);
  process.exit(1);
});
