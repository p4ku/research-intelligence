# 🚀 Guide 03: Running a Research Pipeline via Django Admin

This guide explains how to trigger, monitor, and manage end-to-end autonomous research runs using the **Schwarz Research Intelligence (SRI) Admin Portal**.

---

## 🌐 Quick Access
* **Admin Portal URL**: [https://sri-prod.apps.01.cf.eu01.onstackit.cloud/admin/](https://sri-prod.apps.01.cf.eu01.onstackit.cloud/admin/)

---

## 🔄 Autonomous Execution Architecture

When you trigger a run, the SRI Autonomous State Engine coordinates a sequential 7-stage pipeline across Celery background workers:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 THE 7-STAGE SLR PIPELINE EXECUTION LIFECYCLE                           │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘

 ┌───────────────────────────────────┐
 │ 1. Search & Ingestion             │ ──► Multi-source queries (ArXiv/OpenAlex/Lens) & DOI deduplication
 └─────────────────┬─────────────────┘
                   ▼
 ┌───────────────────────────────────┐
 │ 2. Parallel PDF Download          │ ──► Fetches full-text PDFs to unified storage with SHA256 caching
 └─────────────────┬─────────────────┘
                   ▼
 ┌───────────────────────────────────┐
 │ 3. Layout OCR Conversion          │ ──► Markdown extraction (Auto-skipped if OCR=None for raw multimodal)
 └─────────────────┬─────────────────┘
                   ▼
 ┌───────────────────────────────────┐
 │ 4. Dual-Stage Screening           │ ──► Abstract fast screening (4A) + Multimodal full-text PDF review (4B)
 └─────────────────┬─────────────────┘
                   ▼
 ┌───────────────────────────────────┐
 │ 5. Parameter Extraction           │ ──► Schema-constrained Pydantic/JSON extraction with evidence quotes
 └─────────────────┬─────────────────┘
                   ▼
 ┌───────────────────────────────────┐
 │ 6. Composite Signal Score         │ ──► Evaluates custom Python AST formula to rank accepted papers
 └─────────────────┬─────────────────┘
                   ▼
 ┌───────────────────────────────────┐
 │ 7. Executive Reporting & Digest   │ ──► Generates executive narrative and dispatches Mailgun email digests
 └───────────────────────────────────┘
```

![Research Agent Processes List](./images/07_research_agents_list.png)
*Figure 1: Autonomous Research Agent Processes list showing execution states, paper counts, and duration.*

---

## ⚡ Step-by-Step: Launching an Autonomous Run

1. Log into the [Admin Portal](https://sri-prod.apps.01.cf.eu01.onstackit.cloud/admin/).
2. In the sidebar under **Research Intelligence**, click **Research Agent Processes** ➡️ **+ Add Research Agent Process** (or view an active process).
3. Configure the run parameters:
   * **Workspace**: Select your target workspace (e.g. `Quantum Computing in Logistics 2026`).
   * **Process Name**: `Q1-2026 Quantum Routing Review` *(Optional label for reporting)*.
   * **Paper Limit**: `50` *(Maximum candidate papers to harvest across all scrapers)*.
   * **Date Range Days**: `90` *(Ingest only papers published within the last 90 days; leave empty for all-time)*.
   * **Reprocess Existing Papers**: `Unchecked` *(Check this if you want to re-screen and re-extract parameters from previously fetched papers using updated criteria)*.
   * **Notification Email**: `lead-scout@schwarz.com` *(Optional override to receive instant notification upon completion)*.

4. Click **Save and start process**.

The state machine immediately transitions to `running` and schedules the initial search task.

![Research Agent Process Details & Execution Tree](./images/07b_research_agent_detail.png)
*Figure 2: Active Research Agent Process detail card displaying live status, component run tree, token usage, and cost.*

---

## 📊 Monitoring Live Execution in Real Time

You can monitor your research agent's progress directly from the Admin panel:

### 1. Research Agent Process Detail View
Navigate to your active process to inspect:
* **Current State**: `initialized` ➡️ `search` ➡️ `download` ➡️ `screening` ➡️ `extraction` ➡️ `signal_score` ➡️ `completed`.
* **Progress Bar & Timeline**: Dynamic percentage completion.
* **Cost & Token Tracker**: Real-time USD budget spend and token usage counters.

### 2. Pipeline Runs & Component Runs Tree (Step-by-Step Audit)

![Pipeline Runs List](./images/08_pipeline_runs_list.png)
*Figure 3: Pipeline Runs dashboard tracking lifecycle, trigger method, and paper statistics.*

![Pipeline Run Execution Details](./images/08b_pipeline_run_detail.png)
*Figure 4: Detailed Component Run execution hierarchy with timing and logs.*

| Component Step | Status | Key Metrics Displayed |
| :--- | :--- | :--- |
| **Step 1: Search & Ingestion** | `completed` | 50 papers discovered, 42 unique (8 duplicates pruned) |
| **Step 2: PDF Download** | `completed` | 40 PDFs successfully downloaded (2 open-access missing) |
| **Step 3: OCR Conversion** | `skipped` | OCR skipped (`ocr_provider=None`) for native multimodal ingest |
| **Step 4A: Abstract Screening** | `completed` | 40 screened: 18 passed criteria, 22 excluded |
| **Step 4B: Full-Text Screening** | `completed` | 18 evaluated: 9 accepted, 9 rejected with AI reasoning |
| **Step 5: Parameter Extraction** | `completed` | 18 extractions generated across 2 schemas with evidence quotes |
| **Step 6: Signal Score** | `completed` | 9 papers scored (Top Score: 9.4 / 10.0) |
| **Step 7: Executive Reporting** | `completed` | Briefing compiled and email digest dispatched |

### 3. Viewing Live Error Logs and Traces
If an individual step experiences a transient network or API failure:
1. Click on the specific **Component Run** item.
2. Inspect the **Logs** and **Error Traceback** text fields.
3. SRI features automatic retry policies for rate-limited upstream academic APIs.

---

## ⏸️ Managing Active Processes (Pause / Resume / Abort)

From the Research Agent Process page in Django Admin:
* **Pause Run**: Change `state` to `paused` and click **Save**. The state machine safely freezes execution after the currently running paper finishes.
* **Resume Run**: Change `state` to `running` and click **Save**. The engine automatically picks up from the last uncompleted step without re-doing completed work.
* **Abort Run**: Change `state` to `aborted`. Background Celery workers are signaled to terminate immediately.

---

## 🎯 Next Steps
Once your run is complete (`state == 'completed'`), inspect your results:
* Explore the full results matrix and paper scorecard: **[Guide 05: Viewing Results via Admin](./05_viewing_results_admin.md)**
* Deep-dive into specific papers with AI chat: **[Guide 07: Chatting with Papers via MCP](./07_chatting_with_papers_mcp.md)**
