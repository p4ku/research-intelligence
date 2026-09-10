# User Journey: Pipeline Run Deep-Dive & Execution DAG

## 1. Overview & Objective

The **Run Details Journey** (`/runs/[id]`) delivers a deep technical trace into a specific pipeline execution. It reveals end-to-end telemetry: ingestion volume, screening conversion rates, token consumption, total inference cost, execution parameters, and a granular step-by-step DAG breakdown detailing upstream scrapers and LLM screening models.

---

## 2. Interface View

The Run Details view provides a complete post-execution audit log:

![Pipeline Run Execution Details](./screenshots/06_run_details.png)

---

## 3. Navigation & URL Route

- **Primary Route**: `/runs/[id]` (e.g., `/runs/1243db08-42bd-44a3-95fc-f5ee4664c181`)
- **Breadcrumb Trail**: `RUNS` (`/runs`) &nbsp;➔&nbsp; `[Short UUID]` (e.g., `1243DB08`)
- **Access Points**:
  - Clicking any run row in the Runs overview (`/runs`).
  - Accessing the run link from a briefing edition header.

---

## 4. UI Components & Screen Topology

The view is structured into three primary analytical sections:

### 4.1 Header & Core Metrics Strip
- **Breadcrumbs**: Instant back-link to the full runs ledger.
- **Domain Eyebrow & Run Identifier**: `HYBRID COMPUTING` / `Run 1243db08`.
- **Outcome Status Badge**: Green pill `Completed` (or `Running`, `Failed`).
- **Executive Summary**: Comprehensive execution statement (*"Full SLR pipeline finished successfully. Papers: 416 fetched, 34 passed screening, 136 parameter extractions completed."*).
- **Four Core KPI Cards**:
  - **`Fetched` (416)**: Total documents returned by upstream scrapers.
  - **`Passed screening` (34)**: Relevant documents retained (with percentage yield: `8% of fetched`).
  - **`Papers stored` (416)**: Persistent bibliographic records archived in this run.
  - **`Extractions` (136)**: Specific scientific and technological parameters extracted.

### 4.2 Run Configuration & Resource Consumption Grid
A dedicated metadata container surfaces operational telemetry:
- **`STARTED (UTC)`**: Start timestamp (`9 Sept 2026, 21:26`).
- **`DURATION`**: Total runtime (`12m 53s`).
- **`COST`**: Exact dollar spend (`$2.47`).
- **`TOKENS`**: Total LLM token usage (`2,829,039` tokens: `2,713,810 in · 115,229 out`).
- **`TRIGGERED BY`**: Identity of user or cron trigger (`adam.mahdi@gmail.com`).
- **`MODE`**: Deduplication policy (`Skip duplicates`).
- **`LAST STAGE DISPATCHED`**: Terminal DAG stage (`Completed`).
- **`DUPLICATES`**: Documents identified as redundant and skipped (`152`).
- **`ARTEFACTS`**: Generated intermediate files and PDFs (`89.72 MB · 39 files`).

### 4.3 Step-by-Step DAG Execution Stages
A sequential timeline detailing each discrete pipeline stage (`9 steps · $2.47 attributed`):

1. **arXiv Search (`arxiv_scraper`)**:
   - Status: `Completed`
   - Yield: `384 new`, `518 fetched`, `134 duplicates`
   - Timing: `2m 16s`
2. **OpenAlex Search (`openalex_scraper`)**:
   - Status: `Completed`
   - Yield: `32 new`, `50 fetched`, `18 duplicates`
   - Timing: `7.9s`
3. **Abstract Screening**:
   - Status: `Completed`
   - Filtering: `416 screened` &nbsp;➔&nbsp; `42 passed`, `373 rejected`, `1 withdrawn`
   - Timing & Cost: `3m 41s` | `$0.68 · 704,634 tok`
   - Model Attribution: `google/gemini-3.8-flash`
4. *(Subsequent stages include Full-Text Fetching, Full-Text Screening, Dimensional Extraction, and Briefing Synthesis).*

---

## 5. Step-by-Step User Workflow

### 5.1 Inspecting Run Health & Throughput
1. From `/runs`, click on a run row to open its details.
2. Review the **Outcome** badge and **Summary** statement.
3. Check the **Fetched** vs. **Passed screening** ratio to verify scraper health and screening selectivity.

### 5.2 Analyzing LLM Spend & Token Efficiency
1. Check the **COST** and **TOKENS** fields in the metadata grid.
2. In the **STEPS** breakdown, locate which stage incurred the highest token usage (typically *Abstract Screening* or *Full-Text Screening*).
3. Verify the underlying model deployed (e.g., `gemini-3.8-flash`) and its cost contribution.

### 5.3 Diagnosing Deduplication Performance
1. Inspect the **DUPLICATES** count in the metadata grid and across individual scrapers (e.g., 134 duplicates caught during arXiv search).
2. Confirm that previously analyzed papers were appropriately deduplicated without incurring redundant LLM inference costs.

---

## 6. Technical Invariants & Troubleshooting

- **Reproducibility**: The exact model checkpoint, prompt versions, and scraper configurations are permanently bound to the run record.
- **Failure Isolation**: If any individual step encounters an error, the DAG halts at that stage, logs the stack trace in the step row, and flags the run as `Failed` with partial artifacts preserved for inspection.
