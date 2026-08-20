# 🧠 Schwarz Research Intelligence

> **Enterprise-Grade AI Platform for Autonomous Scientific Literature Review, Deep Tech Scouting & Parameter Extraction.**  
> Powered by **FastMCP (Model Context Protocol)**, **Django REST Framework**, and **Google GenAI / Gemini 3.7 Flash** (hosted on Schwarz Digits Cloud).

---

## 📋 1. System Overview

**Schwarz Research Intelligence** is an enterprise-grade platform designed for automated, AI-driven academic literature review, competitive technology scouting, and parameter extraction.

It orchestrates a 5-step processing pipeline driven by an autonomous **Research Agent Process** state machine:

```mermaid
graph TD
    UserQuery[User Request / Client Trigger] --> InterfaceLayer{Interface Layer}
    InterfaceLayer -->|FastMCP SSE Port 8001| FastMCP[FastMCP Server]
    InterfaceLayer -->|REST API Port 8000| DRF[Django REST API]
    
    FastMCP --> AgentEngine[ResearchAgentProcess State Machine Engine]
    DRF --> AgentEngine
    
    subgraph PipelineExecution ["5-Step Processing Pipeline"]
        AgentEngine --> Step1[Step 1: Search & Ingestion<br/>arXiv, OpenAlex, Lens, PubMed]
        Step1 --> Step2[Step 2: Multi-Threaded Download<br/>papers/hash/paper.pdf]
        Step2 --> Step3{Step 3: OCR Conversion}
        Step3 -->|ocr_provider set| PyPDF_Mistral[PyPDF / Mistral OCR -> Markdown]
        Step3 -->|ocr_provider is None| SkipOCR[Auto-Skip OCR Step]
        PyPDF_Mistral --> Step4
        SkipOCR --> Step4
        Step4[Step 4: Two-Stage Screening] --> Stage4A[Abstract Screening<br/>abstract_* criteria]
        Stage4A --> Stage4B[Full-Text Screening<br/>full_text_* criteria]
        Stage4B --> Step5[Step 5: Dynamic Parameter Extraction<br/>Pydantic JSON & Evidence Quotes]
    end
    
    Step5 --> DB[(PostgreSQL Prod / SQLite Test)]
    Step5 --> Storage[(Django Storage / S3 / MinIO)]
    Step5 --> EmailNotifier[Completion Email Notifier]
```

---

## 🚀 2. Core Architectural Features

### 1. Autonomous Research Agent State Machine (`ResearchAgentProcess`)

The state engine (`tasks/orchestrator/agent_engine.py`) coordinates transitions through state checkpoints, handling background celery job execution, lifecycle interruptions (Pause, Resume, Abort), and email summaries:

```mermaid
graph TD
    Start([User / FastMCP Client / REST API Triggers Agent]) --> Initialized[State: initialized<br/>Creates ResearchAgentProcess & PipelineRun]
    
    Initialized --> SearchStep[Step 1: Search & Ingestion<br/>State: search<br/>Queries scrapers & deduplicates metadata]
    
    SearchStep --> DownloadStep[Step 2: PDF Download<br/>State: download<br/>Fetches PDFs to unified storage]
    
    DownloadStep --> OCRCheck{ocr_provider configured?}
    
    OCRCheck -->|Yes: pypdf / mistral| OCRStep[Step 3: OCR Conversion<br/>State: ocr<br/>Parses layout to structured Markdown]
    OCRCheck -->|No: ocr_provider is None| SkipOCR[Auto-Skip OCR Step<br/>Direct pass-through]
    
    OCRStep --> AbstractScreening[Step 4A: Abstract Screening<br/>State: screening<br/>Evaluates abstract_* criteria]
    SkipOCR --> AbstractScreening
    
    AbstractScreening --> FullTextScreening[Step 4B: Full-Text Screening<br/>State: screening<br/>Evaluates full_text_* criteria]
    
    FullTextScreening --> ExtractionStep[Step 5: Parameter Extraction<br/>State: extraction<br/>Extracts Pydantic JSON & evidence quotes]
    
    ExtractionStep --> Completed([State: completed<br/>Sends summary emails to workspace members])
    
    subgraph Controls ["Agent Process Lifecycle Controls"]
        PauseCommand[pause_research_agent] -.->|State: paused| AgentPaused[Process Paused]
        AgentPaused -.-> ResumeCommand[resume_research_agent]
        ResumeCommand -.->|Resumes active step| SearchStep
        AbortCommand[abort_research_agent] -.->|State: aborted| AgentAborted[Process Aborted & Celery Tasks Terminated]
    end
```

- **State Machine Transitions**: Sequentially advances through `initialized` $\rightarrow$ `search` $\rightarrow$ `download` $\rightarrow$ `ocr` $\rightarrow$ `screening` $\rightarrow$ `extraction` $\rightarrow$ `completed`.
- **Parallel Runs**: Executes multiple agents concurrently per workspace or across workspaces.
- **On-Demand OCR Skipping**: Automatically skips Step 3 OCR if `workspace.ocr_provider` is unconfigured (`None`), passing PDF binaries or abstracts directly to screening and parameter extraction.
- **Notification Engine**: Dispatches completion summary notifications to workspace member emails (`WorkspaceMember.user.email`), subscribers (`Subscriber.email`), and custom overrides.

### 2. Isolated Dual-Stage Screening Criteria
- **Abstract Screening Stage**: Evaluates paper title & abstract against `abstract_acceptance_criteria` and `abstract_rejection_criteria`.
- **Full-Text Screening Stage**: Performs deep evaluation of OCR Markdown text or Multimodal PDF binaries against `full_text_acceptance_criteria` and `full_text_rejection_criteria`.

### 3. Global DocumentRegistry & Multi-Tier Caching
- **Zero-Network PDF Fastpath**: Checks `DocumentRegistry` ($O(1)$ indexed by `sha256_hash`, `doi`, `arxiv_id`) before initiating HTTP requests, saving bandwidth and preventing rate-limits across runs and workspaces.
- **Zero-Compute OCR Fastpath**: Caches layout Markdown in `cache/documents/{sha256}/ocr_{provider}.md`, skipping expensive OCR parser execution for previously converted documents.
- **Strict Storage Isolation**: Workspace run deletions purge only their local workspace run folder (`workspaces/{ws_id}/runs/{run_id}/`), keeping canonical registry binaries and other workspaces' files 100% intact.

### 4. Dynamic Parameter Extraction
- **Schema-Validated Extraction**: Evaluates papers against `ExtractionDefinition` prompts and JSON schemas.
- **Evidence & Confidence Scores**: Stores results in `Extraction` objects containing exact evidence quotes, normalized values, confidence scores, and validation statuses (`pass`, `warn`, `fail`).

### 5. Dual Protocol Interface
- **FastMCP SSE Interface (Port 8001)**: Exposes workspace tools, scrapers, state machine controls, parameter extraction, and document registry stats to LLM clients (Claude, Gemini, Cursor, Antigravity) via `@mcp.tool()` and `@mcp.prompt()`.
- **Django REST API (Port 8000)**: Exposes `/api/workspaces/`, `/api/agents/`, `/api/extractions/`, and `/api/pipeline-runs/` endpoints for web frontends.

---

## 🗄️ 3. Database Architecture & Entity Relationships

The data layer is structured into 5 cohesive domains:
1. **Tenancy & Authentication**: `Workspace`, `WorkspaceMember`, `APIKey`, `UserActivityLog`
2. **Configuration & Scrapers**: `Scraper`, `ExtractionDefinition`, `Subscriber`
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
schwarz_research_intelligence/
├── backend/                     # Django API + Celery Async Task Workers + FastMCP
│   ├── Dockerfile               # Production container definition
│   ├── django_project/          # Settings & WSGI configuration
│   ├── api/                     # DRF REST API viewsets & serializers (/api/)
│   └── research_intelligence/   # Core intelligence platform
│       ├── mcp/                 # FastMCP SSE Server & Tool Registry
│       ├── tasks/               # 5-Step Pipeline & Orchestrator State Engine
│       ├── models.py            # Workspace, DocumentRegistry, Paper, Extraction models
│       └── tests/               # Automated unit & integration test suite (164+ tests)
├── frontend/                    # Next.js User Interface
├── docs/                        # Architecture documentation, diagrams & image generators
│   ├── generate_db_schema.py    # Automated DB schema diagram builder (Mermaid/PNG/SVG)
│   ├── diagrams/                # Raw Mermaid diagram definitions (.mmd)
│   └── images/                  # Compiled architecture & DB schema images (.png / .svg)
├── .github/                     # DevOps & CI/CD Pipelines
│   └── workflows/
│       └── ci.yml               # GitHub Actions workflow (SQLite tests + pip & Docker caching)
├── docker-compose.yml           # Unified local development & production stack
├── AGENTS.md                    # Guidelines for AI agent assistants (Gemini, Claude, Cursor)
└── README.md                    # System documentation (This file)
```

---

## 🛠️ 5. Technology Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Backend Framework** | Python 3.12+, Django 6.0, DRF | Core models, database management, and REST API. |
| **MCP SSE Server** | FastMCP | Model Context Protocol SSE server on port 8001. |
| **Task Queue** | Celery, Redis | Distributed async pipeline execution and background state engine polling. |
| **Database Layer** | PostgreSQL (Prod) / SQLite (Tests) | Persistent storage, audit logs, and in-memory test runner. |
| **Storage Layer** | Django `default_storage` | Local filesystem / AWS S3 / MinIO storage abstraction. |
| **LLM Engine** | Google GenAI / Gemini 3.7 Flash | Enterprise AI provider hosted on Schwarz Digits Cloud. |
| **OCR Providers** | PyPDF / Mistral OCR API | Document layout parsing. |
| **Diagram Engine** | Mermaid CLI / Python Generator | Automated DB schema and architecture diagram generation. |
| **CI/CD** | GitHub Actions | Automated build, test, and container layer caching. |

---

## ⚡ 5. Quick Start for Developers

### Run Locally with Docker Compose
```bash
# 1. Clone repository and set up environment variables
cp .env.example .env

# 2. Build and start containers
docker compose up --build

# 3. Access interfaces:
# - Django REST API: http://localhost:8000/api/
# - FastMCP SSE Endpoint: http://localhost:8001/mcp/tools/
# - Django Admin: http://localhost:8000/admin/
```

### Run Unit Tests Locally
Tests automatically run on an in-memory SQLite database:
```bash
.venv/bin/python backend/manage.py test research_intelligence.tests
```
