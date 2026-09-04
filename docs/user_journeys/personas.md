# User Personas & Access Control Specification

**Document Version**: 3.2  
**Associated Documents**:  
- 🗺️ **[user_journeys.md](user_journeys.md)** — Frontend User Journeys & Interaction Sequences  
- 📐 **[wireframes.md](wireframes.md)** — Screen Layout Wireframes & UI Component Topologies  
- 🧭 **[route_matrix.md](route_matrix.md)** — URL Route & Context Resolution Matrix  
**Scope**: Definitions, behavioral workflows, and permission boundaries for the core personas in the Schwarz Research Intelligence (SRI) platform.

---

## 1. Executive Summary: MVP Scope vs. Step 2 Roadmap

The frontend MVP is specifically designed around **two active user personas**:
1. **Manager (Research Lead)**: Orchestrates research cycles, can run pipelines (`/pipeline`), audits run execution, and consumes all intelligence outputs.
2. **Researcher (Scientific Analyst)**: Consumes scientific intelligence (`/briefing`, `/papers`, `/papers/[id]`, `/ask`) and has **read-only audit access** to pipeline runs (`/pipeline`) to verify SLR methodology and data provenance, **without the ability to trigger or run pipelines**.

> [!IMPORTANT]
> **Admin Features are Step 2 (Out of Scope for MVP Frontend)**:  
> In the current MVP phase, **we do not have anything specific for Admin on the frontend**. System administration, multi-tenant workspace provisioning, scraper query configuration, and fine-grained quota governance are strictly **Step 2**. Any underlying maintenance in Step 1 is handled via standard backend interfaces without custom frontend screens.

```
+---------------------------------------------------------------------------------------------------------------+
|                                    MVP FRONTEND USER PERSONAS (STEP 1)                                        |
+-------------------------------------------------------+-------------------------------------------------------+
|                    1. RESEARCHER                      |                      2. MANAGER                       |
|                 (Scientific Analyst)                  |                    (Research Lead)                    |
+-------------------------------------------------------+-------------------------------------------------------+
|  Scope: RESULTS + READ-ONLY PIPELINE AUDIT            |  Scope: CAN RUN PIPELINES + RESULTS                   |
|  • Reads Executive Synthesis & Briefings              |  • Triggers New Review Runs ([ ▶ Run Pipeline ])      |
|  • Filters Evaluated Papers Catalog                   |  • Monitors Live Run Execution (Mutex Protection)     |
|  • Deep-dives into Paper Details & Scorecards         |  • Audits Historic Runs & Component Level DAGs        |
|  • Interrogates Literature via Grounded AI Chat       |  • Consumes All Briefings, Catalogs & Scorecards      |
|  • ⚙️ Pipeline Management (/pipeline): READ-ONLY AUDIT|  • ⚙️ Pipeline Management (/pipeline): FULL CONTROL   |
|  • 🚫 CANNOT trigger runs ([ ▶ Run Pipeline ] hidden) |  • ✅ CAN trigger runs ([ ▶ Run Pipeline ] active)    |
+-------------------------------------------------------+-------------------------------------------------------+
|                                  [ STEP 2 ROADMAP: SYSTEM ADMINISTRATOR ]                                     |
|  • Custom Admin UI, Workspace Provisioning, Scraper Builder & Quota Controls are deferred to Step 2.          |
+---------------------------------------------------------------------------------------------------------------+
```

---

## 2. Persona 1: Researcher (Scientific Analyst)

### Profile & Motivation
- **Role Title**: Senior Research Scientist, Domain Analyst, Postdoctoral Researcher, Technology Scout.
- **Primary Goal**: Quickly discover breakthrough papers in their domain, understand why a paper received a high Signal Score, verify technical claims against full-text evidence, interrogate methodologies using AI, and audit review run provenance.
- **Daily Pain Points Solved**:
  - Eliminates manual screening of hundreds of noisy arXiv / OpenAlex preprints.
  - Replaces manual PDF scanning with structured scoring ledgers, radar charts, and LLM rationales.
  - Enables instant natural-language Q&A directly cited from paper sections and figures.
  - Provides full transparency into pipeline execution DAGs and SLR data provenance without operational overhead.

### Access Boundary: Results + Read-Only Pipeline Audit
The Researcher has full visibility into research outputs and pipeline execution logs, but **cannot perform state-altering operational actions (cannot run pipelines)**:

- **Accessible Views**:
  1. 📊 **Briefings Dashboard (`/briefing`)**: Reads executive summaries, breakthroughs, bottleneck analysis, and top-scoring paper cards.
  2. 📄 **Browse Papers Catalog (`/papers`)**: Filters papers by screening status, signal score slider, TRL window, and free-text search.
  3. 📑 **Paper Details & Scorecard (`/papers/[id]`)**: Deep-dives into AST formula ledgers, radar charts, LLM screening reasons, and canonical PDF files.
  4. 💬 **Ask Paper Console (`/ask`) & In-Page Assistant**: Converses with papers, verifies citation badges, and restores chat history threads.
  5. ⚙️ **Pipeline Management & Runs Audit (`/pipeline`) — READ-ONLY MODE**:
     - **Visible**: Inspects list of historical runs, completion timestamps, paper counts, and duration metrics.
     - **Visible**: Drills into **Historic Run Details (`/pipeline?run_id=...`)** to audit individual component stages (Search ➔ Ingestion ➔ Screening ➔ Extraction ➔ Scoring ➔ Reporting) for complete scientific transparency.
  6. 👤 **Personal Account Settings (`/settings`)**: Updates name, email, and password.

- **Restricted Operational Actions**:
  - 🚫 **Cannot Trigger Runs**: The **`[ ▶ Run Pipeline ]`** CTA button is **hidden or disabled** for Researchers (with a tooltip or banner: *"Manager role required to initiate pipeline runs"*).
  - 🚫 **Cannot Abort Runs**: Only Managers can halt an in-progress run.
  - 🚫 **Cannot Modify Scrapers or Budgets**: Upstream queries and financial ceilings are managed in the backend (Admin Step 2).

### Typical User Journey
1. **Morning Scan**: Opens `/briefing` for the latest successful run to review the executive synthesis and top 3 high-signal papers.
2. **Targeted Investigation**: Clicks a paper card to open `/papers/[id]?run_id=...` and inspects the Signal Score AST formula breakdown and TRL radar chart.
3. **In-Page Interrogation**: Uses the integrated `Ask this paper` right rail to ask: *"Explain the readout latency assumptions in Section 3.2"*.
4. **Methodology Verification**: Clicks `/pipeline` to review how Run #14 was executed, inspecting which scrapers were run and verifying screening stage pass rates in the component DAG.

---

## 3. Persona 2: Manager (Research Lead / Project Director)

### Profile & Motivation
- **Role Title**: Research Director, Lab Head, R&D Program Manager, Innovation Lead.
- **Primary Goal**: Track research velocity, evaluate domain maturity (TRL progression), initiate new automated review cycles, and audit Systematic Literature Review (SLR) execution quality and spend.
- **Daily Pain Points Solved**:
  - Provides instant high-level visibility into review funnel yields (screened vs. passed).
  - Enables on-demand triggering of review runs without risking duplicate concurrent jobs.
  - Provides a single-pane-of-glass audit trail for review reproducibility without allowing destructive re-runs.

### Access Boundary: Can Run Pipelines + Consume Results
The Manager has complete access to all research outputs plus full operational control over the pipeline execution lifecycle in the frontend.

- **Accessible Views**:
  1. **All Researcher Views**: Full access to `/briefing`, `/papers`, `/papers/[id]`, `/ask`, and `/pipeline`.
  2. ⚙️ **Pipeline Management (`/pipeline`) — FULL OPERATIONAL CONTROL**:
     - **Trigger Pipeline Runs**: **Can start a fresh review cycle using the `[ ▶ Run Pipeline ]` button** (protected by a single active run concurrency mutex lock).
     - **Live Execution Monitoring**: Observes run status in real time while stages progress.
     - **Historic Runs Overview**: Reviews past runs table showing timestamps, durations, paper yields, and total USD costs.
     - **Component DAG Audit (`/pipeline?run_id=...`)**: Drills into **Historic Run Details (Components level)** to audit individual stage outputs (Search ➔ Ingestion ➔ Screening ➔ Extraction ➔ Scoring ➔ Reporting) in read-only mode (`No Re-run`).
  3. 🔔 **Notification Preferences (`/settings`)**: Configures email digest alerts upon run completion.

### Typical User Journey
1. **Executive Review**: Reviews `/briefing` on Monday morning to evaluate the weekly review output.
2. **Funnel Audit**: Checks `/pipeline` to ensure Run #14 completed within budget ($1.15) and processed all fetched papers (142 fetched, 18 passed).
3. **Initiating Reviews**: If new papers were preprinted after a major conference, clicks `[ ▶ Run Pipeline ]` on `/pipeline` to trigger an on-demand review cycle.
4. **Live Oversight**: Monitors the active run status pill while the mutex prevents concurrent team triggers.

---

## 4. Persona 3: System Administrator (Step 2 Roadmap / Out-of-Scope for MVP)

### MVP Scope Status
> [!NOTE]
> **No Specific Admin UI in Step 1**:  
> For the initial MVP, there are no dedicated frontend screens or user journeys for the System Administrator. All administrative features are explicitly planned for **Step 2**.

### Step 2 Scope (Future Iteration)
When implemented in Step 2, the System Administrator interface will encompass:
- **Workspace Provisioning & Multi-tenancy**: Creating research domains, assigning storage quotas, and managing workspace lifecycles.
- **Upstream Scraper Management**: Interactive query builders for arXiv, OpenAlex, Semantic Scholar, and PubMed with rate limits and cron schedules.
- **Team Role Governance**: Provisioning user accounts, assigning roles (`manager` vs. `researcher`), and revoking access.
- **Budget & Quota Controls**: Hard monthly USD ceilings (`monthly_usd_limit`) and LLM token caps per workspace.
- **Model & OCR Routing**: Assigning LLM models (e.g., Claude 3.5 Sonnet, Gemini 2.0 Flash) and PDF parser engines per workspace.

---

## 5. Screen & Action Permissions Matrix (MVP Step 1)

The following matrix defines the exact visibility and action capabilities across the active MVP personas:

| View / Action | URL Route | Researcher (Analyst) | Manager (Lead) | System Admin (Step 2) | Notes |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Login Screen** | `/` | ✅ Visible | ✅ Visible | *(Step 2)* | Standard authentication for all active roles. |
| **Briefings Dashboard** | `/briefing` | ✅ Visible | ✅ Visible | *(Step 2)* | High-level synthesis and top paper cards. |
| **Browse Papers Catalog** | `/papers` | ✅ Visible | ✅ Visible | *(Step 2)* | Multi-attribute search, TRL & score filters. |
| **Paper Details & Scorecard** | `/papers/[id]` | ✅ Visible | ✅ Visible | *(Step 2)* | AST formula ledger, radar chart, PDF link. |
| **Ask Paper Console** | `/ask` | ✅ Visible | ✅ Visible | *(Step 2)* | Grounded multi-turn conversational chat. |
| **In-Page 'Ask this paper'** | `/papers/[id]` rail | ✅ Visible | ✅ Visible | *(Step 2)* | Contextual document assistant. |
| **Pipeline Management View** | `/pipeline` | ✅ **Visible (Read-Only)** | ✅ **Visible (Active)** | *(Step 2)* | **Researcher can view pipeline history & audits.** |
| **Trigger Pipeline Run** | `/pipeline` CTA | 🚫 **No (Manager Only)** | ✅ **Can Run (`[ ▶ ]`)** | *(Step 2)* | Subject to single active run mutex lock. |
| **Inspect Component DAG** | `/pipeline?run_id=...` | ✅ **Visible (Read-Only)** | ✅ **Visible (Read-Only)**| *(Step 2)* | Historic component audit (`No Re-run`). |
| **Audit Spend & Costs** | `/pipeline` | ✅ **Visible (Read-Only)** | ✅ **Visible (Active)** | *(Step 2)* | Run-level USD and duration tracking. |
| **Manage Profile & Password** | `/settings` | ✅ Visible | ✅ Visible | *(Step 2)* | Self-service credential update. |
| **Workspace Provisioning** | Dedicated Admin UI | 🚫 No | 🚫 No | ⏳ **Step 2** | Out of scope for MVP frontend. |
| **Scraper Query Builder** | Dedicated Admin UI | 🚫 No | 🚫 No | ⏳ **Step 2** | Out of scope for MVP frontend. |
| **Budget & Token Limits** | Dedicated Admin UI | 🚫 No | 🚫 No | ⏳ **Step 2** | Out of scope for MVP frontend. |

---

*End of User Personas & Access Control Specification.*
