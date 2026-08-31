# 📋 System Requirements Specification (SRS)
**Document Version:** 2.0.0  
**Target Audience:** Engineering Leads, Architects, AI Agents, and Product Stakeholders  

---

## 1. System Objective & Scope
The **Schwarz Research Intelligence (SRI)** platform is an enterprise-grade agentic AI platform designed for automated systematic literature reviews (SLRs), deep-tech competitive scouting, technology readiness level (TRL) assessment, and interactive scientific reasoning.

The system orchestrates an end-to-end 8-stage processing pipeline: multi-source ingestion, deduplication, abstract screening, parallel PDF downloading, layout OCR, full-text screening, schema-constrained parameter extraction, sandboxed AST signal scoring, executive narrative synthesis, transactional Mailgun digests, FastMCP tool execution, and grounded interactive paper chat.

---

## 2. Functional Requirements (FR)

### FR-1: Multi-Source Ingestion & Cross-Source Deduplication
The system must support automated ingestion of scientific papers and patents from multiple academic and patent data sources.
* **Supported Data Sources:**
  1. **arXiv:** Real-time retrieval of preprint metadata, abstracts, and open PDF endpoints.
  2. **OpenAlex:** Global scholarly entity graph querying and open-access metadata harvesting.
  3. **Lens.org:** Comprehensive patent database queries, citation links, and scholarly records.
  4. **PubMed / Europe PMC:** Biomedical literature retrieval (support for future expansions).
* **Multi-Stage Deduplication Engine:** Ingestion must compute deterministic document identifiers (DOI, arXiv ID, or content-based SHA-256 binary hash) to prevent duplicate processing across multi-source queries.
* **Configurable Scrapers:** Workspaces must support configuring search queries, sources, and schedule intervals.

### FR-2: Pluggable Document Parsing & OCR Pipeline
The system must expose a unified `BaseOCRProvider` interface to extract layout-preserving Markdown text from raw PDFs via `OCRProviderFactory`.
* **Docling:** Local high-fidelity layout analysis (tables, math equations, multi-column reading orders).
* **Mistral OCR:** High-accuracy cloud API engine for complex layouts.
* **PyPDF:** Lightweight, in-process fallback text extractor.
* **Multimodal Direct Pass (OCR Bypass):** The system must allow configuring `ocr_provider=None` to pass raw PDF binaries directly to multimodal LLMs (e.g. Gemini 3.7 Flash), eliminating OCR latency and cost when full-text parsing is unnecessary.

### FR-3: Pluggable LLM Provider Decoupling
The system must isolate core agent logic from specific LLM vendors via `BaseLLMProvider` and `LLMProviderFactory`:
* **Google GenAI / Vertex AI:** Primary high-performance driver (`google/gemini-3.7-flash`, `gemini-1.5-pro`) supporting multimodal PDF understanding, system instructions, and structured JSON schema enforcement.
* **OpenRouter:** Dynamic routing layer for alternative commercial and open-source models (Claude 3.5 Sonnet, Llama 3, Mixtral).
* **OpenAI:** Direct API compatibility layer.
* **Capabilities:** Pydantic/JSON schema validation, deterministic temperature controls, token budgeting, and exponential backoff retry policies.

### FR-4: Orchestrated Asynchronous Pipeline & Autonomous State Engine
Heavy compute steps must run asynchronously on distributed Celery workers with real-time auditability:
* **8-Stage Autonomous Pipeline Stages:**
  1. **Search & Ingestion:** Multi-source querying and deduplication.
  2. **Abstract Screening:** Evaluates paper title & abstract against `abstract_acceptance_criteria` and `abstract_rejection_criteria` (skippable via `skip_abstract_screening=True`). Halts early if 0 papers qualify.
  3. **Parallel PDF Download:** Multi-threaded fetching of qualifying PDFs to unified S3 storage.
  4. **Layout OCR Conversion:** Converts PDFs to Markdown (skipped if `ocr_provider=None`).
  5. **Full-Text Screening:** Deep multimodal analysis of full text/PDF against `full_text_acceptance_criteria` and `full_text_rejection_criteria`.
  6. **Dynamic Parameter Extraction:** Schema-validated extraction into `Extraction` records with confidence scores and evidence quotes.
  7. **Composite Signal Score Evaluation:** Sandboxed AST Python math evaluation of `workspace.signal_score_code` to calculate aggregated composite ranking scores (`paper.signal_score`).
  8. **Narrative Reporting & Synthesis:** Executive briefing generation, BibTeX reference compilation, and transactional email distribution.
* **Autonomous Agent State Machine:** Managed by `ResearchAgentProcess` with full state lifecycle: `initialized` ➔ `search` ➔ `download` ➔ `ocr` ➔ `screening` ➔ `extraction` ➔ `completed` (with support for `pause`, `resume`, `abort`, and mid-step rerun from specific DAG nodes).

### FR-5: Dynamic Parameter Extraction & Schema Customization
* Workspaces must allow users to define custom `ExtractionDefinition` models with dynamic JSON schemas, system prompts, target variables, and validation rules (`pass`, `warn`, `fail`).
* Extracted parameters must capture verbatim evidence quotes from the source text and model confidence ratings.
* Results must be queryable through a multi-dimensional matrix (`get_paper_extractions_matrix`).

### FR-6: Interactive Paper Chat & Scientific Reasoning Engine (`/ask`)
The platform must provide a conversational scientific reasoning interface allowing researchers to interrogate ingested literature:
* **Context Grounding:** The chat engine dynamically injects full PDF/OCR text, screening decisions, extraction parameter cards, and signal score metadata into the LLM context.
* **Precise Citations & Evidence Grounding:** Responses must include paragraph/page-level evidence citations to eliminate hallucinations.
* **Dual Execution Modes:**
  * *Asynchronous Celery Worker:* `POST /api/chat/` returns `202 Accepted` with background worker processing and `GET /api/chat/messages/{id}/` polling.
  * *Synchronous Direct Stream:* Supports streaming answers and tool calls in real time.
* **Multi-Turn Persistent Sessions:** Manages `ChatSession` and `ChatMessage` history per workspace and paper.

### FR-7: Model Context Protocol (FastMCP SSE Server)
The platform must expose its entire capability surface through the standard **Model Context Protocol (MCP)** on port 8001 (`/mcp/` / SSE):
* **Granular Scope-Based RBAC:** Enforces API key scopes (`workspaces:read`, `workspaces:write`, `runs:read`, `runs:write`, `prompts:read`, `prompts:write`).
* **Tool Catalog:**
  * *Workspaces:* `list_workspaces`, `get_workspace`, `create_workspace`, `update_workspace`, `add_workspace_member`.
  * *Autonomous Agents:* `start_research_agent`, `check_run_status`, `list_research_agents`, `get_research_agent_status`, `pause_research_agent`, `resume_research_agent`, `abort_research_agent`, `delete_research_agent`, `get_workflow_dag_schema`.
  * *Scrapers & Papers:* `list_scrapers`, `get_scraper`, `create_scraper`, `preview_search_query`, `list_papers`.
  * *Extraction & Matrices:* `list_extraction_definitions`, `create_extraction_definition`, `list_extractions`, `get_paper_extractions_matrix`.
  * *Paper Chat:* `ask_paper` (interactive scientific interrogation).
  * *Diagnostics:* `get_document_registry_stats`, `test_google_llm`, `list_user_activity_logs`.

### FR-8: Executive Briefing Narrative Synthesis & Mailgun Delivery
* **Narrative Synthesis:** Synthesis of weekly executive research briefs in Markdown and LaTeX with auto-generated BibTeX bibliographies.
* **Transactional Email Delivery:** Outbound email dispatch using Mailgun HTTP API (`research_intelligence.utils.mailer.send_mailgun_message`) for executive reports, pipeline run completion alerts, and subscriber digests.

---

## 3. Security & Safety Requirements (SR)

### SR-1: Sandboxed AST Mathematical Formula Execution
* The system allows workspaces to define custom mathematical ranking formulas in Python (`signal_score_code`).
* **AST Security Sandbox:** Execution is parsed into a Python Abstract Syntax Tree (AST) that verifies only whitelisted mathematical operations (`+`, `-`, `*`, `/`, `**`, `//`, `%`), assignments, conditionals (`if/elif/else`), and safe built-ins (`min`, `max`, `abs`, `round`, `sum`, `pow`).
* **Hard Blocked Constructs:** `import`, `exec`, `eval`, `open`, file I/O, `__builtins__`, network requests, and system calls are strictly blocked at parse time.

### SR-2: Multi-Tenant RBAC & Data Isolation
* **Workspace Boundary Isolation:** All papers, extractions, chat sessions, pipeline runs, and scraper definitions are partitioned under a `Workspace` foreign key.
* **Token Authentication & Stateless Protection:** JWT Bearer authentication with automatic token rotation. API requests clear session cookies to prevent header size inflation (preventing HTTP 431).
* **Storage Protection:** File storage paths are cryptographically sanitized (`workspaces/{ws_id}/runs/{run_id}/documents/{hash}/...`) to prevent directory traversal attacks.

---

## 4. Non-Functional Requirements (NFR)

### NFR-1: Scalability & High-Throughput Ingestion
* **Concurrent Workspaces:** Scale to $\ge 500$ parallel active research workspaces.
* **Batch Processing:** Support horizontal scaling of Celery workers to ingest and process 1,000+ scientific PDFs concurrently.
* **Document Registry Global Cache:** SHA-256 content deduplication prevents re-downloading and re-OCR parsing of identical PDFs across workspaces, saving bandwidth and processing time.

### NFR-2: Comprehensive End-to-End (E2E) Test Suite
The platform must maintain two orthogonal, automated E2E test suites:
1. **Frontend User Journeys (TypeScript & Playwright):**
   * Located in `tests_e2e/specs/` using Page Object Model (`tests_e2e/pages/`).
   * 6 complete user journeys: `01_auth_session_lifecycle`, `02_analyst_daily_review`, `03_manager_workspace_and_settings`, `04_scoring_and_methodology`, `05_interactive_paper_chat`, `06_end_to_end_researcher_flow`.
   * Executable via `./tests_e2e/run_frontend_e2e.sh`, `npm test`, or `npm run test:ui`.
2. **Backend Live Pipeline E2E Simulator (Python):**
   * Located in `tests_e2e/scenarios/` and executed via `./tests_e2e/run_e2e.sh`.
   * 11 orthogonal scenarios: `full_slr_pipeline`, `chat_multiturn`, `agent_lifecycle`, `pipeline_reprocessing`, `cross_source_dedup`, `quota_guard`, `mcp_protocol`, `rbac_data_isolation`, `mid_step_rerun`, `chat_hallucination_guard`, `concurrent_agents_load`.
3. **Unit Test Suite:**
   * 153+ unit/integration tests running against In-Memory SQLite in $\approx 8$ seconds via `./run_tests.sh` with 100% pass rate.

### NFR-3: S3-Compatible Storage Strategy
* All binary assets (PDFs, Markdown conversions, LaTeX reports) are stored in S3-compatible storage (Cloudflare R2, AWS S3, MinIO).
* Secure streaming download endpoints and pre-signed URL capabilities.

### NFR-4: CI/CD & Cloud Infrastructure Automation
* **Containerization:** Multi-container Docker Compose and Cloud Foundry deployment architecture (Postgres, Redis, MinIO, Django REST API, FastMCP server, Next.js frontend, Celery workers, Celery beat).
* **Multi-Environment Deployments:** Production (`sri-prod.apps.01.cf.eu01.onstackit.cloud`) and Staging (`sri.soinventive.co.uk`) with automated zero-downtime rolling deploys and health checking.
* **Local CI/CD Automation:** Container rebuild, bake caching, and restart automation via `./local_cicd/` and `./restart_containers.sh`.
