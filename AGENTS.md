# 🤖 AGENTS.md - Schwarz Research Intelligence System Guide

> **Target AI Models**: Google Gemini (3.7 Flash & Pro), Anthropic Claude (3.5 Sonnet / 3 Opus), Antigravity IDE, Cursor, and FastMCP SSE Clients.  
> **Repository Scope**: Systematic Literature Review (SLR) & Deep Tech Competitive Intelligence Platform.

---

## 🚀 1. Executive Summary & Project Purpose

**Schwarz Research Intelligence** is an enterprise-grade platform designed for automated, AI-driven academic literature review, deep-tech scouting, and parameter extraction.

It orchestrates a 6-step processing pipeline:
1. **Search & Ingestion**: Multi-source querying (ArXiv, OpenAlex, Lens, PubMed) with title/DOI/arXiv ID deduplication.
2. **Parallel PDF Download**: Multi-threaded document fetching to unified storage (`workspaces/{ws_id}/runs/{run_id}/documents/{hash}/original.pdf`).
3. **Layout OCR Conversion**: Conversion to structured Markdown text via local `pypdf`, `Mistral OCR API`, or `gemini` (automatically skipped if `ocr_provider` is `None` to enable direct multimodal PDF analysis in subsequent steps).
4. **Structured 2-Stage Screening**:
   - **Abstract Screening**: Evaluates paper title & abstract against `abstract_acceptance_criteria` and `abstract_rejection_criteria`.
   - **Full-Text Screening**: Performs deep multimodal analysis of raw PDF binaries (or OCR Markdown if generated) against `full_text_acceptance_criteria` and `full_text_rejection_criteria` using `google/gemini-3.7-flash`.
5. **Dynamic Parameter Extraction**: Schema-validated Pydantic/JSON parameter extraction into `Extraction` objects with evidence quotes, confidence scores, and validation flags (`pass`, `warn`, `fail`).
6. **Composite Signal Score Evaluation**: Sandboxed, AST-secured execution of custom Python mathematical formulas defined on `workspace.signal_score_code` to calculate aggregated composite ranking scores (`paper.signal_score`, `PaperMetric.signal_score`).

---

## 🏗️ 2. Architectural Blueprint

```
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                           INTERFACE LAYER                                   │
 │   ┌───────────────────────────┐           ┌─────────────────────────────┐   │
 │   │  FastMCP SSE Server       │           │  Django REST API (DRF)      │   │
 │   │  (Port 8001 / mcp/tools/) │           │  (Port 8000 / api/views/)   │   │
 │   └─────────────┬─────────────┘           └──────────────┬──────────────┘   │
 └─────────────────┼────────────────────────────────────────┼──────────────────┘
                   │                                        │
 ┌─────────────────▼────────────────────────────────────────▼──────────────────┐
 │                     AUTONOMOUS STATE ENGINE & TASKS                         │
 │  ResearchAgentProcess State Machine (tasks/orchestrator/agent_engine.py)   │
 │   ├── Step 1: execute_workspace_search (tasks/step_1_search/search.py)      │
 │   ├── Step 2: execute_pdf_download_job (tasks/step_2_download/fetch.py)    │
 │   ├── Step 3: execute_ocr_job         (tasks/step_3_ocr/convert.py)        │
 │   ├── Step 4: execute_screening_job   (tasks/step_4_screening/abstract.py)  │
 │   │           execute_full_text_screening (step_4_screening/full_text.py)  │
 │   ├── Step 5: execute_extraction_job  (tasks/step_5_extraction/extract.py)  │
 │   └── Step 6: execute_signal_score_job (tasks/step_6_signal_score/scorer.py)│
 └─────────────────────────────────┬───────────────────────────────────────────┘
                                   │
 ┌─────────────────────────────────▼───────────────────────────────────────────┐
 │                      DATA & PERSISTENCE LAYER                               │
 │   PostgreSQL (Prod: DB_HOST=db)  │  SQLite In-Memory (Test Runner)          │
 │   Celery + Redis Task Queue      │  Django Storage (Local/S3/MinIO)         │
 └─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 3. Rules & Guidelines for AI Coding Agents

### Rule 1: Database & Testing Standard
- **Unit Tests MUST Run on In-Memory SQLite**: Django settings (`settings.py`) automatically detect test runs (`'test' in sys.argv`) and force `:memory:` SQLite.
- **Production Postgres Preserved**: Environment variables (`DB_HOST=db`, `DB_NAME=research_intelligence`, `DB_USER=postgres`) in `docker-compose.yml` MUST remain intact.
- **Verification Requirement**: ALWAYS run `.venv/bin/python backend/manage.py test research_intelligence.tests` after backend modifications. Never declare success without 100% test pass (92+ tests).

### Rule 2: Workspace Criteria Dual-Stage Isolation & Defaults
- **Abstract Screening Criteria**: Use `workspace.get_abstract_acceptance_criteria()` and `workspace.get_abstract_rejection_criteria()`.
- **Full-Text Screening Criteria**: Use `workspace.get_full_text_acceptance_criteria()` and `workspace.get_full_text_rejection_criteria()`.
- **Default LLM Model**: `google/gemini-3.7-flash`.
- **Default OCR Engine**: `None` (OCR is skipped by default so full PDF binaries are passed directly into multimodal Gemini 3.7 Flash during screening).

### Rule 3: FastMCP Tool Implementation Pattern
- Define tool logic in `backend/research_intelligence/mcp/tools/<domain>.py`.
- Register the tool in `backend/research_intelligence/mcp/server.py` using `@mcp.tool()` and `@with_db_connection`.
- Ensure exact scope checking via `check_scope(api_key, "workspaces:read" | "workspaces:write" | "runs:read" | "runs:write" | "prompts:read" | "prompts:write")`.
- Maintain rich docstrings explaining every parameter and output payload so LLM clients (Claude, Gemini, OpenAI) understand tool intent.

### Rule 4: Multi-Threading & DB Connection Safety
- Worker loops inside Celery tasks or `ThreadPoolExecutor` MUST invoke `django.db.close_old_connections()` at the start of every thread iteration.
- Enforce single-threaded concurrency fallback (`worker_concurrency = 1`) when `connection.vendor == 'sqlite'` to prevent SQLite database lock contention during test execution.

### Rule 5: Run Lifecycle & Storage Cleanup
- When deleting a `PipelineRun` or `ResearchAgentProcess`, MCP tools MUST invoke recursive storage deletion to remove the run directory (`workspaces/{ws_id}/runs/{run_id}/`) and all related files (`.pdf`, `.md`, `.json`, `.txt`), while cascading deletion across DB records (`ComponentRun`, `Paper`, `Extraction`, `PaperMetric`, `NarrativeReport`).
- Status tools (`get_pipeline_run_status`, `get_research_agent_status`) calculate dynamic metrics: `total_papers_fetched`, `downloaded_documents_count`, `ocr_converted_documents_count`, `screened_documents_count`, `extractions_count`, and the `storage` footprint (`total_files`, `size_bytes`, `size_formatted`).

### Rule 6: Email Notifications & Mailgun Integration
- **Mandatory Mailer Helper**: To send ANY emails or notifications (executive briefings, run alerts, subscriber digests), ALWAYS use `send_mailgun_message` from `research_intelligence.utils.mailer` (or `utils.mailer`).
- **Avoid raw SMTP**: The platform routes all outbound transactional email directly via Mailgun HTTP API (`MAILGUN_API_KEY`, `MAILGUN_API_URL`, `MAILGUN_SENDER_DOMAIN`).
- **Signature & Usage**:
  ```python
  from research_intelligence.utils.mailer import send_mailgun_message

  success, resp_or_err = send_mailgun_message(
      to_email="recipient@example.com",
      subject="Systematic Review Complete",
      text="Your research pipeline run finished.",
      html="<h1>Review Ready</h1><p>...</p>",
      template_name=None,  # optional template to render
      context=None,
  )
  ```

### Rule 7: Sandboxed Python Signal Score Formulas (`signal_score_code`)
- **Execution & Scope**: Evaluated in Step 6 via AST sandbox (`tasks/step_6_signal_score/scorer.py`).
- **Available Variables**: Extraction definitions are automatically available as sanitized snake_case variables:
  - `trl_level` (from 'TRL Level')
  - `novelty_score` (from 'Novelty Score')
  - `fit_score` / `schwarz_fit` (from 'Schwarz Fit' or exit metric)
  - `commercial_viability` (from 'Commercial Viability')
  - `rigour_score` (from 'Rigour Score')
  - Any custom extraction definition name sanitized to `snake_case`.
- **Allowed Operations**: Math arithmetic (`+`, `-`, `*`, `/`, `**`, `//`, `%`), conditions (`if/elif/else`), assignments, comparisons, and built-ins (`min`, `max`, `abs`, `round`, `sum`, `pow`). Blocked: `import`, `exec`, `eval`, `open`, I/O.
- **Representative Code Examples**:
  - *Example A (Weighted Linear Metric)*:
    ```python
    score = 0.4 * fit_score + 0.3 * novelty_score + 0.3 * trl_level
    return round(score, 2)
    ```
  - *Example B (Conditional Branching & Threshold Gating)*:
    ```python
    k = fit_score + 2.0 * novelty_score + trl_level
    if k > 10.0:
        return 5.0
    else:
        return 99.0
    ```
  - *Example C (Tiered Gated Multiplier)*:
    ```python
    if trl_level < 3.0:
        return 0.0
    base = 0.6 * fit_score + 0.4 * novelty_score
    return round(base * (1.2 if trl_level >= 7.0 else 1.0), 2)
    ```

---

## 🔌 4. FastMCP & REST API Reference

### Comprehensive MCP Tools Catalog (`Port 8001 / SSE`)

#### 1. Workspaces & Access (`tools/workspaces.py`)
| Tool Name | Scope | Description |
| :--- | :--- | :--- |
| `list_workspaces` | `workspaces:read` | Lists all workspaces accessible to the authenticated user. |
| `get_workspace` | `workspaces:read` | Returns full workspace hierarchy, criteria, scrapers, OCR engine, and definitions. |
| `create_workspace` | `workspaces:write` | Creates isolated workspace with distinct `abstract_*` / `full_text_*` criteria, default `google/gemini-3.7-flash`, and `ocr_provider=None`. |
| `update_workspace` | `workspaces:write` | Updates workspace criteria, OCR provider, LLM provider/model, or quota limits. |
| `add_workspace_member` | `workspaces:write` | Adds user membership to a workspace with role (`admin`, `manager`, `researcher`). |

#### 2. Autonomous Research Agents (`tools/agent_processes.py`) — **RECOMMENDED PRIMARY ORCHESTRATOR**
| Tool Name | Scope | Description |
| :--- | :--- | :--- |
| `start_research_agent` | `workspaces:write` | **Primary Entrypoint**: Launches autonomous state machine process (`ResearchAgentProcess`) executing all steps 1-6 automatically. Supports `reprocess_existing=True` to re-screen/extract existing workspace papers. |
| `list_research_agents` | `workspaces:read` | Lists all research agent processes for a workspace with current state and runtime. |
| `get_research_agent_status` | `workspaces:read` | Returns agent state (`initialized`, `search`, `download`, `ocr`, `screening`, `extraction`, `completed`, `paused`, `aborted`), active step, audit trail, paper metrics, and storage footprint. |
| `wait_for_research_agent` | `workspaces:read` | **Synchronous Wait**: Blocks until agent reaches `completed`/`failed` or timeout, returning full report and token/cost metrics. |
| `pause_research_agent` | `workspaces:write` | Pauses running state engine process. |
| `resume_research_agent` | `workspaces:write` | Resumes paused state engine process from active step. |
| `abort_research_agent` | `workspaces:write` | Aborts agent process and cancels background Celery tasks. |
| `delete_research_agent` | `workspaces:write` | Purges agent process, pipeline run, downloaded files in storage, and DB extractions. |
| `get_workflow_dag_schema` | `workspaces:read` | Returns the complete SLR DAG graph topology, execution dependencies, input contracts, and output contracts for all nodes. |

#### 3. Data Scrapers & Search (`tools/scrapers.py`)
| Tool Name | Scope | Description |
| :--- | :--- | :--- |
| `list_scrapers` | `workspaces:read` | Lists active scraper configurations for a workspace (`arxiv`, `openalex`, `lens`). |
| `get_scraper` | `workspaces:read` | Returns detailed scraper configuration by ID. |
| `create_scraper` | `workspaces:write` | Configures a new paper ingestion query for a target provider. |
| `update_scraper` | `workspaces:write` | Modifies search query, provider, or result limits. |
| `delete_scraper` | `workspaces:write` | Removes a scraper configuration from a workspace. |
| `preview_search_query` | `workspaces:read` | Dry-run search query against ArXiv/OpenAlex/Lens without saving to DB. |
| `list_papers` | `workspaces:read` | Lists ingested papers with title, authors, abstract, PDF path, and screening status. |

#### 4. Dynamic Parameter Extraction (`tools/extraction_definitions.py`)
| Tool Name | Scope | Description |
| :--- | :--- | :--- |
| `list_extraction_definitions` | `prompts:read` | Lists custom extraction targets for a workspace. |
| `get_extraction_definition` | `prompts:read` | Returns schema, system prompt, and target model for a definition. |
| `create_extraction_definition` | `prompts:write` | Creates new dynamic extraction target (JSON schema, prompts, `llm_model`). |
| `update_extraction_definition` | `prompts:write` | Updates schema, prompts, or model for an extraction target. |
| `delete_extraction_definition` | `prompts:write` | Removes extraction definition and associated extractions. |

#### 5. Manual Step-by-Step Execution (`tools/pipeline_runs.py`, `tools/extractions.py`) — *For isolated component testing only*
| Tool Name | Scope | Description |
| :--- | :--- | :--- |
| `trigger_search_job` | `runs:write` | [Manual Only] Triggers isolated Step 1: Search & Ingestion. |
| `trigger_pdf_download_job` | `runs:write` | [Manual Only] Triggers isolated Step 2: Parallel PDF Download. |
| `trigger_ocr_job` | `runs:write` | [Manual Only] Triggers isolated Step 3: Layout OCR Conversion. |
| `trigger_screening_job` | `runs:write` | [Manual Only] Triggers isolated Step 4: 2-Stage Abstract/Full-Text Screening. |
| `trigger_extraction_job` | `runs:write` | [Manual Only] Triggers isolated Step 5: Dynamic Parameter Extraction. |
| `list_pipeline_runs` | `runs:read` | Lists pipeline runs with status and component run tree. |
| `get_pipeline_run_status` | `runs:read` | Detailed run status with `triggered_by` user, paper counts, downloaded document metrics, and extractions matrix preview. |
| `get_component_run_status` | `runs:read` | Detailed status and error logs for an individual component step run. |
| `abort_job` | `runs:write` | Aborts a pipeline run or individual component run. |
| `delete_pipeline_run` | `runs:write` | Recursively deletes storage folder and purges pipeline run records from DB. |
| `list_extractions` | `workspaces:read` | Queries extracted parameter objects filtered by workspace, definition, run, or paper. |
| `get_paper_extractions_matrix` | `workspaces:read` | **Primary Tool for Results & Scorecards**: Aggregates all accepted papers with their extracted parameters, exit metrics, and justifications in a single call. |
| `get_extraction` | `workspaces:read` | Returns single extraction record with evidence quotes and confidence score. |

#### 6. Diagnostics & Audit (`tools/llm_test.py`, `tools/activity_logs.py`, `tools/document_registry.py`)
| Tool Name | Scope | Description |
| :--- | :--- | :--- |
| `get_document_registry_stats` | `workspaces:read` | Returns global cache efficiency, bandwidth saved, total cached documents, and top reused papers. |
| `test_google_llm` | `workspaces:read` | Validates Google GenAI / Vertex AI connectivity with `gemini-3.7-flash` and checks credentials. |
| `list_user_activity_logs` | `workspaces:read` | Queries security audit trail and MCP tool execution history. |

---

### REST API Endpoints (`/api/`)
- `GET /api/workspaces/`, `POST /api/workspaces/`
- `GET /api/agents/`, `POST /api/agents/` (Supports `/pause/`, `/resume/`, `/abort/`)
- `GET /api/extractions/`, `POST /api/extractions/`
- `GET /api/pipeline-runs/`, `POST /api/pipeline-runs/`
- `GET /admin/storage-browser/` (Admin Django Storage Browser with timestamps & sizes)

---

## 🧪 5. Testing & Validation Protocol

```bash
# Run complete test suite in parallel (~8s across 153+ tests)
./run_tests.sh

# Run specific task test module
./run_tests.sh research_intelligence.tests.test_pdf_cache

# Run FastMCP test suite
./run_tests.sh research_intelligence.tests.test_mcp_server
```
