# 🚀 Schwarz Research Intelligence (SRI)
## User Guide & Operational Manual

Welcome to **Schwarz Research Intelligence (SRI)** — an enterprise-grade AI intelligence platform engineered for automated Systematic Literature Reviews (SLR), deep-tech scouting, competitive intelligence, and high-precision parameter extraction.

---

## 🌐 Platform Access & Core Links

| Service | Endpoint URL | Description |
| :--- | :--- | :--- |
| **SRI Main Web Application** | [https://sri-prod.apps.01.cf.eu01.onstackit.cloud/](https://sri-prod.apps.01.cf.eu01.onstackit.cloud/) | Primary dashboard, research matrix, interactive analytics, and paper exploration. |
| **SRI Administration Portal** | [https://sri-prod.apps.01.cf.eu01.onstackit.cloud/admin/](https://sri-prod.apps.01.cf.eu01.onstackit.cloud/admin/) | Full management panel for Workspaces, Scrapers, Extraction Targets, Users, and Storage. |
| **FastMCP SSE API (Claude Code)** | `https://sri-prod.apps.01.cf.eu01.onstackit.cloud/mcp/sse` | MCP endpoint for Claude Code, Cursor, and AI agents. |

---

## 🧭 End-to-End System Workflow

SRI automates the entire lifecycle from academic ingestion to custom scorecards and deep multi-turn paper interrogations:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 THE SCHWARZ RESEARCH INTELLIGENCE LIFECYCLE                            │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘

 1. WORKSPACE SETUP              2. EXTRACTION SCHEMAS             3. SCRAPER INGESTION
 ┌─────────────────────────┐     ┌─────────────────────────┐       ┌─────────────────────────┐
 │ • Define Scope & Goals  │ ──► │ • Define Structured KPIs│  ───► │ • Configure ArXiv /     │
 │ • Abstract Screening    │     │   (TRL, Fit, Novelty)   │       │   OpenAlex / Lens       │
 │ • Full-Text PDF Criteria│     │ • Schema Constraints    │       │ • Target Scraper Query  │
 └─────────────────────────┘     └─────────────────────────┘       └─────────────────────────┘
                                                                                │
                                                                                ▼
 6. CHAT & DEEP DIVE             5. SCORECARD & RESULTS            4. AUTONOMOUS SLR ENGINE
 ┌─────────────────────────┐     ┌─────────────────────────┐       ┌─────────────────────────┐
 │ • Interactive Paper Q&A │ ◄── │ • Parameter Scorecard   │  ◄─── │ • Search & Ingestion    │
 │ • Multimodal Evidence   │     │ • Python Signal Ranking │       │ • Abstract Screening    │
 │ • Formula Derivations   │     │ • Audit Quotes & Flags  │       │ • PDF Fetch & Cache     │
 │ • Visual Bounding Boxes │     │ • Executive PDF/Email   │       │ • OCR (Optional)        │
 └─────────────────────────┘     └─────────────────────────┘       │ • Full-Text Screening   │
                                                                   │ • Parameter Extraction  │
                                                                   │ • Composite Signal Score│
                                                                   │ • Executive Reporting   │
                                                                   └─────────────────────────┘
```

---

## 📚 User Documentation Modules

Choose your preferred way of working — whether you prefer the visual **Django Admin Portal** or conversational **Claude Code / MCP AI Agents**:

### 1. ⚙️ Setup & Configuration
* **[01. Pipeline Setup via Django Admin](./01_setup_pipeline_admin.md)**
  * Step-by-step visual configuration: Creating Workspaces, adding team members and email subscribers, configuring dual-stage screening criteria, setting up data scrapers, defining dynamic extraction schemas, and writing Python AST scoring formulas.
* **[02. Pipeline Setup via MCP & Claude Code](./02_setup_pipeline_mcp.md)**
  * Natural language and programmatic setup: Configuring your entire research review workspace in seconds through Claude Code or any MCP-compatible AI client.

### 2. ⚡ Launching & Monitoring Runs
* **[03. Running Research Pipelines via Django Admin](./03_running_pipeline_admin.md)**
  * Triggering Autonomous Research Agent processes, tuning paper ingestion quotas, monitoring Celery worker tasks in real-time, and inspecting live step-by-step progress.
* **[04. Running Research Pipelines via MCP & Claude Code](./04_running_pipeline_mcp.md)**
  * Executing reviews autonomously with `start_research_agent`, monitoring live ASCII progress bars via `check_run_status`, pausing, resuming, and aborting runs on demand.

### 3. 📊 Results & Technology Scorecards
* **[05. Viewing Results & Scorecards via Django Admin](./05_viewing_results_admin.md)**
  * Navigating screened papers, exploring LLM decision rationales, reviewing extracted KPI values with verbatim quotes and confidence scores, inspecting storage artifacts, and sending email digests.
* **[06. Viewing Results & Scorecards via MCP & Claude Code](./06_viewing_results_mcp.md)**
  * Querying full aggregated technology matrices with `get_paper_extractions_matrix`, listing top-scoring research papers, and generating executive tabular comparisons.

### 4. 💬 Interactive Paper Chat & Deep Dive
* **[07. Interrogating & Chatting with Papers via MCP](./07_chatting_with_papers_mcp.md)**
  * Interacting with ingested academic papers using `ask_paper` powered by Google Gemini 3.7 Flash: deep mathematical derivations, experimental methodology validation, visual figure verification, and hallucination-guarded answers.

---

## 🎯 Key Benefits for Enterprise Research Teams

1. **Massive Time Savings**: Accelerate Systematic Literature Reviews from months of manual reading to under 15 minutes of autonomous processing.
2. **Zero Hallucinations**: Every extracted data point is tied to direct verbatim evidence quotes and visual coordinates in the original PDF.
3. **Custom Strategic Scoring**: Write transparent Python mathematical formulas to rank papers according to your business's proprietary TRL, strategic fit, and novelty thresholds.
4. **Multimodal Native Processing**: Directly analyzes tables, figures, charts, and equations using cutting-edge Google Gemini 3.7 Flash multimodal models.
5. **Collaborative Multi-Tenancy**: Granular role-based access (Admin, Manager, Researcher) with automatic email notification digests for team stakeholders.
