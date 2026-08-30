# 🤖 Guide 02: Setting Up a Research Pipeline via MCP & Claude Code

With the **Schwarz Research Intelligence (SRI) Model Context Protocol (MCP)** server, you can configure your entire systematic review and competitive scouting pipeline conversationally in seconds using Claude Code, Cursor, or any MCP-enabled AI client.

---

## 🌐 MCP Connection & Architecture

* **Live MCP SSE Endpoint**: `https://sri-prod.apps.01.cf.eu01.onstackit.cloud/mcp/sse`
* **Web Application**: [https://sri-prod.apps.01.cf.eu01.onstackit.cloud/](https://sri-prod.apps.01.cf.eu01.onstackit.cloud/)
* **Admin Portal**: [https://sri-prod.apps.01.cf.eu01.onstackit.cloud/admin/](https://sri-prod.apps.01.cf.eu01.onstackit.cloud/admin/)

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               CONVERSATIONAL SETUP VIA CLAUDE CODE / MCP                               │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘

 USER PROMPT (Natural Language)
 💬 "Create a review workspace for Solid-State Batteries, configure ArXiv & OpenAlex,
     and extract Energy Density, Cathode Chemistry, and TRL with custom signal scoring."
                                │
                                ▼
 CLAUDE CODE / MCP CLIENT (Autonomous Tool Invocations)
 ┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │ 1. create_workspace(...)            ──► Creates isolated project with dual-stage criteria           │
 │ 2. add_workspace_member(...)        ──► Adds researchers and team collaborators                     │
 │ 3. create_scraper(...)              ──► Connects ArXiv / OpenAlex / Lens queries                     │
 │ 4. create_extraction_definition(...)──► Sets JSON schemas for Battery Specs & TRL                    │
 │ 5. update_workspace(...)            ──► Installs Python AST scoring formula for ranking              │
 └──────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
 RESPONSE TO USER
 🚀 "Workspace created successfully! Scrapers, extraction matrix, and scoring formula are live."
```

---

## 💡 Quick Start: Single Conversational Prompt

You can set up an entire research initiative with a single natural language instruction in Claude Code:

> **User Prompt to Claude Code**:
> *"Please set up a new research workspace named 'Solid-State Battery Breakthroughs 2026'. Accept papers focusing on solid electrolyte materials, sulfide/oxide chemistries, and cell-level energy density > 400 Wh/kg. Reject pure liquid electrolyte or lead-acid chemistries. Configure scrapers for ArXiv and OpenAlex, create extraction definitions for 'Battery Specs' and 'TRL', and write a signal scoring formula prioritizing energy density and cycle life."*

Claude Code will automatically orchestrate the corresponding FastMCP tools step-by-step.

---

## 🛠️ Step-by-Step MCP Tool Execution

If you prefer to review or execute individual MCP tool calls, follow this sequence:

### Step 1: Create the Isolated Workspace (`create_workspace`)
Creates the project with tailored dual-stage screening criteria.

```json
{
  "name": "Solid-State Battery Breakthroughs 2026",
  "abstract_acceptance_criteria": "Accept research papers evaluating all-solid-state lithium or sodium batteries, solid electrolyte interfaces (garnet, sulfide, halide, polymer), room-temperature ionic conductivity, or pouch cell cycling.",
  "abstract_rejection_criteria": "Reject conventional liquid electrolyte lithium-ion papers, lead-acid, generic supercapacitors, and non-peer-reviewed whitepapers.",
  "full_text_acceptance_criteria": "Accept if the full PDF reports verified experimental data on ionic conductivity (S/cm), volumetric/gravimetric energy density (Wh/kg or Wh/L), capacity retention after >100 cycles, and full cell fabrication details.",
  "full_text_rejection_criteria": "Reject theoretical reviews without experimental or numerical validation, or papers missing core battery performance metrics.",
  "screening_llm_model": "google/gemini-3.7-flash",
  "ocr_provider": null
}
```

*Tool Returns*: `{"status": "success", "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b"}`

---

### Step 2: Add Team Members (`add_workspace_member`)
Grant workspace permissions to your research team:

```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "member_username_or_email": "dr.smith@schwarz.com",
  "role": "manager"
}
```

---

### Step 3: Configure Academic Scrapers (`create_scraper`)
Set up multi-provider academic search queries to harvest relevant literature:

#### ArXiv Scraper
```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "provider": "arxiv",
  "search_query": "cat:cond-mat.mtrl-sci AND (all:\"solid state battery\" OR all:\"solid electrolyte\")",
  "limit": 50,
  "is_active": true
}
```

#### OpenAlex Scraper
```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "provider": "openalex",
  "search_query": "all-solid-state lithium battery energy density ionic conductivity",
  "limit": 50,
  "is_active": true
}
```

---

### Step 4: Define Dynamic Extraction Schemas (`create_extraction_definition`)
Specify the exact structured JSON fields the AI must extract from screened full-text papers.

#### Extraction Target 1: Battery Performance Specifications
```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "name": "Battery Specs",
  "exit_metric": "energy_density_wh_kg",
  "system_prompt": "You are an expert electrochemist and materials scientist. Extract quantitative battery performance metrics with verbatim quotes from the full text.",
  "user_prompt_template": "Extract key electrochemical metrics from the paper:\nTitle: {{paper_title}}\nFull Text: {{full_text}}",
  "response_schema": {
    "type": "object",
    "properties": {
      "electrolyte_type": { "type": "string", "enum": ["Sulfide", "Oxide/Garnet", "Polymer", "Halide", "Composite"] },
      "energy_density_wh_kg": { "type": "number", "description": "Gravimetric energy density in Wh/kg" },
      "room_temp_conductivity_ms_cm": { "type": "number", "description": "Ionic conductivity at 25C in mS/cm" },
      "cycle_retention_pct": { "type": "number", "description": "Capacity retention percentage" },
      "cycles_tested": { "type": "integer", "description": "Number of discharge cycles tested" },
      "evidence_quote": { "type": "string", "description": "Verbatim quote confirming the metrics" }
    },
    "required": ["electrolyte_type", "energy_density_wh_kg", "evidence_quote"]
  }
}
```

#### Extraction Target 2: Technology Readiness Level (TRL)
```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "name": "TRL Assessment",
  "exit_metric": "trl_level",
  "system_prompt": "Assess the Technology Readiness Level (1-9) of the battery prototype.",
  "user_prompt_template": "Assess TRL for {{paper_title}}:\n{{full_text}}",
  "response_schema": {
    "type": "object",
    "properties": {
      "trl_level": { "type": "integer", "minimum": 1, "maximum": 9 },
      "manufacturing_readiness": { "type": "string" },
      "commercial_scalability": { "type": "string" }
    },
    "required": ["trl_level"]
  }
}
```

---

### Step 5: Install Custom Python Signal Scoring Formula (`update_workspace`)
Define your custom mathematical ranking formula using the extracted metric variables (`energy_density_wh_kg`, `trl_level`, `cycle_retention_pct`):

```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "signal_score_code": "if energy_density_wh_kg < 300:\n    return 0.0\nbase = (energy_density_wh_kg / 50.0) + (trl_level * 1.5)\nif cycle_retention_pct and cycle_retention_pct >= 80.0:\n    base *= 1.25\nreturn round(min(100.0, base), 2)"
}
```

---

### Step 6: Verify Configuration (`get_workspace`)
Inspect your complete live workspace configuration:

```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b"
}
```

---

## 🚀 What's Next?
Your research intelligence workspace is fully configured. You can now:
* Launch your automated review run: **[Guide 04: Running Pipelines via MCP](./04_running_pipeline_mcp.md)**
* Inspect scorecard results: **[Guide 06: Viewing Results via MCP](./06_viewing_results_mcp.md)**
* Ask questions directly to papers: **[Guide 07: Chatting with Papers via MCP](./07_chatting_with_papers_mcp.md)**
