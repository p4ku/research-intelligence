# 🖥️ Research Intelligence - Frontend Panel

This is the Next.js web application providing the user interface for the **Research Intelligence** system. It is designed to serve enterprise researchers, allowing them to manage multitenant workspaces, monitor ingestion pipelines, verify model extractions, interact with the RAG Knowledge Base, and view Deep Research agents.

---

## 🏛️ Directory Structure

The frontend application uses Next.js (App Router), TypeScript, and Tailwind CSS.

```
frontend/
├── Dockerfile               # Production & local development docker image build
├── package.json             # NPM dependencies & task runners
├── tailwind.config.js       # Custom design system tokens
├── postcss.config.js
└── src/
    ├── app/                 # Routing pages
    │   ├── layout.tsx       # Global layout (Sidebar, Theme, Header)
    │   ├── page.tsx         # Ingestion overview & metrics dashboard
    │   ├── workspaces/      # Project prompt engineering & configuration pages
    │   ├── papers/          # Ingested PDF & Markdown list & reader view
    │   ├── extractions/     # Parameter extractions & TRL scoring overview
    │   ├── hitl/            # Human-in-the-loop audit verification view
    │   ├── chat/            # RAG agentic explorer & Deep Research panel
    │   └── reports/         # Generated executive briefs & refinement loops
    ├── components/          # Reusable UI components
    │   ├── ui/              # Glassmorphic panels, tables, charts, buttons
    │   ├── dashboard/       # Metrics counters, task progress monitors
    │   └── chat/            # Agent thought logs, message bubbles, source cards
    └── lib/                 # Core utilities
        ├── api.ts           # Django API request client wrapper
        └── utils.ts         # Formatting & styling helper libraries
```

---

## 🎨 Design System & Aesthetics (Premium Interface)

To deliver a premium, state-of-the-art user experience (moving away from basic minimal products), the application conforms to a cohesive design language:

### 1. Color Palette (Dark Theme / Glassmorphism)
- **Primary Background**: HSL-based dark graphite (`#0d0e12`).
- **Surface Panels**: Semitransparent slate (`rgba(22, 28, 45, 0.4)`) with fine border stroke (`rgba(255, 255, 255, 0.05)`) and back-drop blur filters (`backdrop-blur-md`) to produce an elegant glassmorphism effect.
- **Accents**: 
  - Emerald Green: Successful screenings & high-TRL claims.
  - Electric Blue: Running agents & database searches.
  - Coral Purple: Deep Research loops & hypothesis creation.
  - Amber Gold: Warnings, budget exhaustion, or pending human verification.

### 2. Micro-Animations & Interactivity
- Hover scale-ups (`transition-transform duration-300 hover:scale-[1.02]`) on dashboard metric cards.
- Glowing pulse rings on active Celery task indicators (such as OCR conversion or Deep Research loops running).
- Smooth fading chat animations for agent responses, displaying step-by-step reasoning chains.

---

## 🔑 Page Specifications

### 1. Dashboard Overview (`/app/page.tsx`)
- Displays overall metrics: Active Workspaces, Total Papers Ingested, Token Consumption (Current Month Budget Tracker), Ingestion Funnel rates (Papers Ingested -> Screened -> Approved -> Extracted).
- Live Task Monitor: Shows running Celery worker tasks with progress bars (e.g., "Docling OCR: Processing page 4/12").

### 2. Workspace & Prompt Manager (`/app/workspaces/[id]/page.tsx`)
- Allows workspace owners to configure project boundaries without editing code:
  - **Search Source toggles**: Choose arXiv, OpenAlex, and Lens.org credentials.
  - **Inclusion/Exclusion criteria**: Define rules (e.g., "Exclude meta-analyses", "Include only papers testing human cells").
  - **Pydantic Extractor Schemas**: Interactive editor to define key-value variables to pull from full-texts.
  - **Cost Guards**: Set daily token and USD spending budgets for this workspace.

### 3. Ingested Literature Reader (`/app/papers/page.tsx`)
- List of papers with dynamic columns: Title, Ingestion Source, Screening Status (Passed/Rejected), screening reasoning.
- **Reader View**: Split-screen showing the original PDF side-by-side with the parsed layout Markdown file. Clicking highlighted terms reveals the extraction source.

### 4. Extracted Claims & TRL Dashboard (`/app/extractions/page.tsx`)
- A structured table displaying extracted parameters, transmission models, and patent findings.
- Fully filterable by workspace, category, and Technology Readiness Level (TRL 1-9).
- Clicking a TRL score displays the supporting quotes grounded in the original PDF, showing exactly why the agent scored it as such.

### 5. Human-in-the-Loop (HITL) Verification (`/app/hitl/page.tsx`)
- Tailored for expert validation.
- Displays model extractions flag for human verification side-by-side with the source document snippet.
- Reviewers can click **Approve**, **Reject**, or **Edit Value**. If edited, it submits a payload to Django's `HITLCorrection` model, recording the adjustment lineage.

### 6. RAG Chat & Deep Research Assistant (`/app/chat/page.tsx`)
- Interactive agent chat panel allowing users to query the ingested literature corpus.
- Supports **Agent Thought Logs**: A collapsible panel displaying the agent's step-by-step logic (e.g., "Step 1: Reformulating query... Step 2: Querying pgvector... Step 3: Fetching patent EP12345...").
- **Deep Research Panel**: Allows users to input a custom research hypothesis. Users can watch the Research Agent autonomously start search tasks, download missing references, test findings, and write a summary.

### 7. Executive Summaries & Refinements (`/app/reports/page.tsx`)
- Document view of the generated weekly briefs.
- Lists compilation history, and displays details of the $K=5$ self-critic refinement loop (revealing the Draft content, Critic comments, Revision revisions, and final Grounded report).
