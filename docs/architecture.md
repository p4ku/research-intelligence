# 🏛️ Research Intelligence System Architecture & Pipelines

This document describes the technical architecture and pipeline stages of the **Schwarz Research Intelligence** platform.

---

## 1. High-Level System Architecture

The system is designed as a secure, tenant-isolated architecture consisting of a modern Next.js frontend, a robust Django REST API backend, a dedicated FastMCP SSE server, Celery-based asynchronous task distribution workers, and persistent PostgreSQL / Object Storage.

![System Architecture](./images/architecture.png)

### Core Components

1.  **Users / Scientists & MCP AI Agents**: Access the system via HTTPS/WSS (Web Dashboard & Django Admin) or via SSE (Claude Code, Cursor, MCP clients).
2.  **Reverse Proxy / Router**: Acts as the ingress routing layer, forwarding frontend requests to Next.js, API/Admin calls to Django, and `/sse` / `/messages` to FastMCP.
3.  **Next.js Dashboard / SPA**: The dashboard where researchers review technology scorecards, examine parameter matrices, query papers, and monitor live research progress.
4.  **Django REST API & Admin Portal**: Serves REST endpoint logic, handles authentication, workspace configurations, export/import bundles, and orchestrates pipeline runs.
5.  **FastMCP Server**: Exposes rich Model Context Protocol tools for Claude Code, Cursor, and autonomous agent orchestration (`start_research_agent`, `check_run_status`, `get_paper_extractions_matrix`, `ask_paper`).
6.  **Redis**:
    *   Acts as the **Celery Message Broker** to route tasks to specific worker queues.
    *   Serves as a high-performance **Cache** layer for session management and transient state.
7.  **PostgreSQL**:
    *   Stores relational models (Workspaces, Extraction Definitions, Scrapers, Pipelines, Papers, Extractions, Metrics, Subscribers, Audit Logs).
    *   Utilizes the `pgvector` extension for semantic indexing and context retrieval.
8.  **Celery Pipeline Workers**: Distributed asynchronous execution agents performing heavy compute operations like querying academic APIs, downloading PDFs in parallel, running multimodal LLMs (Gemini 3.7 Flash), AST sandboxed signal scoring, and synthesizing executive briefings.
9.  **MinIO / S3 Object Storage**:
    *   Acts as the S3-compatible object storage backend with tenant and run isolation.
    *   Stores raw source files (PDFs), layout-preserving Markdown conversions, and generated narrative briefings.

---

## 2. Systematic Literature Review (SLR) DAG Pipeline Stages

The platform implements an 8-stage Directed Acyclic Graph (DAG) pipeline designed for maximum speed, compute efficiency, and rigorous academic validation.

![Pipeline Stages](./images/pipeline_stages.png)

### Sequential Stages & Dependency Flow

1.  **Step 1: Search & Ingestion** (`SearchNode`):
    *   Queries external repositories (**arXiv**, **OpenAlex**, **Lens.org**) based on workspace scrapers.
    *   Performs real-time deduplication across Title, DOI, and arXiv ID against existing workspace papers.
    *   Creates candidate `Paper` records with `screening_status='pending'`.
2.  **Step 2: Abstract Screening** (`AbstractScreeningNode`):
    *   *AI Triage Stage*: Evaluates paper titles and abstracts against workspace inclusion/exclusion criteria using **Google Gemini 3.7 Flash**.
    *   Classifies papers as `abstract_passed` or `rejected`.
    *   Automatically skipped if `skip_abstract_screening=True`. Halts gracefully if 0 papers pass to save bandwidth and compute.
3.  **Step 3: Parallel PDF Download** (`DownloadNode`):
    *   Multi-threaded fetching targeting **only papers that passed Abstract Screening** (or all candidate papers if abstract screening was skipped).
    *   Cross-run and cross-workspace deduplication using content-addressable **DocumentRegistry** (SHA-256 hash cache).
4.  **Step 4: Layout OCR Parsing** (`OCRNode`):
    *   Converts PDFs to Markdown via local `PyPDF`, `Mistral OCR API`, or `Gemini Vision`.
    *   **Automatically skipped by default** (`ocr_provider=None`), passing native PDF binaries directly into multimodal Gemini 3.7 Flash.
5.  **Step 5: Full-Text Screening** (`FullTextScreeningNode`):
    *   Deep multimodal analysis of full PDF binaries (or OCR Markdown) against strict workspace `full_text_acceptance_criteria` and `full_text_rejection_criteria`.
    *   Assigns `full_text_passed` / `accepted` or `rejected` with structured decision categories and evidence quotes.
6.  **Step 6: Dynamic Parameter Extraction** (`ExtractionNode`):
    *   Extracts schema-validated JSON parameters (TRL levels, commercial viability, experimental specifications, patent claims) defined in workspace `ExtractionDefinition` models.
    *   Captures verbatim evidence quotes, confidence scores, and validation flags (`pass`, `warn`, `fail`).
7.  **Step 7: Composite Signal Score Evaluation** (`SignalScoreNode`):
    *   Executes custom Python mathematical formulas defined in `workspace.signal_score_code` inside an AST-secured sandbox.
    *   Computes composite ranking scores (`paper.signal_score`) combining TRL, Novelty, and Strategic Fit.
8.  **Step 8: Executive Narrative Reporting & Notification Dispatch** (`ReportingNode`):
    *   Synthesizes executive narrative briefings.
    *   Dispatches transactional HTML email digests and scorecards to subscribers via **Mailgun API**.

---

## 3. Pluggable LLM Providers

To prevent vendor lock-in and enable seamless failover, the core LLM execution layer is decoupled from concrete API endpoints. The system uses a factory pattern to resolve models dynamically.

![LLM Providers](./images/llm_providers.png)

### Pluggable Architecture Components

1.  **Application Layer**: Celery worker tasks and Django API services request LLM generations through the provider factory.
2.  **LLM Abstraction Layer**:
    *   `LLMProviderFactory` resolves the correct driver configuration (from workspace settings).
    *   `BaseLLMProvider` acts as the interface, enforcing support for structured JSON schema outputs, system prompts, reasoning effort budgets, and temperature controls.
3.  **Concrete Drivers**:
    *   `GoogleLLMProvider` connects directly to Google Cloud Vertex AI / GenAI (default: `google/gemini-3.7-flash` with thinking reasoning effort support).
    *   `OpenRouterLLMProvider` handles fallback API calls through OpenRouter (allowing alternate models like Claude 3.5 Sonnet, Llama 3, etc.).
4.  **External Endpoints**: Drivers connect securely via TLS/HTTPS to target endpoints using workspace credentials.

---

## 4. Pluggable OCR Providers

To ensure flexibility in converting document structures (PDF layouts to semantic Markdown), the platform abstracts PDF conversions via pluggable OCR engines.

![OCR Providers](./images/ocr_providers.png)

### Pluggable Architecture Components

1.  **Application Layer**: Celery worker tasks execute the `execute_ocr_job`, retrieving the workspace-configured OCR provider from the factory.
2.  **OCR Abstraction Layer**:
    *   `OCRProviderFactory` resolves the correct driver based on workspace configurations.
    *   `BaseOCRProvider` defines the standardized conversion contracts (`convert(pdf_path)` returning layout-preserving Markdown or HTML).
3.  **Concrete Drivers & Backends**:
    *   `None / Skip OCR` (**Default**): Skips text layout parsing and passes native PDF binary directly to multimodal Gemini 3.7 Flash.
    *   `GeminiOCRProvider`: High-accuracy cloud layout parser using Google Gemini Vision.
    *   `MistralOCRProvider`: High-fidelity cloud fallback API (Mistral OCR endpoint).
    *   `PyPDFOCRProvider`: Lightweight, local in-process fallback using standard text extraction.
