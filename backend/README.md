# 🐍 Research Intelligence - Backend API & Workers

This directory houses the backend Django API server and the Celery async task workers. Both run out of the same codebase and use the same database connection pool, caching brokers, and storage clients.

---

## 🏛️ Architecture Overview

The backend uses a shared **Django** foundation for standard API serving, while executing long-running agent pipelines via **Celery** workers backed by **Redis** as a task queue and **PostgreSQL** as the persistent state database.

```
backend/
├── Dockerfile               # Build configuration for Django & Celery
├── requirements.txt         # Core python libraries
├── django_project/          # Django settings & config files
│   ├── __init__.py
│   ├── settings.py          # Unified settings (DB, Cache, Storage, Sentry)
│   ├── urls.py              # Root routing table
│   └── wsgi.py / asgi.py
├── api/                     # REST API / Web Layer (Django REST Framework)
│   ├── urls.py              # API endpoint routes
│   ├── serializers/         # DRF Serializers for models
    │   ├── auth.py
    │   ├── workspaces.py
    │   ├── papers.py
    │   └── reports.py
    └── views/               # Django views partitioned per-endpoint
        ├── __init__.py
        ├── auth.py          # Workspace login & API key auth
        ├── workspaces.py    # Project configurations & prompt settings
        ├── papers.py        # PDF explorer & parsed markdown retrieval
        ├── extractions.py   # Extracted claims & parameters listing
        ├── hitl.py          # Human-in-the-loop endpoints (Verify, Modify, Reject)
        ├── chat.py          # RAG interactive query sessions
        └── reports.py       # Narrative executive briefings compilation
└── research_intelligence/   # Core Research & Pipeline Domain Logic
    ├── models.py            # Workspace, PipelineRun, Paper database models
    ├── prompts.py           # AgentSLR-based ScreenPrompt generator utilities
    ├── storage.py           # S3/R2/MinIO Storage client abstraction
    ├── llm_providers/       # Pluggable LLM API drivers
    │   ├── __init__.py
    │   ├── base.py          # Abstract base LLM client wrapper
    │   ├── google.py        # Schwarz Digits Google Agent API driver
    │   └── openrouter.py    # OpenRouter API client driver for fallbacks
    ├── tasks/               # Celery task modules partitioned by pipeline step
    │   ├── __init__.py
    │   ├── orchestrator/    # FLOW CONTROLLER & PIPELINE ORCHESTRATION
    │   │   ├── pipeline.py  # Task: run_workspace_ingestion_pipeline(workspace_id) (chains Steps 1-8)
    │   │   └── strategy.py  # Task: execute_dynamic_research_strategy(workspace_id, strategy_dag)
    │   ├── 1_search/        # STEP 1: Search & Ingestion Queries (arXiv, OpenAlex, Lens)
    │   │   ├── arxiv.py     # Task: query_arxiv_api(workspace_id)
    │   │   ├── openalex.py  # Task: query_openalex_api(workspace_id)
    │   │   ├── lens.py      # Task: query_lens_patents(workspace_id)
    │   │   └── dedup.py     # Task: deduplicate_ingested_metadata()
    │   ├── 2_download/      # STEP 2: Document Fetch & Storage
    │   │   └── fetch.py     # Task: download_pdf_to_s3(paper_id)
    │   ├── 3_ocr/           # STEP 3: PDF to Layout-preserving Markdown
    │   │   └── docling.py   # Task: run_docling_ocr(paper_id)
    │   ├── 4_screening/     # STEP 4: Two-Stage Inclusion Classification
    │   │   ├── abstract.py  # Task: screen_abstract(paper_id, workspace_id)
    │   │   └── full_text.py # Task: screen_full_text(paper_id, workspace_id)
    │   ├── 5_extraction/    # STEP 5: Schema-constrained claims mining
    │   │   └── extract.py   # Task: extract_custom_variables(paper_id, workspace_id)
    │   ├── 6_metrics/       # STEP 6: Research Metrics & Importance Evaluation
    │   │   ├── trl.py       # Task: assess_technology_readiness(extraction_id)
    │   │   └── importance.py# Task: calculate_paper_importance(paper_id)
    │   ├── 7_deep_research/ # STEP 7: Multi-step Autonomous Discovery
    │   │   ├── hypothesis.py# Task: run_hypothesis_evaluation(workspace_id)
    │   │   └── web_search.py# Task: run_web_search_scraping(query_text)
    │   └── 8_reporting/     # STEP 8: Evidence-grounded briefing synthesis
    │       ├── insights.py  # Task: compile_workspace_insights(workspace_id)
    │       └── narrative.py # Task: generate_narrative_report_with_refinement(workspace_id)
    └── tests/               # Unit and integration test suites
        ├── __init__.py
        ├── test_models.py   # Workspace, PipelineRun and budget validation tests
        ├── views/           # Integration tests for API view endpoints
        │   ├── __init__.py
        │   ├── test_auth.py
        │   ├── test_workspaces.py
        │   ├── test_papers.py
        │   ├── test_extractions.py
        │   ├── test_hitl.py
        │   ├── test_chat.py
        │   └── test_reports.py
        └── tasks/           # Mock and logic tests for pipeline task steps
            ├── __init__.py
            ├── test_orchestrator.py # Celery chain orchestration and error tolerance testing
            ├── test_1_search.py     # arXiv API search mock tests
            ├── test_2_download.py   # PDF download and retry logic tests
            ├── test_3_ocr.py        # OCR parsing mock tests
            ├── test_4_screening.py  # ScreenPrompt inclusion/exclusion mock tests
            ├── test_5_extraction.py # JSON schema matching validation tests
            ├── test_6_metrics.py    # TRL scoring and PageRank ranker validation tests
            ├── test_7_deep_research.py # Multi-step autonomous lookup and web search tests
            └── test_8_reporting.py  # Digest generator and K-loop self-refinement tests
```

---

## 🗄️ Database Models (Workspace & Pipeline State)

We use a single database with a shared schema. Logical isolation is performed at the project (`Workspace`) level, and each scheduled batch execution is tracked as a `PipelineRun` to allow scientists to contrast weekly dataset updates chronologically.

For the complete, copy-pasteable Django models Python class definitions, please refer to the dedicated models document:
👉 **[Database Models Blueprint (research_intelligence/MODELS.md)](file:///Users/piotr/git/schwarz_research_inteligence/backend/research_intelligence/MODELS.md)**

## ⚙️ Celery Tasks (The Pipeline)

All pipeline stages are designed as independent, idempotent Celery tasks partitioned by directory step under `research_intelligence/tasks/`.

### 0. Orchestration & Control Tasks (`tasks/orchestrator/`)
- **`run_workspace_ingestion_pipeline(workspace_id)`**: The primary pipeline director. It retrieves the active `Workspace` parameters, and dynamically constructs a Celery execution DAG:
  - *Chains*: Step 1 (Search & Ingestion) -> Step 2 (Bulk download) -> Step 3 (OCR conversion) -> Step 4 (Screening).
  - *Chords*: Distributes full-text extraction tasks (Step 5) and TRL scoring tasks (Step 6) as parallel groupings across workers, collecting outputs for the final reporting engine.
- **`execute_dynamic_research_strategy(workspace_id, strategy_dag)`**: Decodes JSON execution blueprints produced by the natural language Strategy Compiler (e.g. from RAG or the dashboard) and chains/coordinates the specific task endpoints sequentially.

### 1. Ingestion Tasks (`tasks/1_search/` & `tasks/2_download/` & `tasks/3_ocr/`)
- **`1_search/`**:
  - `query_arxiv_api(workspace_id)`: Formulates search queries and pulls metadata from arXiv.
  - `query_openalex_api(workspace_id)`: Pulls metadata from OpenAlex.
  - `query_lens_patents(workspace_id)`: Pulls patent claims and metadata from Lens.org.
  - `deduplicate_ingested_metadata(workspace_id)`: Deduplicates articles across databases.
- **`2_download/fetch.py`**:
  - `download_pdf_to_s3(paper_id)`: Downloads paper PDFs and stores them in isolated tenant storage buckets.
- **`3_ocr/docling.py`**:
  - `run_docling_ocr(paper_id)`: Parses paper layout, equations, and tables into standard Markdown.

### 2. Screening & Extraction Tasks (`tasks/4_screening/` & `tasks/5_extraction/` & `tasks/6_metrics/`)
- **`4_screening/`**:
  - `screen_abstract(paper_id, workspace_id)`: Abstract screening using ScreenPrompt logic.
  - `screen_full_text(paper_id, workspace_id)`: Full-text screening for parameters matching workspace constraints.
- **`5_extraction/`**:
  - `extract_custom_variables(paper_id, workspace_id)`: Fetches the `extraction_schema` (JSON Schema) from the workspace, extracts claims/parameters from paper text dynamically using structured LLM response matching, and writes results to the `Extraction` ledger.
- **`6_metrics/`**:
  - `trl.py` -> `assess_technology_readiness(extraction_id)`: Evaluates research methods on a TRL 1-9 scale and grounds the score by linking to exact markdown snippets.
  - `importance.py` -> `calculate_paper_importance(paper_id)`: Ranks scientific documents using graph-based relational network metrics, citation indices, venue impact factor, and author h-index.

### 3. Autonomous Deep Research & Summarization Tasks (`tasks/7_deep_research/` & `tasks/8_reporting/`)
- **`7_deep_research/`**:
  - `run_hypothesis_evaluation(workspace_id)`: Hypothesizes gaps and triggers targeted search querying loops.
  - `run_web_search_scraping(query_text)`: Autonomous fetching of web resources to validate claims.
- **`8_reporting/`**:
  - `compile_workspace_insights(workspace_id)`: Aggregates parameter ranges and highlights conflicting results across papers.
  - `generate_narrative_report_with_refinement(workspace_id)`: Synthesizes reports, running the $K=5$ self-critique/refinement process.

---

## 🔒 LLM Cost Control Implementation

Inside `research_intelligence/llm_providers/google.py` (which wraps the Schwarz Digits Google Agent API calls), the cost control interceptor operates as follows:

1. **Quota Verification**: Before triggering any LLM API request, the client queries the `Workspace` table. If the workspace has exceeded its monthly token or USD limit, it throws a `QuotaExceededException` and halts the Celery pipeline.
2. **Rate Limiting**: Uses a Redis-based token-bucket algorithm to throttle concurrent execution. If rate limits (e.g. 60 requests/min) are near capacity, it sleeps/exponentially backs off before sending the request.
3. **Loop Breakers**: Every task running agentic loops (like self-refinement report generations) must track iteration depth. If `depth > max_limit`, it triggers a callback to Sentry and breaks the loop.
4. **Telemetry Logging**: Upon completion of the API call, a callback writes an entry to `AuditTrail` and updates the `Workspace` consumption metrics.

---

## 🚀 Advanced Agentic Implementations (Technical Reference)

To ensure this platform matches state-of-the-art architectures, the following technical implementations are specified for developers:

### 1. Durable Workflow Checkpoints
Every Celery task in `tasks/7_deep_research/` and `tasks/8_reporting/` must store step execution states in a JSON database field inside `AuditTrail`. 
- Before running a sub-agent loop (e.g., fetching a web source or criticking a paragraph), the worker checks if an audit log for that `task_id` and sub-step already has a completed state.
- If it exists, the worker reads the cached JSON payload and skips execution, resuming directly at the next incomplete step.

### 2. PostgreSQL Hybrid Search Schema
To implement the Hybrid Retrieval Engine, the database utilizes PostgreSQL full-text search integrated with `pgvector`.
- An index is created on the text field: `CREATE INDEX md_content_fts_idx ON api_paper USING gin(to_tsvector('english', abstract));`
- When a search is triggered, the engine runs two query paths:
  1. Lexical search: `ts_rank_cd(to_tsvector('english', abstract), query)`
  2. Vector search: `embedding <=> query_vector`
- The results are normalized and merged inside `api/views/chat.py` using **Reciprocal Rank Fusion (RRF)**:
  $$RRF\_Score(d) = \sum_{m \in M} \frac{1}{60 + r_m(d)}$$
  where $r_m(d)$ is the rank of document $d$ in retriever $m$.

### 3. Hierarchical Step Tracing
To build the collapsible "Agent Thought Logs" in the UI, `AuditTrail` rows support hierarchical relations.
- Every sub-task audit entry includes a `parent_trace_id` referencing the root research request.
- Sub-steps write logs containing the specific tool called (e.g., `web_search`), tool argument, prompt template, and output.
- The view `views/hitl.py` returns a structured JSON tree:
  ```json
  {
    "step_id": "uuid-1",
    "step_name": "Evaluating Hypothesis",
    "thought": "The paper suggests R0 is 2.5, but patent claims state 3.0...",
    "sub_steps": [
      {
        "step_name": "pgvector_query",
        "tool_input": "Zika transmission models",
        "tool_output": "Found 3 papers..."
      }
    ]
  }
  ```

### 4. Strategy Compiler (`prompts.py`)
For natural language programmable strategies, `prompts.py` exposes a compiler function `compile_strategy_to_dag(prose_strategy: str) -> dict`.
- It takes user instructions and uses the Google Agent API with a structured output schema to return a sequence of execution nodes:
  ```json
  {
    "steps": [
      {"action": "search", "params": {"query": "Ebola vaccine trials", "limit": 100}},
      {"action": "filter", "params": {"sample_size_min": 50}},
      {"action": "extract", "params": {"schema": "trial_metrics"}},
      {"action": "report", "params": {"output_format": "comparison_table"}}
    ]
  }
  ```
- The orchestrator in Celery parses this JSON to dynamically chain the respective task files.

### 5. LaTeX and BibTeX Compiler (`tasks/8_reporting/`)
- During the $K=5$ self-critique loop, the narrative task generates both a `.md` dashboard view and a `.tex` document.
- The task dynamically constructs a `.bib` file populated with the BibTeX entries of all papers marked as ground-truth evidence in `Extraction` records.
- PDF generation is handled asynchronously using containerized TeX compilers, with the compiled output saved directly to S3.


## 🧪 Running Tests

The backend includes a comprehensive unit and integration test suite located in the `research_intelligence/tests/` directory.

### Quick Start (Recommended)
We provide an automated test runner script that repairs/sets up the virtual environment, installs dependencies, and runs the tests:
```bash
./backend/run_tests.sh
```

### Manual Execution
If you prefer to run tests manually, activate your virtual environment and run the standard Django test runner from the `backend/` directory:
```bash
# 1. Activate your virtual environment
source venv/bin/activate

# 2. Run the test suite
python manage.py test
```

