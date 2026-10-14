# 🧪 Schwarz Research Intelligence - End-to-End (E2E) Test Suite

State-of-the-art live API test suite and full pipeline simulator for **Schwarz Research Intelligence (SRI)** against **Production**, **Staging**, or **Local** environments.

---

## 🏛️ Architecture & Scenarios

The E2E test suite covers both **Backend REST/MCP Pipelines** and **Next.js Frontend User Journeys**:

### 1. Next.js Frontend User Journeys (TypeScript & Playwright)
Located in `tests_e2e/pages/` and `tests_e2e/specs/`:
* **`pages/`**: Clean Page Object Model abstraction in TypeScript:
  * `LoginPage.ts`: Authentication forms, input handling, and session state.
  * `SidebarNav.ts`: Menu traversing (`/dashboard`, `/briefing`; `/papers` and `/ask` are fixed off, see below), User Menu, and Sign Out.
  * `WorkspaceSwitcher.ts`: Workspace dropdown, listing accessible workspaces, and cookie validation (`rs-workspace`).
  * `SettingsPage.ts`: `/settings` profile form, password form, workspace configuration summary, and notification toggle.
  * `DashboardPage.ts`, `BriefingPage.ts`, `PapersPage.ts`, `AskPage.ts`: Core application surface abstractions.
  * `FeatureToggles.ts`: The account menu's "Demo features" switches (none render while every flag is fixed), plus `addFeatureCookie()` for seeding `rs-features` before a session starts.
* **`specs/`**: Modular, full end-to-end user journey test suites:
  1. `01_auth_session_lifecycle.journey.spec.ts`: Rejection of bad credentials, login, session cookies, deep-link protection, and sign out.
  2. `02_analyst_daily_review.journey.spec.ts`: Today Dashboard funnel metrics, reading executive Briefing, and opening a paper from it (the `/papers` steps left with the flag).
  3. `03_manager_workspace_and_settings.journey.spec.ts`: Multi-tenant workspace switching, `/settings` inspection (Profile, Role, Password, Workspace Metadata), and bilingual EN <-> DE locale toggle.
  4. `04_tuning_read_only.journey.spec.ts`: Read-only tuning inspection of weighted and unweighted ranking dimensions.
  5. `05_interactive_paper_chat.journey.spec.ts`: Deep-dive literature question answering in `/ask`, reasoning engine, and citation stream validation. **Skipped** while `ask` is fixed off.
  6. `06_end_to_end_researcher_flow.journey.spec.ts`: Comprehensive full researcher flow executing the entire application lifecycle end-to-end in a single session.
  7. `07_feature_flags.journey.spec.ts`: The fixed state of the three demo feature flags — `all_papers` and `ask` off, `stars` on, no toggles — and that a cookie cannot move it (see **Demo feature flags** below).
  8. `08_multi_persona_and_full_lifecycle.journey.spec.ts`: End-to-end user journey from API setup (workspaces, scrapers, dynamic extractions) to Dashboard, Runs & 8 steps detail, Briefing (sliders and dimension sorting), Screening Log exclusions, and Paper Scorecard.
  9. `09_run_admission_and_stop_rbac.journey.spec.ts`: Persona permission checks (Researcher launch blocked with 401/403 -> UI pipeline launch -> Admin stops active run via modal -> Rerun button enabled exclusively for Admin).

### Demo feature flags: `all_papers` and `ask` are fixed off, `stars` fixed on

The account menu was built to carry three per-browser switches that hide a feature live and put it back (`docs/design/feature-flags.md`), stored in one readable cookie, `rs-features`, whose value is the `.`-separated list of the flags that are **OFF**.

Since 9 Sep 2026 every flag is **fixed** in the registry (`frontend/src/lib/features.ts`, the `fixed` property): `all_papers` and `ask` are off, `stars` is on. A fixed flag ignores the cookie, is never written to it, and has no menu row, so the "Demo features" section does not render. The product every spec here sees is therefore: three nav rows (`/dashboard`, `/briefing`, `/runs`), `/papers` and `/ask` rendering the shared not-found card (HTTP 200, card streamed inside the shell), no corpus search on Home, `/papers/<id>` still reachable from a briefing, and every star affordance present.

Two page-object helpers turn a hidden route into a false green, which is why journeys 02 and 06 no longer visit `/papers` or `/ask` and journey 05 is skipped:

* `SidebarNav.navigateTo()` falls back to `goto(path)` when the nav link is missing, so a hidden route would still be "navigated to" — into the not-found card.
* `PapersPage.isLoaded()` returns `true` on that card, because it renders inside the shell's `<main>`.

`07_feature_flags.journey.spec.ts` is the guard, and it asserts **absence with raw locators only**: the fixed state in a cookieless browser, then again with the old all-three-off cookie seeded before sign-in, which must change nothing:

```ts
import { addFeatureCookie, FeatureToggles } from '../pages/index.js';

// Seed the OFF list before sign-in; the first server render already sees it.
// With every flag fixed this is a no-op the spec proves, not a way to hide anything.
await addFeatureCookie(page.context(), ['all_papers', 'stars', 'ask'], baseURL!);

const toggles = new FeatureToggles(page);
await toggles.openMenu();
await expect(toggles.sectionHeading).toHaveCount(0); // no "Demo features" section
```

To hand a switch back to the menu, delete that flag's `fixed` property in the registry; the version of this spec before 9 Sep 2026 covered the toggles, the vanish guard and each flag off on its own.

`addFeatureCookie` is a thin wrapper over `context.addCookies()`; `BasePage.addCookies()` is the general form for any preference cookie (`rs-lang`, `rs-features`).

The suite targets the local frontend (`http://localhost:3000`) by default; a dev server on another port takes `E2E_BASE_URL`:

```bash
E2E_BASE_URL=http://localhost:3009 npx playwright test specs/07_feature_flags.journey.spec.ts
```

### 2. Backend & Live Pipeline Scenarios
Located in `tests_e2e/scenarios/`:
```
tests_e2e/
├── package.json              # TypeScript Playwright dependencies & scripts
├── playwright.config.ts      # Playwright multi-environment configuration
├── tsconfig.json             # TypeScript compiler settings
├── run_frontend_e2e.sh       # Executable shell runner for TypeScript Playwright
├── pages/                    # Frontend Page Object Model (POM) layer (.ts)
├── specs/                    # Frontend User Journey test specs (.spec.ts)
├── config.py                 # Backend target environment configs (Prod, Staging, Local)
├── run_e2e.sh                # Automated backend shell runner
├── run_e2e.py                # Backend live pipeline runner
├── test_full_pipeline_e2e.py # Pytest backend pipeline integration suite
├── client/                   # Modular Backend API Client & Domain Services (.py)
└── scenarios/                # 11 Orthogonal Backend User Journeys (.py)
```

---

## 🖥️ Running Frontend Next.js E2E Tests (TypeScript & Playwright)

Frontend E2E tests are built natively in **TypeScript** using **`@playwright/test`** and Page Object Model:

### 1. Quick Setup:
```bash
cd tests_e2e
npm install
```

### 2. Run all frontend user journeys:
The default target is the local Next.js dev server (`cd frontend && bun run dev`, http://localhost:3000). The browser never touches production unless you ask for it — but the local Next server only proxies, so logins and chat sessions land on whichever Django `frontend/.env` names (`BACKEND_INTERNAL_URL` / `NEXT_PUBLIC_API_URL`, default `http://localhost:8000`). Point that at a local backend that has the `admin` user (`ADMIN_USERNAME` / `ADMIN_PASSWORD` override the credentials). An unrecognised `E2E_TARGET_ENV` is an error, not a fallback.

```bash
# Recommended: Run all frontend E2E specs against Production (Headless):
./tests_e2e/run_frontend_e2e.sh prod

# Run against Staging or Local dev:
./tests_e2e/run_frontend_e2e.sh staging
./tests_e2e/run_frontend_e2e.sh local

# Or directly with npm in tests_e2e/:
npm test                             # Runs all specs against Local dev (headless)
npm run test:staging                 # Runs against Staging
npm run test:prod                    # Runs against Production
```

### 3. Interactive UI Mode & Debugging (Time-Travel Debugger):
```bash
./tests_e2e/run_frontend_e2e.sh prod --ui       # Opens Playwright visual UI Mode
./tests_e2e/run_frontend_e2e.sh prod --headed   # Opens visible Chrome browser
./tests_e2e/run_frontend_e2e.sh prod --debug    # Starts Playwright inspector step-by-step
./tests_e2e/run_frontend_e2e.sh --report        # Opens rich HTML execution report
```

### 4. Run a specific user journey spec:
```bash
# Multi-persona setup, dashboard, runs, dynamic sliders, and screening log:
./tests_e2e/run_frontend_e2e.sh prod specs/08_multi_persona_and_full_lifecycle.journey.spec.ts

# Persona permission checks (launch blocked -> UI start -> Admin stop -> Admin rerun):
./tests_e2e/run_frontend_e2e.sh prod specs/09_run_admission_and_stop_rbac.journey.spec.ts

# Classic journey specs:
./tests_e2e/run_frontend_e2e.sh prod specs/01_auth_session_lifecycle.journey.spec.ts
./tests_e2e/run_frontend_e2e.sh prod specs/02_analyst_daily_review.journey.spec.ts
./tests_e2e/run_frontend_e2e.sh prod specs/03_manager_workspace_and_settings.journey.spec.ts
./tests_e2e/run_frontend_e2e.sh prod specs/04_tuning_read_only.journey.spec.ts
```

---

## 🚀 Running E2E Scenarios via CLI

### 1. Run the Complete Research Scanner Review & Chat (Default):
```bash
./tests_e2e/run_e2e.sh
```

### 2. Run Specific Orthogonal Scenarios:
```bash
# 1. Multi-Tenancy & RBAC Security Isolation:
./tests_e2e/run_e2e.sh --scenario=isolation

# 2. Mid-Step Pipeline Rerun (rerun_from_node):
./tests_e2e/run_e2e.sh --scenario=rerun

# 3. Chat Hallucination Guard & Grounding:
./tests_e2e/run_e2e.sh --scenario=guard

# 4. Concurrent Agents Load & Concurrency:
./tests_e2e/run_e2e.sh --scenario=concurrent

# 5. Agent Lifecycle (Pause & Resume):
./tests_e2e/run_e2e.sh --scenario=lifecycle

# 6. Pipeline Reprocessing (reprocess_existing=True):
./tests_e2e/run_e2e.sh --scenario=reprocess

# 7. Multi-Source Deduplication (arXiv + OpenAlex):
./tests_e2e/run_e2e.sh --scenario=dedup

# 8. Quota Guard & Budget Limits:
./tests_e2e/run_e2e.sh --scenario=quota

# 9. FastMCP SSE Protocol & AI Tools:
./tests_e2e/run_e2e.sh --scenario=mcp

# 10. Workflow Scheduling & Observability:
./tests_e2e/run_e2e.sh --scenario=schedule

# 11. Concurrent Pipeline Runs in Single Workspace:
./tests_e2e/run_e2e.sh --scenario=parallel

# 12. Paper Evidence Quotes, Scorecard & PDF Streaming:
./tests_e2e/run_e2e.sh --scenario=evidence

# 13. Researcher RBAC Guard & Read-Only Safety:
./tests_e2e/run_e2e.sh --scenario=researcher

# 14. Executive Briefing Generation & Structured Sections:
./tests_e2e/run_e2e.sh --scenario=briefing

# 15. Paper Comments & Collaboration Area API Lifecycle:
./tests_e2e/run_e2e.sh --scenario=comments
# Or shortcut:
./tests_e2e/run_e2e.sh local comments

# Run ALL Scenarios Sequentially:
./tests_e2e/run_e2e.sh --scenario=all
```

### 3. Run on Different Environments:
```bash
# Recommended: Run ALL 24 scenarios on Production with immediate cleanup:
./tests_e2e/run_e2e.sh prod all --cleanup-after

# Run on Staging or Local dev:
./tests_e2e/run_e2e.sh staging all --cleanup-after
./tests_e2e/run_e2e.sh local all --cleanup-after
```

### 4. Required Environment Variables

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `E2E_TARGET_ENV` | `prod` (or `staging` / `local`) | Target cloud environment or local stack. |
| `ADMIN_USERNAME` / `E2E_USERNAME` | `admin` | Superuser / staff administrator username. |
| `ADMIN_PASSWORD` / `E2E_PASSWORD` | `schwarz123!` | Administrator password. |
| `E2E_BASE_URL` | `https://research-scanner.schwarz` (prod) | Next.js frontend root URL for Playwright tests. |
| `E2E_API_URL` | `https://research-scanner.schwarz` (prod) | Django REST API root URL for backend tests. |
| `E2E_CLEANUP_AFTER` | `false` (flag: `--cleanup-after`) | Automatically deletes test workspaces, runs, and artifacts upon completion. |
| `E2E_TIMEOUT_SEC` | `900` | Maximum polling timeout (in seconds) for Research Scanner agent completion. |
| `E2E_PAPER_LIMIT` | `10` | Maximum candidate papers fetched per scraper in pipeline test runs. |

### 5. Run with Pytest:
```bash
pytest tests_e2e/test_full_pipeline_e2e.py -s -v
```

---

## 🧹 Pre-Cleanup & Artifact Retention Policy

* **Pre-Cleanup (`cleanup_before = True`)**: Before creating a new workspace, the suite automatically searches for and deletes all previous test workspaces and extraction definitions matching `test_e2e_*` to keep your environment spotless.
* **Artifact Retention**: The created workspace and all its artifacts (downloaded PDFs, Markdown extractions, technology scorecards, and reports) are **retained after test completion** so you can inspect them in the Django Admin Portal (`/admin/`) and Storage Browser (`/admin/storage-browser/`).
* **Immediate Deletion**: To delete the workspace immediately upon completion, pass `--cleanup-after`.
