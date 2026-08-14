# 🤖 AGENTS.md - Schwarz Research Intelligence System Guide

> **Target AI Models**: Google Gemini (3.7 Flash & Pro), Anthropic Claude (3.5 Sonnet / 3 Opus), Antigravity IDE, Cursor, and FastMCP SSE Clients.  
> **Repository Scope**: Systematic Literature Review (SLR) & Deep Tech Competitive Intelligence Platform.

---

## 🚀 1. Executive Summary & Project Purpose

**Schwarz Research Intelligence** is an enterprise-grade platform designed for automated, AI-driven academic literature review, deep-tech scouting, and parameter extraction.

It orchestrates a 5-step processing pipeline:
1. **Search & Ingestion**: Multi-source querying (ArXiv, OpenAlex, Lens, PubMed) with title/DOI/arXiv ID deduplication.
2. **Parallel PDF Download**: Multi-threaded document fetching to unified storage (`papers/{hash}/paper.pdf`).
3. **Layout OCR Conversion**: Conversion to structured Markdown text via local `pypdf` or `Mistral OCR API` (automatically skipped if `ocr_provider` is unconfigured).
4. **Structured 2-Stage Screening**:
   - **Abstract Screening**: Evaluates paper title & abstract against `abstract_acceptance_criteria` and `abstract_rejection_criteria`.
   - **Full-Text Screening**: Performs deep analysis of OCR Markdown / Multimodal PDF binary against `full_text_acceptance_criteria` and `full_text_rejection_criteria`.
5. **Dynamic Parameter Extraction**: Schema-validated Pydantic/JSON parameter extraction into `Extraction` objects with evidence quotes, confidence scores, and validation flags (`pass`, `warn`, `fail`).

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
 │   └── Step 5: execute_extraction_job  (tasks/step_5_extraction/extract.py)  │
 └─────────────────────────────────┬───────────────────────────────────────────┘
                                   │
 ┌─────────────────────────────────▼───────────────────────────────────────────┐
 │                      DATA & PERSISTENCE LAYER                               │
 │   PostgreSQL (Prod: DB_HOST=db)  │  SQLite In-Memory (Test Runner)          │
 │   Celery + Redis Task Queue      │  Django Storage (Local/S3/GCS)           │
 └─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 3. Rules & Guidelines for AI Coding Agents

### Rule 1: Database & Testing Standard
- **Unit Tests MUST Run on In-Memory SQLite**: Django settings (`settings.py`) automatically detect test runs (`'test' in sys.argv`) and force `:memory:` SQLite.
- **Production Postgres Preserved**: Environment variables (`DB_HOST=db`, `DB_NAME=research_intelligence`, `DB_USER=postgres`) in `docker-compose.yml` MUST remain intact.
- **Verification Requirement**: ALWAYS run `.venv/bin/python backend/manage.py test research_intelligence.tests` after backend modifications. Never declare success without 100% test pass.

### Rule 2: Workspace Criteria Dual-Stage Isolation
- **Abstract Screening Criteria**: Use `workspace.get_abstract_acceptance_criteria()` and `workspace.get_abstract_rejection_criteria()`.
- **Full-Text Screening Criteria**: Use `workspace.get_full_text_acceptance_criteria()` and `workspace.get_full_text_rejection_criteria()`.
- **No Shared Criteria Overwrite**: Do NOT re-introduce legacy single criteria fields (`acceptance_criteria` / `rejection_criteria`).

### Rule 3: FastMCP Tool Implementation Pattern
- Define tool logic in `backend/research_intelligence/mcp/tools/<domain>.py`.
- Register the tool in `backend/research_intelligence/mcp/server.py` using `@mcp.tool()` and `@with_db_connection`.
- Ensure exact scope checking via `check_scope(api_key, "workspaces:read" | "workspaces:write")`.
- Maintain rich docstrings explaining every parameter and output payload so LLM clients (Claude, Gemini, OpenAI) understand tool intent.

### Rule 4: Multi-Threading & DB Connection Safety
- Worker loops inside Celery tasks or `ThreadPoolExecutor` MUST invoke `django.db.close_old_connections()` at the start of every thread iteration.
- Enforce single-threaded concurrency fallback (`worker_concurrency = 1`) when `connection.vendor == 'sqlite'` to prevent SQLite database lock contention during test execution.

---

## 🔌 4. FastMCP & REST API Reference

### Key MCP Tools Exposed
| Tool Name | Scope | Description |
| :--- | :--- | :--- |
| `create_workspace` | `workspaces:write` | Creates isolated workspace with distinct `abstract_*` and `full_text_*` criteria. |
| `update_workspace` | `workspaces:write` | Updates workspace criteria, OCR provider, or quota limits. |
| `get_workspace` | `workspaces:read` | Returns full workspace hierarchy, scrapers, OCR engine, and definitions. |
| `start_research_agent` | `workspaces:write` | Launches autonomous state machine process (`ResearchAgentProcess`). |
| `get_research_agent_status` | `workspaces:read` | Returns process state, active step, history audit trail, and paper metrics. |
| `pause_research_agent` | `workspaces:write` | Pauses running state engine process. |
| `resume_research_agent` | `workspaces:write` | Resumes paused state engine process. |
| `abort_research_agent` | `workspaces:write` | Aborts agent process and cancels background Celery tasks. |
| `delete_research_agent` | `workspaces:write` | Purges agent process, pipeline run, downloaded files, and extractions. |
| `list_extractions` | `workspaces:read` | Queries extracted parameter objects by workspace or definition ID. |

### REST API Endpoints (`/api/`)
- `GET /api/workspaces/`, `POST /api/workspaces/`
- `GET /api/agents/`, `POST /api/agents/` (Supports `/pause/`, `/resume/`, `/abort/`)
- `GET /api/extractions/`, `POST /api/extractions/`
- `GET /api/pipeline-runs/`, `POST /api/pipeline-runs/`

---

## 🧪 5. Testing & Validation Protocol

```bash
# Run complete test suite (54+ tests across all modules)
.venv/bin/python backend/manage.py test research_intelligence.tests

# Run specific task test module
.venv/bin/python backend/manage.py test research_intelligence.tests.tasks.test_4_screening
```
