# 🐍 Schwarz Research Intelligence - Backend & FastMCP Infrastructure

> **Enterprise-Grade AI Architecture for Systematic Literature Review (SLR) & Deep Tech Intelligence.**  
> Unified backend exposing a **FastMCP SSE Interface (Port 8001)** for AI Agents, a **Django REST API (Port 8000)** for Web Interfaces, and a **Django Admin & Storage Browser** for Administrators.

---

## 🏛️ 1. Architecture Overview & Personas

The backend provides a unified Django foundation for persistent data management, FastMCP for agentic tool protocol interactions, and distributed Celery task workers backed by Redis and PostgreSQL. It powers three core interfaces:
1. **🧑‍💼 Manager / Researcher**: Interacts via Next.js Frontend calling **Django REST API** (`/api/auth/`, `/api/workspaces/`, `/api/papers/`, `/api/chat/`, `/api/reports/`).
2. **⚡ Power User / AI Agent**: Interacts via **FastMCP SSE Server** (`/sse`, `/messages` on port 8001) for programmatic tool execution (`start_research_agent`, `get_paper_extractions_matrix`, `ask_paper`).
3. **🛡️ Administrator / Lead Architect**: Manages system state directly via **Django Admin Portal & Storage Browser** (`/admin/`, `/admin/storage-browser/`).

```
backend/
├── Dockerfile                  # Unified build for Django, Celery & FastMCP
├── requirements.txt            # Python dependencies
├── manage.py                   # Django CLI & test runner
├── django_project/             # Core project configuration
│   ├── settings.py             # Environment settings (Postgres prod / SQLite tests, Storage, Sentry)
│   ├── urls.py                 # Root URL routing table
│   └── celery.py               # Celery app initialization
├── api/                        # Django REST Framework (DRF) Web Layer (/api/)
│   ├── auth_backend.py         # WorkspaceJWTAuthentication & APIKey scope validation
│   ├── serializers/            # DRF Serializers (workspaces, auth, agents, extractions, papers)
│   ├── views/                  # DRF Views (auth, workspaces, agents, extractions, diagnostics)
│   └── urls.py                 # API routing (/api/auth/, /api/workspaces/, /api/health/)
├── chat/                       # Interactive Paper Q&A & Knowledge Explorer (/api/chat/)
├── mcp_server/                 # FastMCP SSE Server (Port 8001) & Tool Modules (/mcp/)
│   ├── server/                 # FastMCP Server Instance & Tool Registrations
│   ├── tools/                  # Domain tool logic (agent_processes, workspaces, extractions, etc.)
│   ├── views.py                # MCP Discovery & Capabilities endpoints
│   └── management/commands/    # Django management command (python manage.py run_mcp)
└── research_intelligence/      # Core Platform Domain Logic
    ├── llm_providers/          # LLM Drivers (Google Vertex AI / Gemini 3.7 Flash, OpenRouter)
    ├── ocr_providers/          # Document OCR Parsers (PyPDF, Mistral OCR, Gemini)
    ├── tasks/                  # Celery Tasks & Orchestrator DAG State Engine
    │   ├── orchestrator/       # ResearchAgentProcess State Machine & DAG Runner
    │   ├── step_1_search/      # Multi-source querying & deduplication (ArXiv, OpenAlex, Lens, PubMed)
    │   ├── step_2_download/    # Parallel document fetch & SHA-256 PDF caching
    │   ├── step_3_ocr/         # PDF layout parsing (skipped by default for multimodal)
    │   ├── step_4_screening/   # 2-Stage Abstract & Multimodal Full-Text Screening
    │   ├── step_5_extraction/  # Schema-validated JSON parameter extraction
    │   ├── step_6_signal_score/# AST-sandboxed mathematical composite scoring
    │   ├── step_7_reporting/   # Executive narrative report synthesis & notification dispatch
    │   └── auxiliary/          # Email digest notifications & health monitoring
    ├── utils/                  # Mailgun HTTP transactional emailer & sandbox
    ├── management/commands/    # Management commands (python manage.py seed)
    └── tests/                  # Complete test suite (400+ tests running on in-memory SQLite)
```

---

## ⚙️ 2. The SLR Processing Pipeline Stages

The autonomous DAG engine orchestrates the complete literature review lifecycle:

```mermaid
graph TD
    Start([User / FastMCP Client / REST API Triggers Agent]) --> Initialized[State: initialized<br/>Creates ResearchAgentProcess & PipelineRun]
    
    Initialized --> SearchStep[Search & Ingestion<br/>State: search<br/>Queries ArXiv, OpenAlex, Lens, PubMed with deduplication]
    
    SearchStep --> AbstractScreening[Abstract Screening<br/>State: abstract_screening<br/>Fast triage against abstract_* criteria]
    
    AbstractScreening --> DownloadStep[Parallel PDF Download<br/>State: download<br/>Fetches PDFs ONLY for abstract-passed papers]
    
    DownloadStep --> OCRCheck{ocr_provider configured?}
    
    OCRCheck -->|Yes: pypdf / mistral / gemini| OCRStep[OCR Conversion<br/>State: ocr<br/>Parses layout to structured Markdown]
    OCRCheck -->|No: ocr_provider is None| SkipOCR[Auto-Skip OCR Step<br/>Direct pass-through for multimodal screening]
    
    OCRStep --> FullTextScreening[Full-Text Screening<br/>State: full_text_screening<br/>Multimodal analysis of raw PDF via Gemini 3.7 Flash]
    SkipOCR --> FullTextScreening
    
    FullTextScreening --> ExtractionStep[Dynamic Parameter Extraction<br/>State: extraction<br/>Schema-validated JSON parameter extraction]
    
    ExtractionStep --> SignalScoreStep[Composite Signal Scoring<br/>State: signal_score<br/>AST-sandboxed Python scoring formula evaluation]
    
    SignalScoreStep --> ReportingStep[Executive Reporting<br/>State: reporting<br/>Synthesizes briefing & dispatches Mailgun digests]
    
    ReportingStep --> Completed([State: completed<br/>Transactional briefing emails via Mailgun])
```

* **Search & Ingestion**: Multi-source querying with title, DOI, and arXiv ID deduplication.
* **Abstract Screening**: Fast AI triage evaluating title & abstract against `abstract_acceptance_criteria` with Indirect Prompt Injection guard.
* **Parallel PDF Download**: Multi-threaded document fetching for passed papers with SHA-256 caching and SSRF private IP protection.
* **Layout OCR Parsing**: Layout Markdown parsing (skipped by default for multimodal Gemini).
* **Full-Text Screening**: Multimodal deep PDF analysis against `full_text_acceptance_criteria`.
* **Dynamic Parameter Extraction**: Schema-validated parameter extraction with evidence quotes and confidence scores.
* **Composite Signal Scoring**: Sandboxed mathematical formula execution (`workspace.signal_score_code`).
* **Executive Reporting & Notification Dispatch**: Narrative synthesis and email delivery via Mailgun.

---

## 🚀 3. Pipeline Triggering Pathways & Concurrency Controls

The Systematic Literature Review (SLR) pipeline can be dispatched through **5 distinct, enterprise-grade execution channels**, all converging into the unified `ResearchAgentRunner` and `WorkflowDAG` orchestrator:

| Pathway | Interface / Entrypoint | Concurrency & Overlap Policy | Async Dispatch Mechanism |
| :--- | :--- | :--- | :--- |
| **1. Celery Beat Periodic Dispatcher** | `dispatch_due_workflow_schedules()` | `select_for_update(skip_locked=True)` + `prevent_overlap` check. If overlapping, advances `next_run_at` to prevent busy-spin. | Automated cron evaluation with staggered jitter ($0\text{s} - 45\text{s}$) to distribute worker load. |
| **2. Django Admin UI ("Run Now")** | Admin action / detail view: `admin:research_intelligence_workflowschedule_trigger` | `force=True` (allows manual execution override even if previous run is active). | `transaction.on_commit` Celery task dispatch with immediate UI flash message. |
| **3. Django REST API** | `POST /api/schedules/{id}/trigger/`<br/>`POST /api/pipeline-runs/` | Honors `prevent_overlap` (returns HTTP 200 with process ID or 409 Conflict if locked). | Non-blocking DRF viewset dispatching async Celery task. |
| **4. FastMCP SSE Agent Tools** | `start_research_agent(workspace_id, ...)`<br/>`trigger_search_job(...)` | Dynamic configuration overrides (e.g. `reprocess_existing`, `limit`, `n_last_days`). | Async Celery worker trigger returning instant execution payload and run UUID. |
| **5. Direct Engine / Programmatic Runner** | `ResearchAgentRunner.tick(process_id)` | Row-level locking on PostgreSQL (`select_for_update`). Protected against premature connection closure via `in_atomic_block` guard. | Direct DAG node evaluation and synchronous/asynchronous task dispatch. |

### Key Architectural Concurrency & Observability Guarantees:
1. **Overlap Prevention (`prevent_overlap=True`)**: Prevents duplicate executions if a previous `PipelineRun` is still in status `'running'` or `'pending'`.
2. **Decoupled Signals Observer**: Django `post_save` signals in `signals.py` observe `PipelineRun` and `ResearchAgentProcess` state changes and update the associated `WorkflowSchedule.last_status` via dual lookup (`last_pipeline_run_id` OR `schedule_id`).
3. **Failure Guardrails & Auto-Pause**: Automatically tracks `consecutive_failures_count` across recurring runs, auto-pausing (`is_active=False`) once `max_consecutive_failures` threshold is reached.
4. **Early Halting Safety**: When zero new papers are discovered (due to deduplication) or zero papers pass screening, the pipeline cleanly halts at that step (`stopped_at_step`, `stop_reason`) and sets `pipeline_run.status='completed'` with an informative `status_message`.
5. **Daylight Saving Time (DST) Support**: Leverages Python's native `zoneinfo.ZoneInfo` for accurate localized cron evaluations (e.g. Europe/Berlin, UTC, America/New_York) without 1-hour shifts during clock changes.

---

## 🔐 4. Authentication & Security Architecture

*(See [`docs/SECURITY.md`](../docs/SECURITY.md) for full threat model specification and RBAC matrix)*

* **JWT Web Authentication & Token Lifecycle**:
  * `POST /api/auth/login/`: Username/email + password login (throttled at 5 req/min against brute-force).
  * `POST /api/auth/logout/`: Immediately invalidates the refresh token on the token blacklist.
  * `POST /api/auth/refresh/`: Rotating token renewal with automatic blacklisting of previous refresh tokens.
  * `GET /api/auth/me/`: Returns user profile and workspace count.
  * `POST /api/auth/change-password/`: Enforces Django password complexity validators and revokes all active session tokens.
* **FastMCP Agent Authentication**:
  * Authenticates via `APIKey` (`key_id:secret`) with granular scopes (`workspaces:read`, `workspaces:write`, `runs:read`, `runs:write`, `prompts:read`, `prompts:write`).
* **Multi-Role Workspace Authorization (RBAC)**:
  * Each workspace member has a role (`admin`, `manager`, `researcher`) enforced on REST endpoints and FastMCP tools.
* **Automated Token Pruning (Celery Beat)**:
  * Periodic task `cleanup_expired_tokens_task` runs daily (every 24h) to prune expired blacklisted tokens from the database.

---

## 🧪 5. Testing & Verification

```bash
# Run the complete test suite (400+ tests in parallel, 0 tokens / in-memory SQLite)
./run_tests.sh

# Run specific test modules
./run_tests.sh research_intelligence.tests.test_api_security_fixes
./run_tests.sh research_intelligence.tests.test_jwt_auth
./run_tests.sh research_intelligence.tests.test_mcp_security_and_multitenancy
./run_tests.sh mcp_server
```
