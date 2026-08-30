# 🧪 Schwarz Research Intelligence - End-to-End (E2E) Test Suite

State-of-the-art live API test suite and full pipeline simulator for **Schwarz Research Intelligence (SRI)** against **Production**, **Staging**, or **Local** environments.

---

## 🏛️ Architecture & Structure

```
tests_e2e/
├── config.py                 # Target environment configs (Prod, Staging, Local), quotas & credentials
├── client/                   # Modular API Client & Domain Services
│   ├── api_client.py         # HTTP Session with JWT Bearer auth, latency logging & retry handling
│   ├── auth_service.py       # Login / JWT acquisition (/api/auth/login/)
│   ├── workspace_service.py  # Workspaces, Scrapers, and Extraction Definitions CRUD
│   ├── agent_service.py      # Research Agent process lifecycle & polling engine
│   ├── pipeline_service.py   # Pipeline runs, papers, extractions, and reports querying
│   └── chat_service.py       # Paper Chat / Knowledge Explorer interrogation (/api/chat/)
├── scenarios/                # Modular Reusable User Journeys
│   └── full_slr_pipeline.py  # Complete 8-stage SLR review scenario
├── test_full_pipeline_e2e.py # Pytest integration test class
└── run_e2e.py                # Standalone CLI runner with rich formatting
```

---

## 🚀 Running E2E Tests

### 1. Run Live against Production (Default):
```bash
python -m tests_e2e.run_e2e --target=prod
```

### 2. Run Live against Staging:
```bash
python -m tests_e2e.run_e2e --target=staging
```

### 3. Run with Pytest:
```bash
pytest tests_e2e/test_full_pipeline_e2e.py -s -v
```

### 4. Custom Options:
```bash
python -m tests_e2e.run_e2e --target=prod --limit=10 --user=test_e2e --password='t4st_pa55w0rD!#' --cleanup
```

---

## 📋 What the E2E Pipeline Scenario Validates:

1. **Authentication**: Authenticates with `test_e2e` credentials via `POST /api/auth/login/` and captures JWT Bearer token.
2. **Workspace Creation**: Provisions a unique workspace (`test_e2e_<random>`) with:
   - Abstract screening inclusion & exclusion criteria
   - Multimodal Full-text screening criteria
   - Sandboxed Python `signal_score_code` mathematical formula
   - Gemini 3.7 Flash default model configuration
3. **Scraper Configuration**: Sets up arXiv query (e.g. quantum optimization) with target paper limit.
4. **Extraction Targets**: Creates schema-validated parameter extraction definitions (`Strategic Fit`, `TRL Assessment`, `Novelty Score`).
5. **Autonomous Agent Execution**: Launches the autonomous research agent process via `POST /api/agents/`.
6. **Real-Time Polling & State Audit**: Monitors state transitions across all SLR stages:
   - `Search & Deduplication`
   - `Abstract Screening`
   - `Parallel PDF Download` (downloaded strictly for passed papers)
   - `Layout OCR` (skipped for direct multimodal PDF)
   - `Full-Text Screening` (deep Gemini 3.7 multimodal evaluation)
   - `Parameter Extraction`
   - `Composite Signal Score`
   - `Executive Reporting`
7. **Scorecard & Results Verification**: Queries `/api/papers/`, `/api/extractions/`, `/api/reports/` and confirms signal scores.
8. **Interactive Paper Chat Interrogation**: Queries `/api/chat/?sync=true` against top-ranked paper and validates visual citations and fact-checking.
9. **Automated Cleanup**: Optionally deletes the test workspace when `--cleanup` is enabled.
