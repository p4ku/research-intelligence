# ⚡ Guide 04: Running a Research Pipeline via MCP & Claude Code

With the **Schwarz Research Intelligence (SRI) Model Context Protocol (MCP)** server, you can trigger, monitor, pause, and supervise entire systematic reviews using Claude Code or any MCP-compatible AI agent.

---

## 🌐 Quick Access
* **Live MCP SSE Endpoint**: `https://research-scanner.schwarz/mcp/sse` *(or `https://sri-prod.apps.01.cf.eu01.onstackit.cloud/mcp/sse`)*
* **Web App URL**: [https://research-scanner.schwarz/](https://research-scanner.schwarz/) *(or [Cloud Foundry mirror](https://sri-prod.apps.01.cf.eu01.onstackit.cloud/))*
* **Admin Portal**: [https://research-scanner.schwarz/admin/](https://research-scanner.schwarz/admin/) *(or [Cloud Foundry mirror](https://sri-prod.apps.01.cf.eu01.onstackit.cloud/admin/))*

---

## 🔄 Autonomous Agent Orchestration Flow

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 AUTONOMOUS AGENT ORCHESTRATION VIA MCP                                 │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘

 USER
 💬 "Launch a systematic review on workspace 'Solid-State Battery Breakthroughs' and monitor progress."
   │
   ▼
 CLAUDE CODE / MCP CLIENT
   │
   ├──► 1. start_research_agent(workspace_id="...", limit=50, n_last_days=90)
   │       └── Returns: { "process_id": "9a1b2c3d-...", "status": "running" }
   │
   ├──► 2. check_run_status(process_id="9a1b2c3d-...")  [Non-blocking poll]
   │       └── Returns: Rich Markdown progress card with timeline and paper counts
   │
   └──► 3. get_paper_extractions_matrix(process_id="9a1b2c3d-...")  [Upon completion]
           └── Returns: Final technology scorecard & parameter matrix
```

---

## 💡 Quick Start: Conversational Execution

Simply ask Claude Code:

> **User Prompt**:
> *"Please start an autonomous research run for my workspace 'Solid-State Battery Breakthroughs 2026'. Limit ingestion to 50 papers from the last 90 days. Monitor the run and present the results when complete."*

Claude Code will launch the run and report real-time milestone updates.

---

## 🛠️ Detailed MCP Tool Reference

### 1. Launching an Autonomous Run (`start_research_agent`)
This is the **primary recommended entrypoint** for running systematic reviews.

#### Date Filtering Modes (Choose One):
You can filter harvested literature by publication date using **either** relative days **or** explicit calendar dates:

* **Mode 1: Relative Lookback Window (Default & Most Common)**
  * `n_last_days` *(optional, integer, default: 7)*: Number of past days to query (`now() - N days` to `now()`). Active when neither `start_date` nor `end_date` is specified.
  * *Example*: `"n_last_days": 14` (searches papers from the last 14 days).

* **Mode 2: Explicit Date Range**
  * `start_date` *(optional, ISO string, e.g. `'2026-08-01'`)*: Ingests papers published on or after this date.
  * `end_date` *(optional, ISO string, e.g. `'2026-08-31'`)*: Ingests papers published on or before this date. Defaults to `now()` if omitted when `start_date` is provided.
  * *Example*: `"start_date": "2026-08-01", "end_date": "2026-08-31"` (searches the exact August 2026 calendar interval).

#### General Parameters:
* `workspace_id` *(required)*: UUID of your target workspace.
* `limit` *(optional, default: null = all available)*: Maximum number of candidate papers to harvest across scrapers.
* `query_prefix` *(optional)*: Additional query keywords to prepend to all scraper queries.
* `skip_abstract_screening` *(optional, boolean)*: Set to `true` to skip abstract screening and route all papers directly to full text screening (default: inherits `workspace.skip_abstract_screening`).
* `reprocess_existing` *(optional, boolean)*: Reprocessing policy override. When omitted (`null`), inherits the workspace default policy (`workspace.reprocess_existing`). Set explicitly to `true` to re-screen and re-extract all existing workspace papers even if no new papers are found; set `false` to only process newly scraped papers.
* `notification_email` *(optional)*: Single-run email override to receive Mailgun completion report (default: sends to all active workspace Subscribers).

#### Example A: Relative Lookback Run (`start_research_agent` / `start_pipeline_run`):
```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "name": "Weekly Autonomous Ingestion",
  "n_last_days": 14,
  "limit": 50
}
```

#### Example B: Explicit Calendar Interval Run (`start_research_agent` / `start_pipeline_run`):
```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "name": "August 2026 Solid Electrolyte Review",
  "start_date": "2026-08-01",
  "end_date": "2026-08-31",
  "limit": 50,
  "reprocess_existing": false,
  "notification_email": "innovation-team@schwarz.com"
}
```

*Response*:
```json
{
  "status": "success",
  "process_id": "9a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
  "pipeline_run_id": "e4f5a6b7-c8d9-0e1f-2a3b-4c5d6e7f8a9b",
  "message": "Autonomous Research Agent Process started successfully."
}
```

#### Granular Search Trigger (`trigger_search_job`):
To execute Stage 1 Search as a standalone step:
```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "start_date": "2026-08-01",
  "end_date": "2026-08-15",
  "limit": 25
}
```
*(Or with relative days)*:
```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "n_last_days": 30,
  "limit": 25
}
```


---

### 2. Monitoring Real-Time Status (`check_run_status`)
`check_run_status` is the **primary non-blocking status inspector**. It returns live metrics, percentage completion, fine-grained TQDM progress bars, and a rendered ASCII progress card.

#### Tool Invocation Example:
```json
{
  "process_id": "9a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d"
}
```

#### Example Output Markdown Card:
```markdown
### 🚀 SLR Pipeline Status: `running` (65%)
**Process ID**: `9a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d`
**Elapsed Time**: `1m 42s` | **Cost**: `$0.14 USD` | **Tokens**: `142,500`

`[████████████████████░░░░░░░░░░] 65% Complete`

#### 📋 Execution Stages:
| Stage | Status | Details |
| :--- | :--- | :--- |
| **1. Search & Ingestion** | ✅ Done (4.2s) | 50 papers discovered (ArXiv: 25, OpenAlex: 25) |
| **2. Abstract Screening** | ✅ Done (18.1s)| 42 screened (18 passed, 24 rejected) |
| **3. Parallel PDF Download**| ✅ Done (12.4s)| 18 PDFs stored (0 paywalled, SHA-256 cached) |
| **4. Layout OCR Parsing** | ⏭️ Skipped | Direct multimodal Gemini 3.7 Flash active |
| **5. Full-Text Screening** | 🔄 In Progress | [██████░░░░░░] (12/18 items • 66.7%) |
| **6. Dynamic Extraction** | ⏳ Pending | Awaiting full-text screening completion |
| **7. Signal Score Ranking**| ⏳ Pending | Python scoring formula queued |
| **8. Executive Reporting** | ⏳ Pending | Report compilation & email digest queued |
```

---

### 3. State Management Tools

| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `pause_research_agent` | `process_id` | Pauses the active process without losing state or downloaded files. |
| `resume_research_agent` | `process_id` | Resumes a paused process from the exact active step. |
| `abort_research_agent` | `process_id` | Cancels the active process and terminates background Celery workers. |
| `list_research_agents` | `workspace_id` | Lists all historical and active processes with runtimes and completion states. |
| `get_research_agent_status` | `process_id` | Returns low-level diagnostic logs, task IDs, and storage footprints. |
| `get_pipeline_logs` | `process_id`, `limit` | Live terminal telemetry and worker logs inspector. |

---

## 🎯 Next Steps
When `check_run_status` reports `is_finished: true` and `status: completed`:
* View the aggregated parameter scorecard: **[Guide 06: Viewing Results via MCP](./06_viewing_results_mcp.md)**
* Chat with accepted papers: **[Guide 07: Chatting with Papers via MCP](./07_chatting_with_papers_mcp.md)**
