# User Personas & Access Control Specification

**Document Version**: 3.0  
**Associated Documents**:  
- 🗺️ **[user_journeys.md](user_journeys.md)** — Frontend User Journeys & Interaction Sequences  
- 📐 **[wireframes.md](wireframes.md)** — Screen Layout Wireframes & UI Component Topologies  
- 🧭 **[route_matrix.md](route_matrix.md)** — URL Route & Context Resolution Matrix  
**Scope**: Definitions, goals, behavioral workflows, and permission boundaries for the 3 core personas in the Schwarz Research Intelligence (SRI) platform.

---

## 1. Executive Summary: The 3 Personas

The Schwarz Research Intelligence platform serves three distinct user roles with strict boundary segregation:

```
+---------------------------------------------------------------------------------------------------------------+
|                                      SCHWARZ RESEARCH INTELLIGENCE ROLES                                      |
+------------------------------------+------------------------------------+-------------------------------------+
|         1. RESEARCHER              |            2. MANAGER              |          3. SYSTEM ADMIN            |
|       (Scientific Analyst)         |         (Research Lead)            |          (Infrastructure)           |
+------------------------------------+------------------------------------+-------------------------------------+
|  Scope: RESULTS ONLY               |  Scope: RESULTS + ORCHESTRATION    |  Scope: FULL SYSTEM & GOVERNANCE    |
|  • Reads Executive Briefings       |  • Consumes Executive Synthesis    |  • Multi-tenant Workspace Setup     |
|  • Filters Evaluated Papers        |  • Triggers Review Runs (Mutex)    |  • Upstream Scraper Configurations  |
|  • Deep-dives into Scorecards      |  • Audits Component DAGs & Spend   |  • User Provisioning & Roles        |
|  • Interrogates Papers via AI Chat |  • Oversees Digest Schedules       |  • Token Ceilings & USD Quotas      |
+------------------------------------+------------------------------------+-------------------------------------+
```

> [!IMPORTANT]
> **Core Principle: Researcher Sees Results Only**:  
> A Researcher is a pure consumer of scientific intelligence. They are strictly shielded from pipeline execution details, infrastructure settings, scraper queries, and budget caps. The **`⚙️ Pipeline Management`** view is hidden from Researchers; their navigation is dedicated purely to discovering, filtering, and interrogating evaluated literature.

---

## 2. Persona 1: Researcher (Scientific Analyst)

### Profile & Motivation
- **Role Title**: Senior Research Scientist, Domain Analyst, Postdoctoral Researcher.
- **Primary Goal**: Quickly discover breakthrough papers in their domain, understand why a paper received a high Signal Score, verify technical claims against full-text evidence, and interrogate specific methodologies using grounded AI.
- **Daily Pain Points Solved**:
  - Eliminates manual screening of hundreds of noisy arXiv / OpenAlex preprints.
  - Replaces manual PDF scanning with structured scoring ledgers, radar charts, and LLM rationales.
  - Enables instant natural-language Q&A directly cited from paper sections and figures.

### Access Boundary (Results Only)
- **Accessible Views**:
  1. 📊 **Briefings Dashboard (`/briefing`)**: Reads executive summaries, breakthroughs, bottleneck analysis, and top-scoring paper cards.
  2. 📄 **Browse Papers Catalog (`/papers`)**: Filters papers by screening status, signal score slider, TRL window, and free-text search.
  3. 📑 **Paper Details & Scorecard (`/papers/[id]`)**: Deep-dives into AST formula ledgers, radar charts, LLM screening reasons, and canonical PDF files.
  4. 💬 **Ask Paper Console (`/ask`) & In-Page Assistant**: Converses with papers, verifies citation badges, and restores chat history threads.
  5. 👤 **Personal Account Settings (`/settings`)**: Updates name, email, and password.
- **Restricted / Hidden Views**:
  - ❌ **Pipeline Management (`/pipeline`)**: Hidden. Researchers cannot trigger runs, abort jobs, view pipeline execution logs, or inspect system costs.
  - ❌ **Workspace Governance**: Cannot configure scrapers, modify screening prompts, alter AST formulas, or change budgets.

### Typical User Journey
1. **Morning Scan**: Opens `/briefing` for the latest successful run to review the executive synthesis and top 3 high-signal papers.
2. **Targeted Investigation**: Clicks a paper card to open `/papers/[id]?run_id=...` and inspects the Signal Score AST formula breakdown and TRL radar chart.
3. **In-Page Interrogation**: Uses the integrated `Ask this paper` right rail to ask: *"Explain the readout latency assumptions in Section 3.2"*.
4. **Broader Exploration**: Navigates to `/papers` and adjusts the Signal Score cutoff slider to $\ge 80$ to find additional candidates across the active domain.

---

## 3. Persona 2: Manager (Research Lead / Project Director)

### Profile & Motivation
- **Role Title**: Research Director, Lab Head, R&D Program Manager, Innovation Lead.
- **Primary Goal**: Track research velocity, evaluate domain maturity (TRL progression), audit Systematic Literature Review (SLR) execution quality and spend, and initiate new automated review cycles.
- **Daily Pain Points Solved**:
  - Provides instant high-level visibility into review funnel yields (screened vs. passed).
  - Eliminates accidental duplicate runs through strict workspace mutex locks.
  - Provides a single-pane-of-glass audit trail for review reproducibility without allowing destructive re-runs.

### Access Boundary (Results + Operational Pipeline)
- **Accessible Views**:
  1. **All Researcher Views**: Full access to `/briefing`, `/papers`, `/papers/[id]`, and `/ask`.
  2. ⚙️ **Pipeline Management & Audit (`/pipeline`)**:
     - Can trigger new review runs via the **`[ ▶ Run Pipeline ]`** button (subject to single-run concurrency mutex).
     - Monitors live run execution progress across pipeline stages.
     - Audits historical runs: UTC start times, durations, paper counts, and total USD spend.
     - Drills into **Historic Run Details (`/pipeline?run_id=...`)** to inspect component-level execution DAGs (Ingestion ➔ Screening ➔ Extraction ➔ Scoring ➔ Reporting).
  3. 🔔 **Notification Subscriptions**: Receives automated email summaries upon review completion.
- **Restricted Views**:
  - ❌ Cannot delete workspaces or modify system-wide LLM infrastructure keys (reserved for System Admin).

### Typical User Journey
1. **Executive Review**: Reviews `/briefing` on Monday morning to evaluate the weekly review output.
2. **Funnel Audit**: Checks `/pipeline` to ensure Run #14 completed within budget ($1.15) and processed all fetched papers (142 fetched, 18 passed).
3. **Initiating Reviews**: If new papers were preprinted after a major conference, clicks `[ ▶ Run Pipeline ]` on `/pipeline` to trigger an on-demand review cycle.
4. **Live Oversight**: Monitors the active run status pill while the mutex prevents concurrent team triggers.

---

## 4. Persona 3: System Administrator (Governance & Infrastructure)

### Profile & Motivation
- **Role Title**: Enterprise Platform Administrator, Head of DevOps / IT, Lead ML Engineer.
- **Primary Goal**: Ensure system availability, provision workspaces and user roles, configure upstream scrapers, monitor LLM token and dollar consumption against monthly limits, and enforce security policies.
- **Daily Pain Points Solved**:
  - Prevents runaway LLM API costs through hard monthly budget caps (`monthly_usd_limit`).
  - Controls access via fine-grained workspace membership roles.
  - Manages upstream data source credentials and rate limits.

### Access Boundary & Two-Tier Administrative Strategy (MVP Architecture)

To maintain an ultra-lean frontend MVP while providing full enterprise governance, the System Administrator operates across two interfaces:

```
+---------------------------------------------------------------------------------------------------------------+
|                                      SYSTEM ADMINISTRATOR WORKSPACES                                          |
+-------------------------------------------------------+-------------------------------------------------------+
|            TIER 1: FRONTEND RESEARCH PORTAL           |         TIER 2: BACKEND ADMINISTRATIVE CONSOLE        |
|                       (Next.js)                       |                    (Django Admin)                     |
+-------------------------------------------------------+-------------------------------------------------------+
|  • Workspace Context Switching (All Domains)          |  • Workspace Provisioning & Deletion                  |
|  • Verification of Briefings, Catalog & Scorecards    |  • Upstream Scraper Setup (arXiv, OpenAlex queries)   |
|  • Pipeline Execution Trigger & Mutex Verification    |  • Team Provisioning & Role Assignments               |
|  • Personal Account Profile & Security Settings       |  • Monthly USD & Token Quota Limits                   |
|                                                       |  • LLM Provider Keys & OCR Model Assignment           |
|                                                       |  • Persistent Usage Ledger & Storage Purging          |
+-------------------------------------------------------+-------------------------------------------------------+
```

1. **Frontend Research Portal (`/`)**:
   - Has global visibility across all workspaces in the dropdown.
   - Can verify end-to-end user experiences, review briefings, and launch pipeline runs.
2. **Administrative Console (`/admin/`)**:
   - Configures upstream scraper search queries, limits, and sort criteria (`/admin/.../scraper/`).
   - Assigns workspace memberships and roles (`admin`, `manager`, `researcher`) (`/admin/.../workspacemember/`).
   - Sets monthly budget ceilings (`monthly_usd_limit`, `monthly_token_limit`) to protect against overages.
   - Issues and revokes machine-to-machine API keys (`APIKey`) for MCP and REST integrations.

---

## 5. Screen & Action Permissions Matrix

The following matrix defines the exact visibility and action capabilities across all three personas:

| View / Action | URL Route | Researcher | Manager | System Admin | Notes |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Login & SSO** | `/` | ✅ | ✅ | ✅ | Standard authentication for all roles. |
| **View Briefings Dashboard** | `/briefing` | ✅ | ✅ | ✅ | High-level synthesis and top paper cards. |
| **Browse Papers Catalog** | `/papers` | ✅ | ✅ | ✅ | Multi-attribute search, TRL & score filters. |
| **Inspect Paper Details & Scorecard** | `/papers/[id]` | ✅ | ✅ | ✅ | AST formula ledger, radar chart, PDF link. |
| **Ask Paper Interrogation Console** | `/ask` | ✅ | ✅ | ✅ | Grounded multi-turn conversational chat. |
| **Use In-Page 'Ask this paper'** | `/papers/[id]` rail | ✅ | ✅ | ✅ | Contextual document assistant. |
| **Access Pipeline Management** | `/pipeline` | 🚫 **Hidden** | ✅ | ✅ | **Researcher sees results only.** |
| **Trigger Pipeline Run** | `/pipeline` CTA | 🚫 **No** | ✅ | ✅ | Subject to single-run concurrency mutex. |
| **Inspect Component Execution DAG** | `/pipeline?run_id=...` | 🚫 **Hidden** | ✅ | ✅ | View execution logs and timing (`No Re-run`). |
| **Audit Spend & Token Costs** | `/pipeline` | 🚫 **Hidden** | ✅ | ✅ | Track run costs ($) and durations. |
| **Manage Profile & Password** | `/settings` | ✅ | ✅ | ✅ | Self-service credential update. |
| **Configure Scrapers & Queries** | Admin Console | 🚫 **No** | 🚫 **No** | ✅ | Managed via Admin Console in MVP. |
| **Invite Users & Assign Roles** | Admin Console | 🚫 **No** | 🚫 **No** | ✅ | Provision `admin`, `manager`, `researcher`. |
| **Set USD Budget / Token Caps** | Admin Console | 🚫 **No** | 🚫 **No** | ✅ | Enforce workspace financial quotas. |

---

*End of User Personas & Access Control Specification.*
