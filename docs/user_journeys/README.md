# Schwarz Research Intelligence (SRI) — Web Interface User Journeys

Welcome to the comprehensive user journey documentation for the **Schwarz Research Intelligence (SRI)** web platform. This repository section documents the complete end-to-end user workflows, interactive screen topologies, and operational interfaces captured directly from the live production deployment (`https://research-scanner.schwarz` / `https://sri-prod.apps.01.cf.eu01.onstackit.cloud`).

---

## 🗺️ User Journey Documentation Index

The user journeys are documented in dedicated, modular specifications corresponding to each primary application view:

| # | User Journey | Route | Key Features & Focus | Documentation |
| :-: | :--- | :--- | :--- | :--- |
| **01** | **Authentication & Login** | `/` or `/login` | Credentialed entry, token refresh, security notices, radar scan backdrop | 📖 [01_login.md](./01_login.md) |
| **02** | **Executive Dashboard** | `/dashboard` | Recent briefings ledger, multi-run preservation, ad-hoc briefing trigger | 📖 [02_dashboard.md](./02_dashboard.md) |
| **03** | **Briefings Archive** | `/briefing` | Domain filter chips, multi-run history, screening yields, edition previews | 📖 [03_briefings.md](./03_briefings.md) |
| **04** | **Selected Document** | `/papers/[id]` | Paper metadata, TUM ecosystem/GDPR compliance badges, scorecard, radar chart | 📖 [04_selected_document.md](./04_selected_document.md) |
| **05** | **Pipeline Runs** | `/runs` | Global KPIs (spend, volume, pass rate), status tabs, complete run audit ledger | 📖 [05_pipeline_runs.md](./05_pipeline_runs.md) |
| **06** | **Run Details** | `/runs/[id]` | Deep-dive telemetry, token counts, dollar costs, scraper yield & DAG stages | 📖 [06_run_details.md](./06_run_details.md) |
| **07** | **Ask Document** | `/papers/[id]` | Full-text grounded AI interrogation drawer, visual citations, live streaming | 📖 [07_ask_document.md](./07_ask_document.md) |
| **08** | **Paper Comments & Collaboration** | `/papers/[id]` | Threaded message feed, Markdown annotations, consensus emoji reactions (👍, 💡, 🚀) | 📖 [08_paper_comments.md](./08_paper_comments.md) |
| **09** | **All Papers Corpus** | `/papers` | Cross-domain literature repository, multi-faceted filtering, sorting, pagination | 📖 [09_all_papers.md](./09_all_papers.md) |

---

## 📸 Production Screenshot Gallery

All screenshots were captured against the live production environment using automated Playwright tests (`tests_e2e/capture_journeys.mjs`) authenticated with the production administrative credentials:

1. **Login Page**: [`./screenshots/01_login.png`](./screenshots/01_login.png)
2. **Dashboard**: [`./screenshots/02_dashboard.png`](./screenshots/02_dashboard.png)
3. **Briefings Archive**: [`./screenshots/03_briefings.png`](./screenshots/03_briefings.png)
4. **Selected Document (Sequential Scroll Steps & Full-Page)**:
   - Step 1 (Masthead, Badges, Abstract, Scorecard & Radar): [`./screenshots/04_selected_document_part1.png`](./screenshots/04_selected_document_part1.png)
   - Step 2 (Assessment Kickoff & Research Metric Facets): [`./screenshots/04_selected_document_part2.png`](./screenshots/04_selected_document_part2.png)
   - Step 3 (Schwarz Strategic Fit & Synergies): [`./screenshots/04_selected_document_part3.png`](./screenshots/04_selected_document_part3.png)
   - Step 4 (Strategic Need Match, TRL Classification & Provenance Footer): [`./screenshots/04_selected_document_part4.png`](./screenshots/04_selected_document_part4.png)
   - Complete Full-Page Overview: [`./screenshots/04_selected_document_fullpage.png`](./screenshots/04_selected_document_fullpage.png)
5. **Pipeline Runs Overview**: [`./screenshots/05_pipeline_runs.png`](./screenshots/05_pipeline_runs.png)
6. **Pipeline Run Details (DAG)**:
   - Executive Telemetry & Top Stages: [`./screenshots/06_run_details.png`](./screenshots/06_run_details.png)
   - Complete 9-Stage DAG Breakdown: [`./screenshots/06_run_details_fullpage.png`](./screenshots/06_run_details_fullpage.png)
7. **Ask Document Interrogation Drawer**: [`./screenshots/07_ask_document.png`](./screenshots/07_ask_document.png)
8. **Paper Comments & Annotator Collaboration**: [`./screenshots/08_paper_comments.png`](./screenshots/08_paper_comments.png)
9. **All Papers Directory / Corpus Catalog**:
   - Executive Viewport: [`./screenshots/09_all_papers.png`](./screenshots/09_all_papers.png)
   - Full-Page Catalog: [`./screenshots/09_all_papers_fullpage.png`](./screenshots/09_all_papers_fullpage.png)

---

## 👥 Target Personas & Primary Objectives

- **Executive & Research Lead (Manager)**:
  - Quickly reviews morning briefings on `/dashboard` and `/briefing`.
  - Audits pipeline operational spend and screening selectivity on `/runs`.
  - Triggers ad-hoc domain scans via the **New Briefing** panel.
- **Intelligence Analyst & Researcher (Analyst)**:
  - Drills into high-signal scientific literature on `/papers/[id]`.
  - Evaluates technology readiness (TRL 1–9) and strategic Schwarz ecosystem fit.
  - Converses with complex papers using the **Ask Document** interactive assistant.
- **System Administrator / Operations**:
  - Inspects scraper health (arXiv, OpenAlex), deduplication efficiency, and token burn on `/runs/[id]`.

---

## 🔗 Related Architectural Specifications

- 👥 **[personas.md](./personas.md)** — User Personas, Daily Workflows & Permissions Matrix.
- 🧭 **[route_matrix.md](./route_matrix.md)** — URL routes, parameter bindings, and backend API contracts.
- 📐 **[wireframes.md](./wireframes.md)** — Full-fidelity layout wireframes and screen topologies.
- 🗺️ **[user_journeys.md](./user_journeys.md)** — Interaction Architecture & State Transitions.
