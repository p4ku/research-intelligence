# 🧪 Schwarz Research Intelligence - End-to-End (E2E) Test Suite

State-of-the-art live API test suite and full pipeline simulator for **Schwarz Research Intelligence (SRI)** against **Production**, **Staging**, or **Local** environments.

---

## 🏛️ Architecture & Scenarios

The E2E test suite covers both **Backend REST/MCP Pipelines** and **Next.js Frontend User Journeys**:

### 1. Next.js Frontend User Journeys (TypeScript & Playwright)
Located in `tests_e2e/pages/` and `tests_e2e/specs/`:
* **`pages/`**: Clean Page Object Model abstraction in TypeScript:
  * `LoginPage.ts`: Authentication forms, input handling, and session state.
  * `SidebarNav.ts`: Menu traversing (`/dashboard`, `/briefing`, `/papers`, `/ask`), User Menu, and Sign Out.
  * `WorkspaceSwitcher.ts`: Workspace dropdown, listing accessible workspaces, and cookie validation (`rs-workspace`).
  * `SettingsPage.ts`: `/settings` profile form, password form, workspace configuration summary, and notification toggle.
  * `DashboardPage.ts`, `BriefingPage.ts`, `PapersPage.ts`, `AskPage.ts`: Core application surface abstractions.
* **`specs/`**: Modular, full end-to-end user journey test suites:
  1. `01_auth_session_lifecycle.journey.spec.ts`: Rejection of bad credentials, login, session cookies, deep-link protection, and sign out.
  2. `02_analyst_daily_review.journey.spec.ts`: Today Dashboard funnel metrics, reading executive Briefing, systematic Papers exploration and scorecard inspections.
  3. `03_manager_workspace_and_settings.journey.spec.ts`: Multi-tenant workspace switching, `/settings` inspection (Profile, Role, Password, Workspace Metadata), and bilingual EN <-> DE locale toggle.
  4. `05_interactive_paper_chat.journey.spec.ts`: Deep-dive literature question answering in `/ask`, reasoning engine, and citation stream validation.
  5. `06_end_to_end_researcher_flow.journey.spec.ts`: Comprehensive full researcher flow executing the entire application lifecycle end-to-end in a single session.

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
```bash
npm test                             # Runs all specs against Production (headless)
npm run test:staging                 # Runs against Staging
npm run test:local                   # Runs against Local dev
```

### 3. Interactive UI Mode & Debugging (Time-Travel Debugger):
```bash
npm run test:ui                      # Opens Playwright visual UI Mode
npm run test:headed                  # Opens visible Chrome browser
npm run test:debug                   # Starts Playwright inspector step-by-step
npm run test:report                  # Opens rich HTML execution report
```

### 4. Run a specific user journey spec:
```bash
npx playwright test specs/settings.spec.ts    # /settings journey (role, profile, password)
npx playwright test specs/auth.spec.ts        # Authentication & logout journey
npx playwright test specs/navigation.spec.ts  # Sidebar navigation journey
npx playwright test specs/workspace.spec.ts   # Workspace switcher journey
npx playwright test specs/papers.spec.ts      # Papers exploration & scorecards
npx playwright test specs/i18n.spec.ts        # Bilingual locale toggle (EN <-> DE)
npx playwright test specs/ask.spec.ts         # Paper Chat / Ask interface
```

---

## 🚀 Running E2E Scenarios via CLI

### 1. Run the Complete SLR Review & Chat (Default):
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

# Run ALL Scenarios Sequentially:
./tests_e2e/run_e2e.sh --scenario=all
```

### 3. Run on Different Environments:
```bash
./tests_e2e/run_e2e.sh staging          # Run on Staging
./tests_e2e/run_e2e.sh prod             # Run on Production
./tests_e2e/run_e2e.sh local            # Run on Local development server
```

### 4. Run with Pytest:
```bash
pytest tests_e2e/test_full_pipeline_e2e.py -s -v
```

---

## 🧹 Pre-Cleanup & Artifact Retention Policy

* **Pre-Cleanup (`cleanup_before = True`)**: Before creating a new workspace, the suite automatically searches for and deletes all previous test workspaces and extraction definitions matching `test_e2e_*` to keep your environment spotless.
* **Artifact Retention**: The created workspace and all its artifacts (downloaded PDFs, Markdown extractions, technology scorecards, and reports) are **retained after test completion** so you can inspect them in the Django Admin Portal (`/admin/`) and Storage Browser (`/admin/storage-browser/`).
* **Immediate Deletion**: To delete the workspace immediately upon completion, pass `--cleanup-after`.
