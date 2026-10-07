# 🧠 Schwarz Research Intelligence

> **Enterprise-Grade AI Platform for Autonomous Scientific Literature Review, Deep Tech Scouting & Parameter Extraction.**  
> Powered by **FastMCP (Model Context Protocol)**, **Django REST Framework**, **Next.js Dashboard SPA**, **Celery Distributed Workers**, and **Google GenAI / Gemini 3.7 Flash** (hosted on Schwarz Digits Cloud).

---

## 📋 1. System Overview & User Personas

**Schwarz Research Intelligence** is an enterprise-grade platform designed for automated, AI-driven academic literature review, competitive technology scouting, and dynamic parameter extraction.

The system serves three core personas through dedicated access channels:
* **🧑‍💼 Manager / Researcher (Frontend User)**: Interacts with the **Next.js Dashboard / SPA** for exploratory literature review, technology scorecards, dynamic parameter matrices, and interactive multi-turn paper Q&A (`Paper Chat`).
* **⚡ Power User / AI Agent (MCP Client)**: Interacts programmatically via the **FastMCP SSE Server (Port 8001)** from Claude Code, Cursor, Antigravity IDE, or custom agent scripts to trigger autonomous multi-stage SLR runs (`start_research_agent`), check DAG progress, and query extracted scorecards.
* **🛡️ Administrator / Lead Architect (Django Admin User)**: Manages workspace criteria, RBAC memberships, token/USD spending quotas, operational security audit logs, and file storage via the **Django Admin Portal & Storage Browser**.

```mermaid
graph TB
    subgraph Personas ["User Personas & Clients"]
        manager["🧑‍💼 Manager / Researcher<br>(Frontend Web User)"]
        power["⚡ Power User / AI Agent<br>(MCP Client: Claude / Cursor / Antigravity)"]
        admin["🛡️ Administrator / Lead<br>(Django Admin User)"]
    end

    subgraph Ingress ["Ingress Gateway Router (Port 80/443)"]
        nginx[Reverse Proxy & Ingress Router]
    end

    subgraph Interfaces ["Application Interfaces"]
        frontend[Next.js Dashboard / SPA<br>Web UI & Scorecards]
        api[Django REST API<br>/api/ - Auth, Papers, Chat]
        django_admin[Django Admin Portal<br>/admin/ - RBAC, Quotas, Storage]
        mcp[FastMCP SSE Server<br>Port 8001 / SSE Tools]
    end

    subgraph StateEngine ["Autonomous State Engine & DAG Orchestrator"]
        engine[ResearchAgentRunner & DAG Workflow Engine]
    end

    subgraph PipelineExecution ["8-Stage Systematic Literature Review (SLR) Pipeline"]
        engine --> Step1[1. Search & Ingestion<br>arXiv, OpenAlex, Lens, PubMed]
        Step1 --> Step2[2. Abstract Screening<br>AI Triage via Gemini 3.7 Flash]
        Step2 --> Step3[3. Parallel PDF Download<br>Only for Abstract-Passed Papers]
        Step3 --> Step4{4. Layout OCR Parsing}
        Step4 -->|ocr_provider set| OCRConv[PyPDF / Mistral OCR / Gemini -> MD]
        Step4 -->|ocr_provider is None| SkipOCR[Auto-Skip OCR<br>Direct Multimodal PDF Mode]
        OCRConv --> Step5
        SkipOCR --> Step5
        Step5[5. Multimodal Full-Text Screening<br>Deep PDF Verification via Gemini 3.7 Flash]
        Step5 --> Step6[6. Dynamic Parameter Extraction<br>Schema-Constrained JSON & Evidence Quotes]
        Step6 --> Step7[7. Composite Signal Score<br>AST-Sandboxed Custom Python Math Formula]
        Step7 --> Step8[8. Executive Reporting & Alerts<br>Briefing Synthesis & Mailgun Email Digests]
    end

    manager ==>|HTTPS / Web Browser| nginx
    power ==>|HTTPS / SSE MCP Protocol| nginx
    admin ==>|HTTPS / Admin Sessions| nginx

    nginx --> frontend
    nginx --> api
    nginx --> django_admin
    nginx --> mcp

    frontend ==>|REST Queries / JWT| api
    api ==>|Trigger Runs / Chat| engine
    mcp ==>|Autonomous SLR Tools| engine
    django_admin ==>|Admin ORM & Config| engine

    Step8 --> DB[(PostgreSQL Prod / SQLite Test)]
    Step8 --> Storage[(Django Storage / S3 / MinIO)]
    Step8 --> EmailNotifier[Transactional Mailgun Dispatch]
```

---

## 🚀 2. Core Architectural Features

### 1. Autonomous Research Agent State Machine (`ResearchAgentProcess`)

The state engine (`tasks/orchestrator/agent_engine.py` & `runner.py`) coordinates transitions through state checkpoints, handling background Celery job execution, lifecycle interruptions (Pause, Resume, Abort), and email summaries:

```mermaid
graph TD
    Start([User / FastMCP Client / REST API Triggers Agent]) --> Initialized[State: initialized<br/>Creates ResearchAgentProcess & PipelineRun]
    
    Initialized --> SearchStep[Search & Ingestion<br/>State: search<br/>Queries scrapers & deduplicates metadata]
    
    SearchStep --> AbstractScreening[Abstract Screening<br/>State: abstract_screening<br/>Fast triage against abstract_* criteria]
    
    AbstractScreening --> DownloadStep[PDF Download<br/>State: download<br/>Fetches PDFs ONLY for abstract-passed papers]
    
    DownloadStep --> OCRCheck{ocr_provider configured?}
    
    OCRCheck -->|Yes: pypdf / mistral / gemini| OCRStep[OCR Conversion<br/>State: ocr<br/>Parses layout to structured Markdown]
    OCRCheck -->|No: ocr_provider is None| SkipOCR[Auto-Skip OCR Step<br/>Direct pass-through for multimodal screening]
    
    OCRStep --> FullTextScreening[Full-Text Screening<br/>State: full_text_screening<br/>Multimodal analysis of raw PDF via Gemini 3.7 Flash]
    SkipOCR --> FullTextScreening
    
    FullTextScreening --> ExtractionStep[Parameter Extraction<br/>State: extraction<br/>Extracts schema-validated JSON & evidence quotes]
    
    ExtractionStep --> SignalScoreStep[Composite Signal Scoring<br/>State: signal_score<br/>AST-sandboxed Python scoring formula evaluation]
    
    SignalScoreStep --> ReportingStep[Executive Reporting<br/>State: reporting<br/>Synthesizes briefing & dispatches Mailgun digests]
    
    ReportingStep --> Completed([State: completed<br/>Pipeline finished successfully])
    
    subgraph Controls ["Agent Process Lifecycle Controls"]
        PauseCommand[pause_research_agent] -.->|State: paused| AgentPaused[Process Paused]
        AgentPaused -.-> ResumeCommand[resume_research_agent]
        ResumeCommand -.->|Resumes active step| SearchStep
        AbortCommand[abort_research_agent] -.->|State: aborted| AgentAborted[Process Aborted & Celery Tasks Terminated]
    end
```

- **State Machine Transitions**: Sequentially advances through `initialized` $\rightarrow$ `search` $\rightarrow$ `abstract_screening` $\rightarrow$ `download` $\rightarrow$ `ocr` $\rightarrow$ `full_text_screening` $\rightarrow$ `extraction` $\rightarrow$ `signal_score` $\rightarrow$ `reporting` $\rightarrow$ `completed`.
- **Parallel Runs**: Executes multiple agents concurrently per workspace or across workspaces.
- **On-Demand OCR Skipping**: Automatically skips OCR if `workspace.ocr_provider` is unconfigured (`None`), passing PDF binaries directly to multimodal Gemini 3.7 Flash.
- **Notification Engine**: Dispatches completion summary notifications to workspace member emails (`WorkspaceMember.user.email`), subscribers (`Subscriber.email`), and custom overrides via Mailgun.
- **Security & Defense-in-Depth**: See [`docs/SECURITY.md`](./docs/SECURITY.md) for full threat model, AST sandboxing, SSRF URL filters, and RBAC matrix.

### 2. Isolated Dual-Stage Screening Criteria
- **Abstract Screening Stage**: Evaluates paper title & abstract against `abstract_acceptance_criteria` and `abstract_rejection_criteria`.
- **Full-Text Screening Stage**: Performs deep multimodal evaluation of raw PDF binaries (or OCR Markdown text) against `full_text_acceptance_criteria` and `full_text_rejection_criteria`.

### 3. Global DocumentRegistry & Multi-Tier Caching
- **Zero-Network PDF Fastpath**: Checks `DocumentRegistry` ($O(1)$ indexed by `sha256_hash`, `doi`, `arxiv_id`) before initiating HTTP requests, saving bandwidth and preventing rate-limits across runs and workspaces.
- **Zero-Compute OCR Fastpath**: Caches layout Markdown in `cache/documents/{sha256}/ocr_{provider}.md`, skipping expensive OCR parser execution for previously converted documents.
- **Strict Storage Isolation**: Workspace run deletions purge only their local workspace run folder (`workspaces/{ws_id}/runs/{run_id}/`), keeping canonical registry binaries and other workspaces' files 100% intact.

### 4. Dynamic Parameter Extraction & Multi-Metric Postprocessing
- **Schema-Validated Extraction**: Evaluates papers against `ExtractionDefinition` prompts and JSON schemas using Gemini 3.8 Flash (`google/gemini-3.8-flash`).
- **Explicit Primary & Secondary Frontend Metrics**: Supports explicit `primary_frontend_metric` (e.g. `'fit_score'` or `'trl_level'`) and `secondary_frontend_metrics` (e.g. `['novelty', 'significance']`) configured on `ExtractionDefinition`, providing a deterministic path for scorecard headlines and facet display.
- **Exit Metrics List**: Directly accepts an explicit list of parameters (`exit_metrics: ["rigour_score", "sample_size", "p_value"]`) to unpack multiple distinct variables from a single extraction definition into Signal Scoring.
- **Python AST-Sandboxed Postprocessing Snippet**: Optional Python code (`postprocessing_code`) executed in a secure sandbox with full access to the raw LLM JSON response (`data`, `response`, `json_response`) and extracted variables. Automatically injects a derived variable `<first_metric>_postprocessed` into the scoring environment.
- **Evidence & Confidence Scores**: Stores results in `Extraction` objects containing exact evidence quotes, normalized values, confidence scores, and validation statuses (`pass`, `warn`, `fail`).
- **REST API & FastMCP Tools**: Full programmatic manipulation via `/api/extraction-definitions/` and FastMCP tools (`create_extraction_definition`, `update_extraction_definition`, `set_extraction_frontend_metrics`, `get_extraction_definition`, `list_extraction_definitions`).

### 5. Custom Python AST Signal Scoring
- Evaluates sandboxed mathematical ranking formulas (`workspace.signal_score_code`) securely using Python AST analysis.
- Consumes all extracted variables, multi-exit parameters, and postprocessed metrics (e.g. `score = (0.4 * market_fit_postprocessed) + (0.3 * novelty) + (0.3 * sample_size)`).

### 6. Workspace Configuration Export & Import (Staging ➔ Production Sync)
- Export full workspace configurations as JSON bundles (criteria, prompts, schemas, scrapers, subscribers, formulas).
- Import with explicit **Yes/No overwrite prompt** to fine-tune existing workspaces or import new ones.

### 7. Dual Protocol Interface & Canonical Scorecard Endpoints
- **FastMCP SSE Interface (Port 8001)**: Exposes workspace tools, scrapers, state machine controls, parameter extraction, and document registry stats to LLM clients (Claude, Gemini, Cursor, Antigravity) via `@mcp.tool()` and `@mcp.prompt()`.
- **Django REST API (Port 8000)**: Exposes core resources along with unified scorecard and briefing editions:
  - `/api/workspaces/{id}/scorecard/`: High-performance, workspace-scoped canonical scorecard with run-scoping, multi-field search, screening status filter, and database-level ordering (`-signal_score`, `title`, `created_at`).
  - `/api/papers/{id}/scorecard/`: Dedicated paper scorecard delivering structured dimensions, facets, prose insights, evidence quotes, and risk/affiliation flags.
  - `/api/workspaces/{id}/editions/` & `/api/workspaces/{id}/editions/{date}/`: Briefing editions delivering pre-scored paper lists and exclusions directly, eliminating client-side paper composition.
  - `/api/pipeline-runs/`: Paginated execution telemetry with heavy JSON fields (`stage_results`, `step_history`) deferred on list views for 10x smaller payload, and available on retrieve.
  - `/api/chat/`, `/api/auth/`, `/api/extraction-definitions/`, `/api/papers/`.

### 8. The 5 Pipeline Triggering Pathways & Concurrency Controls
The Systematic Literature Review (SLR) pipeline can be dispatched through **5 distinct, enterprise-grade execution channels**, all converging into the unified `ResearchAgentRunner` and `WorkflowDAG` orchestrator:

| Pathway | Interface / Entrypoint | Concurrency & Overlap Policy | Async Dispatch Mechanism |
| :--- | :--- | :--- | :--- |
| **1. Celery Beat Periodic Dispatcher** | `dispatch_due_workflow_schedules()` | `select_for_update(skip_locked=True)` + `prevent_overlap` check. If overlapping, advances `next_run_at` to prevent busy-spin. | Automated cron evaluation with staggered jitter ($0\text{s} - 45\text{s}$) to distribute worker load. |
| **2. Django Admin UI ("Run Now")** | Admin action / detail view: `admin:research_intelligence_workflowschedule_trigger` | `force=True` (allows manual execution override even if previous run is active). | `transaction.on_commit` Celery task dispatch with immediate UI flash message. |
| **3. Django REST API** | `POST /api/schedules/{id}/trigger/`<br/>`POST /api/pipeline-runs/` | Honors `prevent_overlap` (returns HTTP 200 with process ID or 409 Conflict if locked). | Non-blocking DRF viewset dispatching async Celery task. |
| **4. FastMCP SSE Agent Tools** | `start_research_agent(workspace_id, ...)`<br/>`trigger_search_job(...)` | Dynamic configuration overrides (e.g. `reprocess_existing`, `limit`, `n_last_days`). | Async Celery worker trigger returning instant execution payload and run UUID. |
| **5. Direct Engine / Programmatic Runner** | `ResearchAgentRunner.tick(process_id)` | Row-level locking on PostgreSQL (`select_for_update`). Protected against premature connection closure via `in_atomic_block` guard. | Direct DAG node evaluation and synchronous/asynchronous task dispatch. |

* **Concurrency & Overlap Guard**: `prevent_overlap=True` guarantees zero race conditions or duplicate runs for the same schedule.
* **Decoupled Signals Observer**: Django `post_save` signals in `signals.py` update observing `WorkflowSchedule.last_status` records dynamically.
* **Failure Guardrails & Auto-Pause**: Auto-pauses recurring schedules (`is_active=False`) when `consecutive_failures_count >= max_consecutive_failures`.
* **Daylight Saving Time (DST) Support**: Leverages Python's native `zoneinfo.ZoneInfo` for localized cron evaluations without 1-hour clock shifts.

---

## 🗄️ 3. Database Architecture & Entity Relationships

The data layer is structured into 5 cohesive domains:
1. **Tenancy & Authentication**: `Workspace`, `WorkspaceMember`, `APIKey`, `UserActivityLog`
2. **Configuration & Scrapers**: `Scraper`, `ExtractionDefinition`, `Subscriber`, `WorkflowSchedule`
3. **Execution & Orchestration**: `PipelineRun`, `ResearchAgentProcess`, `ComponentRun`
4. **Ingestion & Registry Cache**: `Paper`, `DocumentRegistry` (Global SHA-256 PDF & OCR Cache)
5. **Intelligence & Scorecards**: `Extraction`, `PaperMetric`, `NarrativeReport`, `HITLCorrection`

### High-Level Domain Relationships
![Database Schema Overview](docs/images/db_schema_overview.svg)

### Detailed Entity-Relationship Diagram (ERD)
![Detailed Database ERD](docs/images/db_schema_detailed.svg)

> **💡 Refreshing Schema Diagrams**:
> Run `./docs/generate_db_schema.py` anytime models are modified to regenerate both diagrams in `docs/images/` (.png & .svg) and `docs/diagrams/` (.mmd).

---

## 🏗️ 4. Repository Structure

```
├── backend/                     # Django API + Celery Async Task Workers + FastMCP
│   ├── Dockerfile               # Production container definition
│   ├── django_project/          # Settings & WSGI configuration
│   ├── api/                     # DRF REST API viewsets & serializers (/api/)
│   ├── chat/                    # Interactive Knowledge Explorer & Paper Chat (/api/chat/)
│   ├── mcp_server/              # FastMCP Server (Port 8001) & Tool Registry (/mcp/)
│   └── research_intelligence/   # Core intelligence platform
│       ├── services/            # Scorecard service & extraction parsing architecture
│       ├── tasks/               # 8-Stage Pipeline & Orchestrator DAG State Engine
│       ├── models/              # Workspace, DocumentRegistry, Paper, Extraction models
│       └── tests/               # Automated unit & integration test suite (949+ tests)
├── frontend/                    # Next.js 15 App Router SPA + BFF Seam (586 tests)
├── docs/                        # Architecture documentation, diagrams & image generators
│   ├── generate_db_schema.py    # Automated DB schema diagram builder (Mermaid/PNG/SVG)
│   ├── diagrams/                # Raw Mermaid diagram definitions (.mmd)
│   ├── images/                  # Compiled architecture & DB schema images (.png / .svg)
│   └── user_documentation/      # Complete user guides for Django Admin and FastMCP (Claude Code)
├── .github/                     # DevOps & CI/CD Pipelines
│   └── workflows/
│       ├── ci.yml               # GitHub Actions workflow (SQLite tests + pip caching)
│       └── deploy.yml           # Automated deployment to STACKIT Cloud Foundry
├── tests_e2e/                   # E2E Test Suites (Frontend TS Playwright + Backend Python Pipeline)
├── docker-compose.yml           # Unified local development & production stack
└── README.md                    # System documentation (This file)
```

---

## 🛠️ 5. Technology Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Backend Framework** | Python 3.12+, Django 6.0, DRF | Core models, database management, and REST API. |
| **MCP SSE Server** | FastMCP | Model Context Protocol SSE server on port 8001. |
| **Frontend Framework** | Next.js 15, React 19, TailwindCSS 4, Bun | Modern responsive literature intelligence dashboard with Souverän design system. |
| **Task Queue** | Celery, Redis | Distributed async pipeline execution and DAG state engine polling. |
| **Database Layer** | PostgreSQL (Prod) / SQLite (Tests) | Persistent storage, composite B-tree indexes, audit logs, and in-memory test runner. |
| **Storage Layer** | Django `default_storage` | Local filesystem / AWS S3 / MinIO storage abstraction. |
| **Telemetry & APM** | Sentry SDK | Error tracking, distributed performance tracing, and profiler. |
| **LLM Engine** | Google GenAI / Gemini 3.8 Flash | Enterprise AI provider with reasoning effort support hosted on Schwarz Digits Cloud. |
| **OCR Providers** | PyPDF / Mistral OCR / Gemini Vision | Document layout parsing. |
| **Diagram Engine** | Mermaid CLI / Python Generator | Automated DB schema and architecture diagram generation. |
| **CI/CD** | GitHub Actions | Automated build, test, and container layer caching. |

---

## ⚡ 6. Quick Start for Developers

### Run Locally with Docker Compose
```bash
# 1. Clone repository and set up environment variables
cp .env_example .env

# 2. Build and start containers
docker compose up --build

# 3. Access interfaces:
# - Next.js Frontend: http://localhost:3000
# - Django REST API: http://localhost:8000/api/
# - FastMCP SSE Endpoint: http://localhost:8001/mcp/
# - Django Admin: http://localhost:8000/admin/
```

### Run Unit Tests Locally
Tests automatically run on an in-memory SQLite database (0 tokens consumed):
```bash
# Backend test suite (949 tests)
cd backend && uv run pytest

# Frontend test suite (828 tests)
cd frontend && bun test
```

---

## 🧪 7. Running End-to-End (E2E) Test Suites

The platform includes full-spectrum E2E test suites for both the **Next.js Frontend (Playwright / TypeScript)** and **Backend REST/MCP Pipelines (Python / Pytest)**:

### 1. Frontend E2E Playwright Tests
Executes complete browser user journeys across `/dashboard`, `/briefing`, `/runs`, `/runs/[id]`, `/briefing/[date]/run`, `/papers/[id]`, dynamic extraction sliders, and role-based permissions (Admin, Manager, Researcher).

```bash
# Run all frontend E2E specs against Production (Headless):
./tests_e2e/run_frontend_e2e.sh prod

# Run against Staging or Local dev:
./tests_e2e/run_frontend_e2e.sh staging
./tests_e2e/run_frontend_e2e.sh local

# Interactive UI Mode & Time-Travel Debugger:
./tests_e2e/run_frontend_e2e.sh prod --ui

# Visible browser window (--headed):
./tests_e2e/run_frontend_e2e.sh prod --headed

# Run specific user journey specs:
./tests_e2e/run_frontend_e2e.sh prod specs/08_multi_persona_and_full_lifecycle.journey.spec.ts
./tests_e2e/run_frontend_e2e.sh prod specs/09_run_admission_and_stop_rbac.journey.spec.ts
```

### 2. Backend Live Pipeline E2E Tests
Executes autonomous multi-agent SLR reviews, screening triage, full multimodal extractions, composite signal scoring, and RBAC matrix validation across all 23 scenarios:

```bash
# Run ALL 23 backend E2E scenarios sequentially with immediate workspace cleanup:
./tests_e2e/run_e2e.sh prod all --cleanup-after

# Run against Staging or Local dev:
./tests_e2e/run_e2e.sh staging all --cleanup-after
./tests_e2e/run_e2e.sh local all --cleanup-after

# Run via Pytest:
pytest tests_e2e/test_full_pipeline_e2e.py -s -v
```

### 3. Required Environment Variables

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `E2E_TARGET_ENV` | `prod` (or `staging` / `local`) | Target cloud environment or local stack. |
| `ADMIN_USERNAME` / `E2E_USERNAME` | `admin` | Superuser / staff administrator username. |
| `ADMIN_PASSWORD` / `E2E_PASSWORD` | `schwarz123!` | Administrator password. |
| `E2E_BASE_URL` | `https://research-scanner.schwarz` (prod) | Next.js frontend root URL for Playwright tests. |
| `E2E_API_URL` | `https://research-scanner.schwarz` (prod) | Django REST API root URL for backend tests. |
| `E2E_CLEANUP_AFTER` | `false` (flag: `--cleanup-after`) | Automatically deletes test workspaces, runs, and artifacts upon completion. |
| `E2E_TIMEOUT_SEC` | `900` | Maximum polling timeout (in seconds) for SLR agent completion. |
| `E2E_PAPER_LIMIT` | `10` | Maximum candidate papers fetched per scraper in pipeline test runs. |

