# User Personas & Access Control Specification

**Document Version**: 3.3  
**Associated Documents**:  
- 🗺️ **[user_journeys.md](user_journeys.md)** — Frontend User Journeys & Interaction Sequences  
- 📐 **[wireframes.md](wireframes.md)** — Screen Layout Wireframes & UI Component Topologies  
- 🧭 **[route_matrix.md](route_matrix.md)** — URL Route & Context Resolution Matrix  
**Scope**: Definitions, behavioral workflows, and permission boundaries for the core personas in the Schwarz Research Intelligence (SRI) platform.

---

## 1. Executive Summary: MVP Scope vs. Step 2 Roadmap

The frontend MVP is specifically designed around **two active user personas**:
1. **Manager (Research Lead)**: Full operational control over review cycles; can trigger runs (`[ ▶ Run Pipeline ]`), drills into **Historic Run Details (Components level)** (`/pipeline?run_id=...`), audits DAG execution, and consumes all research outputs.
2. **Researcher (Scientific Analyst)**: Consumes research results (`/briefing`, `/papers`, `/papers/[id]`, `/ask`) and has access to **Pipeline Management (`/pipeline`) in high-level read-only mode only** (inspects the list of historical runs, completion timestamps, paper counts, and durations). **The Researcher CANNOT trigger runs and CANNOT drill into component-level DAG execution details.**

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
|  Scope: RESULTS + HIGH-LEVEL RUNS LIST ONLY           |  Scope: CAN RUN PIPELINES + COMPONENT DAGS + RESULTS  |
|  • Reads Executive Synthesis & Briefings              |  • Triggers New Review Runs ([ ▶ Run Pipeline ])      |
|  • Filters Evaluated Papers Catalog                   |  • Monitors Live Run Execution (Mutex Protection)     |
|  • Deep-dives into Paper Details & Scorecards         |  • Drills into Historic Run Details (Components Level)|
|  • Interrogates Literature via Grounded AI Chat       |  • Audits Component DAGs & Spend (Search➔Report)     |
|  • ⚙️ Pipeline Management (/pipeline): LIST ONLY       |  • ⚙️ Pipeline Management (/pipeline): FULL CONTROL   |
|  • ❌ CANNOT drill into Component DAGs (/pipeline?run) |  • ✅ CAN drill into Component DAGs (/pipeline?run)   |
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
- **Primary Goal**: Quickly discover breakthrough papers in their domain, understand why a paper received a high Signal Score, verify technical claims against full-text evidence, interrogate methodologies using AI, and maintain awareness of when review runs took place.
- **Daily Pain Points Solved**:
  - Eliminates manual screening of hundreds of noisy arXiv / OpenAlex preprints.
  - Replaces manual PDF scanning with structured scoring ledgers, radar charts, and LLM rationales.
  - Enables instant natural-language Q&A directly cited from paper sections and figures.
  - Provides a clean overview of when historical SLR review cycles were executed.

### Access Boundary: Results + High-Level Runs List Only
The Researcher has full visibility into research outputs and a high-level summary of review runs, but **is strictly barred from technical component-level pipeline details and operational triggers**:

- **Accessible Views**:
  1. 📊 **Briefings Dashboard (`/briefing`)**: Reads executive summaries, breakthroughs, bottleneck analysis, and top-scoring paper cards.
  2. 📄 **Browse Papers Catalog (`/papers`)**: Filters papers by screening status, signal score slider, TRL window, and free-text search.
  3. 📑 **Paper Details & Scorecard (`/papers/[id]`)**: Deep-dives into AST formula ledgers, radar charts, LLM screening reasons, and canonical PDF files.
  4. 💬 **Ask Paper Console (`/ask`) & In-Page Assistant**: Converses with papers, verifies citation badges, and restores chat history threads.
  5. ⚙️ **Pipeline Management & Runs Audit (`/pipeline`) — READ-ONLY RUNS LIST ONLY**:
     - **Visible**: Inspects high-level list of historical runs, completion timestamps, paper counts, and duration metrics.
  6. 👤 **Personal Account Settings (`/settings`)**: Updates name, email, and password.

- **Strictly Restricted Views & Actions**:
  - ❌ **CANNOT Drill into Component Details**: **Historic Run Details at the component level (`/pipeline?run_id=...`) is strictly HIDDEN from Researchers**. Researchers cannot click run rows to open the component DAG breakdown, cannot view individual stage logs (Search, Download, OCR, Screening, Extraction, Signal, Report), and cannot view internal component execution latencies.
  - 🚫 **CANNOT Trigger Runs**: The **`[ ▶ Run Pipeline ]`** CTA button is **hidden or disabled** for Researchers (*"Manager role required to initiate pipeline runs"*).
  - 🚫 **CANNOT Abort or Modify Runs**: Only Managers have operational pipeline authority.

### Typical User Journey
1. **Morning Scan**: Opens `/briefing` for the latest successful run to review the executive synthesis and top 3 high-signal papers.
2. **Targeted Investigation**: Clicks a paper card to open `/papers/[id]?run_id=...` and inspects the Signal Score AST formula breakdown and TRL radar chart.
3. **In-Page Interrogation**: Uses the integrated `Ask this paper` right rail to ask: *"Explain the readout latency assumptions in Section 3.2"*.
4. **Run Awareness**: Navigates to `/pipeline` to check when the last review cycle completed, viewing its completion timestamp and paper count in the summary table.

---

## 3. Persona 2: Manager (Research Lead / Project Director)

### Profile & Motivation
- **Role Title**: Research Director, Lab Head, R&D Program Manager, Innovation Lead.
- **Primary Goal**: Track research velocity, evaluate domain maturity (TRL progression), initiate new automated review cycles, and perform in-depth component-level audits of Systematic Literature Review (SLR) execution quality and spend.
- **Daily Pain Points Solved**:
  - Provides instant high-level visibility into review funnel yields (screened vs. passed).
  - Enables on-demand triggering of review runs without risking duplicate concurrent jobs.
  - Provides detailed component-level execution transparency (Search ➔ Ingestion ➔ Screening ➔ Extraction ➔ Scoring ➔ Reporting) to diagnose stage bottlenecks and audit spend.

### Access Boundary: Can Run Pipelines + Component-Level DAG Audit + Results
The Manager has complete access to all research outputs, full operational control to trigger runs, and exclusive access to drill into component-level execution details.

- **Accessible Views**:
  1. **All Researcher Views**: Full access to `/briefing`, `/papers`, `/papers/[id]`, `/ask`, and high-level `/pipeline`.
  2. ⚙️ **Pipeline Management (`/pipeline`) — FULL OPERATIONAL CONTROL**:
     - **Trigger Pipeline Runs**: **Can start a fresh review cycle using the `[ ▶ Run Pipeline ]` button** (protected by a single active run concurrency mutex lock).
     - **Live Execution Monitoring**: Observes run status in real time while stages progress.
     - **Historic Runs Overview**: Reviews past runs table showing timestamps, durations, paper yields, and total USD costs.
     - **Exclusive Component DAG Audit (`/pipeline?run_id=...`)**: **Drills into Historic Run Details (Components level)** by clicking any run row. Audits individual stage outputs (Search ➔ Ingestion ➔ Screening ➔ Extraction ➔ Scoring ➔ Reporting), inspects stage timings, models, and component costs in read-only mode (`No Re-run`).
  3. 🔔 **Notification Preferences (`/settings`)**: Configures email digest alerts upon run completion.

### Typical User Journey
1. **Executive Review**: Reviews `/briefing` on Monday morning to evaluate the weekly review output.
2. **Funnel Audit**: Checks `/pipeline` to ensure Run #14 completed within budget ($1.15) and processed all fetched papers (142 fetched, 18 passed).
3. **Component Deep Dive**: Clicks Run #14 on `/pipeline` to open the **Historic Run Details (Components level)** drawer and verifies the screening and extraction stage latencies.
4. **Initiating Reviews**: If new papers were preprinted after a major conference, clicks `[ ▶ Run Pipeline ]` on `/pipeline` to trigger an on-demand review cycle.

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
| **Pipeline Runs Overview (High-level)** | `/pipeline` | ✅ **Visible (List Only)** | ✅ **Visible (Active)** | *(Step 2)* | **Researcher sees list of runs only.** |
| **Trigger Pipeline Run** | `/pipeline` CTA | 🚫 **No (Manager Only)** | ✅ **Can Run (`[ ▶ ]`)** | *(Step 2)* | Subject to single active run mutex lock. |
| **Historic Run Details (Components level)** | `/pipeline?run_id=...` | 🚫 **Hidden (Manager Only)** | ✅ **Visible & Active** | *(Step 2)* | **Researcher cannot enter into component details.** |
| **Audit Spend & Run Metrics** | `/pipeline` | ✅ **Visible (Table summary)**| ✅ **Visible (Component DAG)**| *(Step 2)* | Researcher sees summary table costs; Manager audits stage spend. |
| **Manage Profile & Password** | `/settings` | ✅ Visible | ✅ Visible | *(Step 2)* | Self-service credential update. |
| **Workspace Provisioning** | Dedicated Admin UI | 🚫 No | 🚫 No | ⏳ **Step 2** | Out of scope for MVP frontend. |
| **Scraper Query Builder** | Dedicated Admin UI | 🚫 No | 🚫 No | ⏳ **Step 2** | Out of scope for MVP frontend. |
| **Budget & Token Limits** | Dedicated Admin UI | 🚫 No | 🚫 No | ⏳ **Step 2** | Out of scope for MVP frontend. |

---

*End of User Personas & Access Control Specification.*
