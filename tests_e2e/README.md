# 🧪 Schwarz Research Intelligence - End-to-End (E2E) Test Suite

State-of-the-art live API test suite and full pipeline simulator for **Schwarz Research Intelligence (SRI)** against **Production**, **Staging**, or **Local** environments.

---

## 🏛️ Architecture & Scenarios

Every test scenario in `tests_e2e/scenarios/` is strictly **orthogonal, self-contained, and independently executable**:

```
tests_e2e/
├── config.py                 # Target environment configs (Prod, Staging, Local), quotas & credentials
├── run_e2e.sh                # Automated shell runner with auto-venv detection
├── run_e2e.py                # Standalone CLI runner with rich ASCII scorecard & argument parsing
├── test_full_pipeline_e2e.py # Pytest integration test suite
├── client/                   # Modular API Client & Domain Services
│   ├── api_client.py         # HTTP Session with JWT Bearer auth, latency logging & retry handling
│   ├── auth_service.py       # Login / JWT acquisition (/api/auth/login/)
│   ├── workspace_service.py  # Workspaces, Scrapers, and Extraction Definitions CRUD
│   ├── agent_service.py      # Research Agent process lifecycle & live heartbeat polling engine
│   ├── pipeline_service.py   # Pipeline runs, papers, extractions, and reports querying
│   └── chat_service.py       # Paper Chat / Knowledge Explorer interrogation (/api/chat/)
└── scenarios/                # 11 Orthogonal & Reusable User Journeys
    ├── full_slr_pipeline.py  # 1. Full 8-stage SLR review + Chat + Token Economics
    ├── chat_multiturn.py     # 2. Multi-turn conversational Q&A + Context Caching
    ├── agent_lifecycle.py    # 3. Agent Pause & Resume state machine recovery
    ├── pipeline_reprocessing.py # 4. Reprocessing existing papers (reprocess_existing=True)
    ├── cross_source_dedup.py # 5. Cross-source scraping & deduplication (arXiv + OpenAlex)
    ├── quota_guard.py        # 6. Monthly budget & token ceiling enforcement
    ├── email_digest.py       # 7. Transactional Mailgun executive digest dispatch
    ├── mcp_protocol.py       # 8. FastMCP SSE tools & AI agent discovery
    ├── rbac_data_isolation.py# 9. Multi-tenancy & unauthenticated RBAC security isolation
    ├── mid_step_rerun.py     # 10. Mid-step pipeline re-execution (rerun_from_node)
    ├── chat_hallucination_guard.py # 11. Hallucination guard & adversarial grounding probe
    └── concurrent_agents_load.py   # 12. Multi-agent concurrent load & row-locking test
```

---

## 🚀 Running E2E Scenarios via CLI

### 1. Run the Complete SLR Review & Chat (Default):
```bash
./tests_e2e/run_e2e.sh
```

### 2. Run Specific Orthogonal Scenarios:
```bash
# 1. Multi-Tenancy & RBAC Security Isolation:
./tests_e2e/run_e2e.sh --scenario=isolation

# 2. Mid-Step Pipeline Rerun (rerun_from_node):
./tests_e2e/run_e2e.sh --scenario=rerun

# 3. Chat Hallucination Guard & Grounding:
./tests_e2e/run_e2e.sh --scenario=guard

# 4. Concurrent Agents Load & Concurrency:
./tests_e2e/run_e2e.sh --scenario=concurrent

# 5. Agent Lifecycle (Pause & Resume):
./tests_e2e/run_e2e.sh --scenario=lifecycle

# 6. Pipeline Reprocessing (reprocess_existing=True):
./tests_e2e/run_e2e.sh --scenario=reprocess

# 7. Multi-Source Deduplication (arXiv + OpenAlex):
./tests_e2e/run_e2e.sh --scenario=dedup

# 8. Quota Guard & Budget Limits:
./tests_e2e/run_e2e.sh --scenario=quota

# 9. Transactional Email Digest:
./tests_e2e/run_e2e.sh --scenario=digest

# 10. FastMCP SSE Protocol & AI Tools:
./tests_e2e/run_e2e.sh --scenario=mcp

# Run ALL Scenarios Sequentially:
./tests_e2e/run_e2e.sh --scenario=all
```

### 3. Run on Different Environments:
```bash
./tests_e2e/run_e2e.sh staging          # Run on Staging
./tests_e2e/run_e2e.sh prod             # Run on Production
./tests_e2e/run_e2e.sh local            # Run on Local development server
```

### 4. Run with Pytest:
```bash
pytest tests_e2e/test_full_pipeline_e2e.py -s -v
```

---

## 🧹 Pre-Cleanup & Artifact Retention Policy

* **Pre-Cleanup (`cleanup_before = True`)**: Before creating a new workspace, the suite automatically searches for and deletes all previous test workspaces and extraction definitions matching `test_e2e_*` to keep your environment spotless.
* **Artifact Retention**: The created workspace and all its artifacts (downloaded PDFs, Markdown extractions, technology scorecards, and reports) are **retained after test completion** so you can inspect them in the Django Admin Portal (`/admin/`) and Storage Browser (`/admin/storage-browser/`).
* **Immediate Deletion**: To delete the workspace immediately upon completion, pass `--cleanup-after`.
