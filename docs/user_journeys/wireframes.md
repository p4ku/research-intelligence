# Frontend Screen Layout Wireframes Specification

**Document Version**: 3.0  
**Associated Documents**:  
- 🗺️ **[user_journeys.md](user_journeys.md)** — Frontend User Journeys, State Transitions, and Interaction Sequences  
- 👥 **[personas.md](personas.md)** — User Personas, Daily Workflows & Permissions Matrix  
- 🧭 **[route_matrix.md](route_matrix.md)** — URL Route & Context Resolution Matrix  
**Scope**: High-fidelity ASCII layout wireframes and UI component topologies for all primary screens and embedded sub-functionalities.

---

## 1. Global Shell & Layout Conventions

Across all authenticated views, the application renders a persistent two-tier context shell:
1. **Top Context Navigation Bar (`Global Context Bar`)**:
   - Institutional SRI Branding & Logo
   - **Workspace Selector**: Scoped domain dropdown (e.g., `Quantum Computing ▾`).
   - **Run Selector**: Dropdown displaying finished pipeline runs for the active workspace; **automatically pre-selects the Last Successful Run** (`default to last successful run`).
   - User Profile & Settings Trigger (`[ Profile ▾ ]`).
2. **Main Navigation Rail / Sidebar (Persona-Specific Visibility in MVP)**:
   - **Manager Navigation (Can Run Pipelines + Results)**:
     - `1. 📊 Briefings (/briefing)` — Executive synthesis and top papers
     - `2. 📄 Browse Papers (/papers)` — Searchable literature catalog & filters
     - `3. 💬 Ask Paper (/ask)` — Grounded AI interrogation console
     - `4. ⚙️ Pipeline Management (/pipeline)` — **Active for Manager** (Trigger runs with `[ ▶ Run Pipeline ]`, audit DAGs)
     - `👤 Settings (/settings)` — Personal profile & preferences
   - **Researcher Navigation (Results + High-Level Runs List Only)**:
     - `1. 📊 Briefings (/briefing)` — Executive synthesis and top papers
     - `2. 📄 Browse Papers (/papers)` — Searchable literature catalog & filters
     - `3. 💬 Ask Paper (/ask)` — Grounded AI interrogation console
     - `4. ⚙️ Pipeline Management (/pipeline)` — **Visible in High-Level List Mode Only** (Inspects list of runs, timestamps, paper counts, and durations; **cannot enter component-level details or DAGs**; cannot trigger runs)
     - `👤 Settings (/settings)` — Personal profile & preferences
   - **System Administrator**:
     - *(⏳ **No specific screens or navigation at this stage**; full admin UI is deferred to a **Future Iteration**)*

```
+---------------------------------------------------------------------------------------------------------------+
|  GLOBAL TWO-TIER CONTEXT BAR                                                                                  |
|  [ SRI Logo ]   Workspace: [ Quantum Computing ▾ ]    Run: [ Run #14 (Latest Successful) ▾ ]  | [ Profile ▾ ] |
+---------------------------------------------------------------------------------------------------------------+
|  MANAGER SIDEBAR (Can Run Pipelines + Results)  |  RESEARCHER SIDEBAR (High-Level Runs List Only)             |
|  • 📊 Briefings                                 |  • 📊 Briefings                                             |
|  • 📄 Browse Papers                             |  • 📄 Browse Papers                                         |
|  • 💬 Ask Paper                                 |  • 💬 Ask Paper                                             |
|  • ⚙️ Pipeline Management [ ▶ Run Pipeline ]    |  • ⚙️ Pipeline Management (Runs List Only · No Details CTA)  |
|  • 👤 Settings                                  |  • 👤 Settings                                              |
|  ---------------------------------------------  |  ---------------------------------------------------------  |
|  ADMIN ROLE STATUS: No specific screens in MVP (Future Iteration)                                             |
+---------------------------------------------------------------------------------------------------------------+
```

---

## 2. Screen 1: Briefings Dashboard (`/briefing`)

### Layout Topology
- **Top Full-Width Search**: `SearchFrame` spanning both panes for quick filtering across all editions.
- **Left Column (2/3) — Reader Frame**:
  - Publication date, run context badge, permalink action.
  - Briefing title & funnel statistics (`X papers screened · Y passed · Z included`).
  - Generated markdown narrative (`AnswerMarkdown`): Executive summary, key technological breakthroughs, bottleneck analysis.
  - Ranked Top Scoring Paper Cards with signal score pill, bibliographic meta, and direct drill-downs to `Paper Details` or `Ask This Paper`.
- **Right Column (1/3 sticky) — Edition History Rail**:
  - Chronological edition selector displaying previous pipeline runs in this workspace.

```
+---------------------------------------------------------------------------------------------------------------+
|  [ SRI Logo ]   Workspace: [ Quantum Computing ▾ ]    Run: [ Run #14 (Latest Successful) ▾ ]  | [ Profile ▾ ] |
+---------------------------------------------------------------------------------------------------------------+
|  [ 🔍 Search briefing editions by keyword, date, or theme...                                (Esc to clear) ]  |
|                                                                                                               |
|  +-------------------------------------------------------------+  +----------------------------------------+  |
|  |  LEFT AREA (2/3) — Selected Briefing Reader Frame           |  |  RIGHT RAIL (1/3) — Edition History    |  |
|  |                                                             |  |                                        |  |
|  |  SEP 3, 2026 · RUN #14                     [ 🔗 Permalink ] |  |  PREVIOUS EDITIONS / RUNS              |  |
|  |  Executive Synthesis: Quantum Error Correction Breakthroughs|  |  ------------------------------------  |  |
|  |  142 papers screened · 18 passed full-text · 6 in briefing   |  |  ● Run #14 (Current) · Sep 3, 2026     |  |
|  |  ---------------------------------------------------------  |  |    18 passed · 6 in briefing           |  |
|  |  💡 Executive Summary & Strategic Highlights                |  |                                        |  |
|  |  Recent experimental demonstrations in transmon qubit       |  |  ○ Run #13 · Aug 27, 2026              |  |
|  |  architectures have significantly compressed readout latency|  |    14 passed · 4 in briefing           |  |
|  |  below 20ns using dedicated FPGA firmware pipelines...      |  |                                        |  |
|  |                                                             |  |  ○ Run #12 · Aug 20, 2026              |  |
|  |  🚀 Key Breakthroughs & Technological Frontiers             |  |    9 passed · 3 in briefing            |  |
|  |  • Real-Time Decoding: Sub-microsecond syndrome processing   |  |                                        |  |
|  |  • Multiplexed Readout: 16-qubit frequency division arrays   |  |  ○ Run #11 · Aug 13, 2026              |  |
|  |                                                             |  |    12 passed · 5 in briefing           |  |
|  |  ---------------------------------------------------------  |  |                                        |  |
|  |  🏆 TOP SCORING PAPERS IN THIS BRIEFING                     |  |  ------------------------------------  |  |
|  |  +-------------------------------------------------------+  |  |  [ 📂 View All Runs in Pipeline ➔ ]    |  |
|  |  | [91.4] Oraqle: An Empirical Analysis of Qubit Readout  |  |  +----------------------------------------+  |
|  |  | Authors: J. Smith, A. Doe · arXiv:2401.0987 · TRL: 4.0 |  |                                              |
|  |  | [ View Paper Details ➔ ]    [ 💬 Ask This Paper ]      |  |                                              |
|  |  +-------------------------------------------------------+  |                                              |
|  |  +-------------------------------------------------------+  |                                              |
|  |  | [88.0] Fault-Tolerant Surface Codes on Transmon Arrays |  |                                              |
|  |  | Authors: L. Chen et al. · DOI: 10.1038/... · TRL: 5.0  |  |                                              |
|  |  | [ View Paper Details ➔ ]    [ 💬 Ask This Paper ]      |  |                                              |
|  |  +-------------------------------------------------------+  |                                              |
|  +-------------------------------------------------------------+                                              |
+---------------------------------------------------------------------------------------------------------------+
```

> [!NOTE]
> **Role Visibility on Briefings**:
> - The link `[ 📂 View All Runs in Pipeline ➔ ]` at the bottom of the Edition History rail is visible to **both Managers and Researchers** (Managers have full execution controls; Researchers inspect historical runs in high-level list-only mode).
> - **System Admin**: No dedicated screen in MVP (deferred to a **Future Iteration**).

---

## 3. Screen 2: Browse Papers Catalog (`/papers`)

### Layout Topology
- **Full-Width Search Bar**: Fast fuzzy search filtering by title, authors, abstract text, arXiv ID, or DOI.
- **Left Column (Main List — 2fr)**:
  - Header with result count scoped to the active run (`Showing 42 papers in Run #14`) and `Reset filters` trigger.
  - Multi-card paper stack (`PaperCard`): title, author list, source badge (`arXiv`, `OpenAlex`), publication date, Signal Score badge, TRL pill, Screening pill, and abstract excerpt.
  - Bottom pagination (`PageNav`): `[ Previous ] Page 1 of 6 [ Next ]`.
- **Right Column (Aside — 1fr)**:
  - **Sort By**: Radio options (`Signal score`, `Most recent`, custom extracted dimension).
  - **Screening Status**: Options (`Passed`, `Borderline`, `Pending`, `Rejected`, `All`).
  - **Signal Strength Cutoff**: Dynamic score slider (`minScore` 0 to 100).
  - **TRL Window**: Dual min/max TRL selectors (`1–3 Research`, `4–6 Development`, `7–9 Deployment`).
  - **Ingestion Window**: Date threshold radio group (`Last 24 hours`, `Last 7 days`, `All time`).

```
+---------------------------------------------------------------------------------------------------------------+
|  [ SRI Logo ]   Workspace: [ Quantum Computing ▾ ]    Run: [ Run #14 (Latest Successful) ▾ ]  | [ Profile ▾ ] |
+---------------------------------------------------------------------------------------------------------------+
|  [ 🔍 Search papers by title, author, abstract, arXiv ID, or DOI...                         (Esc to clear) ]  |
|                                                                                                               |
|  +-------------------------------------------------------------+  +----------------------------------------+  |
|  |  LEFT COLUMN (Main) — Filtered Corpus (42 papers in Run #14)|  |  RIGHT FILTER RAIL (1fr)               |  |
|  |  Showing 1–8 of 42 papers               [ Reset filters ]   |  |                                        |  |
|  |                                                             |  |  SORT BY                               |  |
|  |  +-------------------------------------------------------+  |  |  (•) Signal score                      |  |
|  |  | 📄 Oraqle: An Empirical Analysis of Qubit Readout...  |  |  |  ( ) Most recent                       |  |
|  |  | Authors: J. Smith, A. Doe · 2026-08-28 · arXiv:2401.0987|  |  |  ( ) TRL level                          |  |
|  |  | [ Signal: 91.4 ] [ TRL: 4 ] [ Passed ] [ arXiv ]        |  |  ------------------------------------  |  |
|  |  | Snippet: "We demonstrate a 15ns readout latency on... |  |  |  SCREENING STATUS                      |  |
|  |  | [ View Details & Scorecard ➔ ]    [ 💬 Ask Paper ]    |  |  |  (•) Passed (18)                       |  |
|  |  +-------------------------------------------------------+  |  |  ( ) Borderline (6)                    |  |
|  |                                                             |  |  ( ) Rejected (118)                    |  |
|  |  +-------------------------------------------------------+  |  |  ( ) All statuses                      |  |
|  |  | 📄 Real-Time Neural Syndrome Decoding on FPGA         |  |  ------------------------------------  |  |
|  |  | Authors: M. Davis et al. · 2026-08-15 · DOI: 10.1103/...|  |  |  SIGNAL STRENGTH CUTOFF               |  |
|  |  | [ Signal: 87.2 ] [ TRL: 5 ] [ Passed ] [ DOI ]          |  |  |  Minimum score: ≥ 75                  |  |
|  |  | Snippet: "Syndrome processing latency is reduced to... |  |  |  [==========|---------] (0 to 100)     |  |
|  |  | [ View Details & Scorecard ➔ ]    [ 💬 Ask Paper ]    |  |  ------------------------------------  |  |
|  |  +-------------------------------------------------------+  |  |  TRL WINDOW                            |  |
|  |                                                             |  |  Min: [ TRL 4 ▾ ]  to  Max: [ TRL 9 ▾ ] |  |
|  |  ---------------------------------------------------------  |  |  ------------------------------------  |  |
|  |  [ Previous ]         Page 1 of 6            [ Next ]       |  |  INGESTION WINDOW                      |  |
|  +-------------------------------------------------------------+  |  (•) All time      ( ) Last 7 days     |  |
|                                                                   +----------------------------------------+  |
+---------------------------------------------------------------------------------------------------------------+
```

---

## 4. Screen 3: Paper Details & Integrated Interrogation (`/papers/[id]?run_id=<id>`)

### Layout Topology
- **Breadcrumb Navigation**: `← Back to Briefings / Papers`.
- **Left Area (2fr) — Paper Run Results & Scoring Details**:
  - **Header**: Paper title, author list, external repository links, canonical PDF viewer link (`[ View PDF ]`), Run scorecard badge (`Evaluated in Run #14 · Signal Score: 91.4/100`).
  - **Signal Score Formula Ledger (`SignalLedger`)**: Python AST formula snippet with real bound variable values for this run.
  - **Dimensions & TRL Evaluation**: Extracted parameters with confidence ratings, LLM quotes, and technological radar chart.
  - **Screening Justifications**: Dual-stage LLM audit reasoning (*Abstract Screening Passed* & *Full-Text Screening Passed*).
  - **Abstract & Extracted Content**: Structured document text.
- **Right Rail (1fr) — Integrated `Ask this paper` Sub-Functionality**:
  - Native contextual assistant scoped directly to this document.
  - Streaming conversational interface with inline evidence citation badges (`[Page 4, Fig 2]`).
  - Docked prompt composer enabling interrogation without leaving the scorecard.

```
+---------------------------------------------------------------------------------------------------------------+
|  [ SRI Logo ]   Workspace: [ Quantum Computing ▾ ]    Run: [ Run #14 (Latest Successful) ▾ ]  | [ Profile ▾ ] |
+---------------------------------------------------------------------------------------------------------------+
|  ← Back to Briefings / Papers                                                                                 |
|                                                                                                               |
|  +-------------------------------------------------------------+  +----------------------------------------+  |
|  |  LEFT AREA (2fr) — Paper Run Results & Scoring Details      |  |  RIGHT RAIL (1fr) — Ask this paper     |  |
|  |                                                             |  |                                        |  |
|  |  📄 Oraqle: An Empirical Analysis of Qubit Readout...       |  |  💬 Ask this paper (Grounded Chat)     |  |
|  |  Authors: J. Smith, A. Doe · arXiv:2401.0987 · [ View PDF ] |  |  ------------------------------------  |  |
|  |  Badge: Evaluated in Run #14 · Signal Score: 91.4/100       |  |  "Explain the readout fidelity in      |  |
|  |  ---------------------------------------------------------  |  |   theorem 2"                           |  |
|  |  📊 Signal Score Formula Ledger (AST Variables & Snippet)   |  |                                        |  |
|  |  • Gate TRL: 4.0 | Bonus TRL: 1.0 | Novelty: 0.85           |  |  🤖 Answer: According to Section 3...  |  |
|  |  ---------------------------------------------------------  |  |  Citations: [Page 4, Fig 2] [Sec 3.1]  |  |
|  |  🎯 Dimensions & TRL (Radar Chart & Parameter Extractions)  |  |                                        |  |
|  |  ---------------------------------------------------------  |  |  ------------------------------------  |  |
|  |  🛡️ Screening Justifications                                |  |  [ Type prompt...                ]  |  |
|  |  • Abstract Screening: PASSED (LLM justification quote)     |  |                                        |  |
|  |  • Full-Text Screening: PASSED (LLM justification quote)    |  +----------------------------------------+  |
|  |  ---------------------------------------------------------  |                                              |
|  |  📑 Abstract & Extracted Markdown Layout                     |                                              |
|  +-------------------------------------------------------------+                                              |
+---------------------------------------------------------------------------------------------------------------+
```

---

## 5. Screen 4: Ask Paper Console (`/ask`)

### Layout Topology
- **Left Column (3fr) — Main Interrogation Console**:
  - **Header Eyebrow**: Monospace label (`ASK PAPER CONSOLE`).
  - **Paper Target Chip**: Active paper selector pill with dropdown trigger (`[ 📄 Oraqle: Qubit Readout... (Run #14) ▾ ]`) and clear target action (`[✖]`).
  - **Transcript Body (`useTranscriptScroll`)**:
    - User message bubble with timestamp.
    - Assistant grounded response bubble with citations (`LiveAnswer` / `SettledAnswer`).
    - Interactive Evidence citation badges (`[Page 4, Theorem 2]`).
    - Suggested follow-up prompt chips (`FollowUps`).
  - **Docked Composer (`DOCK_WRAP`)**:
    - Auto-growing textarea (`FIELD_CLASS`).
    - Context grounding badge (`Grounded in full-text & Run #14 scorecard`).
    - Streaming control button (`[ ⏹ Stop / ✈ Send ]`).
- **Right Column (1fr / min 17rem) — Chat History Rail**:
  - Header: Monospace title `CHAT HISTORY (RIGHT)` with thread count.
  - Chronological list of saved sessions with paper title, turn count, and timestamp.
  - Click-to-restore action; delete confirmation dialog (`AlertDialog`).
  - `[ + Start New Conversation Thread ]` trigger.

```
+---------------------------------------------------------------------------------------------------------------+
|  [ SRI Logo ]   Workspace: [ Quantum Computing ▾ ]    Run: [ Run #14 (Latest Successful) ▾ ]  | [ Profile ▾ ] |
+---------------------------------------------------------------------------------------------------------------+
|  +-------------------------------------------------------------+  +----------------------------------------+  |
|  |  MAIN CHAT CONSOLE (3fr)                                    |  |  RIGHT RAIL (1fr) — Chat History       |  |
|  |  Eyebrow: ASK PAPER CONSOLE                                 |  |                                        |  |
|  |  Target: [ 📄 Oraqle: Qubit Readout... (Run #14) ▾ ] [✖]    |  |  CHAT HISTORY (RIGHT) · 4 threads      |  |
|  |  ---------------------------------------------------------  |  |  ------------------------------------  |  |
|  |                                                             |  |  ● Qubit Readout & FPGA Latency        |  |
|  |  👤 Researcher (14:32):                                     |  |    Active thread · 4 turns · 10m ago   |  |
|  |  "Explain the readout fidelity threshold in theorem 2 and   |  |                                        |  |
|  |   compare it with typical hardware limits."                 |  |  ○ Surface Code Syndrome Decoding      |  |
|  |                                                             |  |    Yesterday · 6 turns                 |  |
|  |  🤖 Assistant (14:32):                                      |  |                                        |  |
|  |  According to Section 3.2 (page 4), Theorem 2 bounds the    |  |  ○ Transmon Multiplexing Limits        |  |
|  |  readout fidelity above 99.4% under the assumption that     |  |    Aug 28 · 2 turns                    |  |
|  |  discriminator integration time is tau <= 25ns.             |  |                                        |  |
|  |                                                             |  |  ○ Cat-State Stabilizer Comparison     |  |
|  |  Evidence Citations:                                        |  |    Aug 20 · 5 turns                    |  |
|  |  [ Page 4, Theorem 2 ]  [ Figure 3: Latency vs SNR ]        |  |                                        |  |
|  |                                                             |  |  ------------------------------------  |  |
|  |  Suggested Follow-ups:                                      |  |  [ + Start New Conversation Thread ]   |  |
|  |  [ "What FPGA hardware clock was used?" ]                   |  +----------------------------------------+  |
|  |  [ "How does this compare to Run #13 findings?" ]           |                                              |
|  |  ---------------------------------------------------------  |                                              |
|  |  DOCK COMPOSER:                                             |                                              |
|  |  [ Ask a question about this paper...                      ] |                                              |
|  |  Scope: Grounded in full-text & Run #14 scorecard | [ Send ➔]|                                              |
|  +-------------------------------------------------------------+                                              |
+---------------------------------------------------------------------------------------------------------------+
```

---

## 6. Screen 5: Pipeline Management & Execution Audit (`/pipeline` or `/studio/runs`)

> [!IMPORTANT]
> **Role-Based Permissions on Pipeline Management**:
> - **Manager (`Manager can run pipelines & inspect DAGs`)**: Fully active. Can trigger new review runs via **`[ ▶ Run Pipeline ]`** (with single-active-run concurrency mutex lock), monitor live execution, and click any run row (`[ View Component Audit ➔ ]`) to open the **Historic Run Details (Components level)** drawer to audit the DAG.
> - **Researcher (`Researcher sees high-level runs list ONLY`)**: Can view the list of historical runs, completion timestamps, paper counts, and durations in the summary table. **Researchers CANNOT enter into component details** (the `[ View Component Audit ➔ ]` action and component-level DAG drawer are **strictly hidden and inaccessible** for Researchers). The **`[ ▶ Run Pipeline ]`** CTA is also hidden or disabled.
> - **System Admin**: **No specific screens or features in this MVP** (governance portal and custom admin tools are deferred to a **Future Iteration**).

### Layout Topology
- **Top Context Bar**: Run selector is dimmed/inactive because the Pipeline view manages and displays *all* historical runs.
- **Page Header & Action**: View title, description, and primary CTA:
  - **For Manager**: Active **`[ ▶ Run Pipeline ]`** button (disabled with mutex tooltip if a run is already active).
  - **For Researcher**: Read-only overview mode — CTA button is hidden or renders as disabled badge `[ Manager Role Required to Trigger ]`.
- **StatBand**: Aggregate metrics (`Total Runs`, `Papers Fetched`, `Passed Screening`, `Total Spend USD`).
- **RunTabs**: Filter strip (`All`, `Completed`, `Running`, `Failed`).
- **RunsTable**: High-density table displaying UTC start time, Outcome pill, Last stage reached, Fetched/Passed counts, Duration, Cost, and audit drill-down action (`[ View Component Audit ➔ ]` is Manager only).
- **Component Execution Timeline Drawer / Sheet (`StepTimeline`) — MANAGER ONLY**:
  - Detailed component-level breakdown of the selected historical run.
  - Shows each stage status, timing, LLM model used, and monetary spend.
  - **Access Restriction**: **Visible only to Managers; strictly hidden from Researchers**.
  - **Strict Business Rule**: Permanent `[ No Re-Run Permitted ]` audit policy.

```
+---------------------------------------------------------------------------------------------------------------+
|  [ SRI Logo ]   Workspace: [ Quantum Computing ▾ ]    Run: [ All Runs Overview (Managed Here) ] | [ Profile ▾ ] |
+---------------------------------------------------------------------------------------------------------------+
|  Pipeline Management & Runs Audit                                       [ ▶ Run Pipeline ] (Manager Only)     |
|  Immutable execution audit trail, run history, and spend for Quantum Computing.                               |
|                                                                                                               |
|  +---------------------------------------------------------------------------------------------------------+  |
|  |  Runs: 14   |   Papers Fetched: 1,420   |   Passed Screening: 184 (13%)   |   Total Spend: $14.28       |  |
|  +---------------------------------------------------------------------------------------------------------+  |
|                                                                                                               |
|  Filter Status: [ All (14) ]  [ Completed (12) ]  [ Running (0) ]  [ Failed (2) ]                             |
|                                                                                                               |
|  +---------------------------------------------------------------------------------------------------------+  |
|  | Started (UTC)   | Outcome  | Last Stage  | Fetched | Passed | Duration | Cost  | Actions                    |  |
|  | ----------------|----------|-------------|---------|--------|----------|-------|--------------------------- |  |
|  | 03 Sep 14:20    | SUCCESS  | Reporting   |     142 |     18 | 4m 12s   | $1.15 | [ View Component Audit ]*  |  |
|  | 27 Aug 09:15    | SUCCESS  | Reporting   |     138 |     14 | 3m 50s   | $1.02 | [ View Component Audit ]*  |  |
|  | 20 Aug 11:00    | FAILED   | Extraction  |      90 |      0 | 1m 20s   | $0.35 | [ View Error Logs ]*       |  |
|  | 13 Aug 16:45    | SUCCESS  | Reporting   |     155 |     19 | 4m 30s   | $1.20 | [ View Component Audit ]*  |  |
|  +---------------------------------------------------------------------------------------------------------+  |
|  * Note on Actions: [ View Component Audit ] is visible ONLY to Managers. For Researchers, rows are static.   |
|                                                                                                               |
|  +---------------------------------------------------------------------------------------------------------+  |
|  |  DRAWER: HISTORIC RUN DETAILS (COMPONENTS LEVEL) — VISIBLE TO MANAGER ONLY (HIDDEN FOR RESEARCHER)      |  |
|  |  -----------------------------------------------------------------------------------------------------  |  |
|  |  ● 1. Ingestion (arXiv / OpenAlex)     [ SUCCESS ] · 142 papers fetched          (22s | $0.00)          |  |
|  |  ● 2. Screening (Abstract & Full-Text) [ SUCCESS ] · 18 passed / 124 rejected    (1m 45s | $0.48)       |  |
|  |  ● 3. Extraction (TRL & AST Dimensions)[ SUCCESS ] · 18 papers extracted        (1m 15s | $0.52)       |  |
|  |  ● 4. Scoring (Signal Score Formulas)  [ SUCCESS ] · Ledgers computed            (10s | $0.00)          |  |
|  |  ● 5. Reporting (Executive Briefing)   [ SUCCESS ] · Briefing generated          (40s | $0.15)          |  |
|  +---------------------------------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------------------------------+
+---------------------------------------------------------------------------------------------------------------+
```

---

## 7. Screen 6: Account & Workspace Settings (`/settings`)

### Layout Topology
- **Max-W-3XL Centered Stack**: Structured clean cards for profile, authentication, workspace bindings, and notifications.
- **Card 1 — Personal Profile (`ProfileForm`)**: First name, last name, email address, role badge (`Manager`, `Researcher`).
- **Card 2 — Security & Password (`PasswordForm`)**: Current password verification, new password inputs.
- **Card 3 — Active Workspace Configuration**: Display of active upstream scrapers, active extraction definitions, screening LLM model, and cron schedule for automated review digests.
- **Card 4 — Notification Delivery Preferences (`NotificationSettings`)**: Instant email alerts on pipeline completion and failure alerts.

```
+---------------------------------------------------------------------------------------------------------------+
|  [ SRI Logo ]   Workspace: [ Quantum Computing ▾ ]    Run: [ Run #14 (Latest Successful) ▾ ]  | [ Profile ▾ ] |
+---------------------------------------------------------------------------------------------------------------+
|  Settings                                                                                                     |
|  Your personal profile, active workspace configuration, and notification delivery rules.                     |
|                                                                                                               |
|  +---------------------------------------------------------------------------------------------------------+  |
|  |  👤 Personal Profile                                                                                    |  |
|  |  Name:  [ Piotr B.                                    ]   Email: [ piotr@example.com                  ] |  |
|  |  Role:  Manager (Can Run Pipelines)                                 [ Save Profile Changes ]         |  |
|  +---------------------------------------------------------------------------------------------------------+  |
|                                                                                                               |
|  +---------------------------------------------------------------------------------------------------------+  |
|  |  🔒 Security & Password Change                                                                          |  |
|  |  Current Password: [ ************ ]   New Password: [ ************ ]   [ Update Password ]              |  |
|  +---------------------------------------------------------------------------------------------------------+  |
|                                                                                                               |
|  +---------------------------------------------------------------------------------------------------------+  |
|  |  ⚙️ Active Workspace Configuration (Quantum Computing)                                                 |  |
|  |  • Sources: arXiv · OpenAlex                                                                           |  |
|  |  • Extraction Definitions: Gate TRL · Bonus TRL · Qubit Count · Readout Latency                        |  |
|  |  • Screening Model: gpt-4o (Dual-stage evaluation)                                                      |  |
|  |  • Automated Schedule: Weekly on Monday at 06:00 UTC (cron: 0 6 * * 1)                                    |  |
|  +---------------------------------------------------------------------------------------------------------+  |
|                                                                                                               |
|  +---------------------------------------------------------------------------------------------------------+  |
|  |  🔔 Notification Delivery Preferences                                                                   |  |
|  |  [✓] Send email executive briefing on pipeline run completion                                          |  |
|  |  [ ] Alert on pipeline execution failure or API quota errors                                           |  |
|  |  Delivery Email: [ alerts@domain.com                    ]                      [ Save Preferences ]     |  |
|  +---------------------------------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------------------------------+
```

> [!NOTE]
> **Role Variations on Settings Screen**:
> - **Manager**: Profile displays `Role: Manager (Can Run Pipelines)`. Card 4 allows subscribing to run failure alerts and automated completion summaries.
> - **Researcher**: Profile displays `Role: Researcher (Results Only)`. Allows self-service credential updates and briefing email notifications.
> - **System Admin**: Dedicated administration portal encompassing workspace management & editing, extraction definitions, workspace members & roles, and upstream scrapers & quotas is deferred to a **Future Iteration**.

---

## 8. Screen 7: Authentication & Institutional Login (`/`)

### Layout Topology
- **Centered Isolation Shell**: Focuses the user directly on credential validation or institutional single-sign-on without extraneous navigation chrome.
- **Card Contents**: SRI Institutional Branding, email and password form fields with client-side validation, error toast container, and corporate SAML/OAuth SSO option.

```
+---------------------------------------------------------------------------------------------------------------+
|                                                                                                               |
|                                     +-----------------------------------+                                     |
|                                     |    [ SRI Institutional Logo ]     |                                     |
|                                     |  SCHWARZ RESEARCH INTELLIGENCE   |                                     |
|                                     |  Automated Systematic Literature  |                                     |
|                                     |  Review & Signal Discovery Engine |                                     |
|                                     | --------------------------------- |                                     |
|                                     |  Sign in to your account          |                                     |
|                                     |                                   |                                     |
|                                     |  Email Address                    |                                     |
|                                     |  [ user@institution.org         ] |                                     |
|                                     |                                   |                                     |
|                                     |  Password                         |                                     |
|                                     |  [ •••••••••••••••••••••••••••• ] |                                     |
|                                     |                                   |                                     |
|                                     |  [       Sign In to SRI ➔       ] |                                     |
|                                     |                                   |                                     |
|                                     |  -------------------------------- |                                     |
|                                     |  [ 🏛️ Sign in with Corporate SSO ]|                                     |
|                                     +-----------------------------------+                                     |
|                                                                                                               |
+---------------------------------------------------------------------------------------------------------------+
```

---

*End of Wireframes Specification. For interaction flowcharts, state transitions, and sequence diagrams, refer to [user_journeys.md](user_journeys.md).*
