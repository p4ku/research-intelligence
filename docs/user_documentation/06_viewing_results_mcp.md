# 📊 Guide 06: Viewing Review Results & Technology Scorecards via MCP

Using Claude Code, Cursor, or any MCP AI assistant, you can instantly generate structured technology scorecards, compare scientific performance metrics, and inspect accepted literature in formatted Markdown tables.

---

## 🌐 Quick Access
* **Live MCP SSE Endpoint**: `https://sri-prod.apps.01.cf.eu01.onstackit.cloud/mcp/sse`
* **Web App URL**: [https://sri-prod.apps.01.cf.eu01.onstackit.cloud/](https://sri-prod.apps.01.cf.eu01.onstackit.cloud/)
* **Admin Portal**: [https://sri-prod.apps.01.cf.eu01.onstackit.cloud/admin/](https://sri-prod.apps.01.cf.eu01.onstackit.cloud/admin/)

---

## 🧭 Scorecard Query Flow

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              GENERATING TECHNOLOGY SCORECARDS VIA MCP                                  │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘

 USER PROMPT
 💬 "Show me the technology scorecard and top papers from the latest Solid-State Battery run."
   │
   ▼
 CLAUDE CODE / MCP CLIENT
   │
   └──► Calls: get_paper_extractions_matrix(process_id="...", screening_status="accepted")
          │
          ▼
 RESPONSE GENERATION
 📊 Compiles aggregated Markdown table ranking papers by Signal Score with all extracted KPIs:
    • Paper Title & Authors
    • Signal Score (Composite Ranking)
    • Extracted KPIs (Energy Density, Conductivity, TRL)
    • Verified Evidence Quotes
```

---

## 💡 Quick Start: Conversational Scorecard Prompts

You can request results in natural language:

### Prompt 1: High-Level Technology Scorecard
> *"Show me the technology matrix and extracted parameters for all accepted papers in workspace 'Solid-State Battery Breakthroughs 2026'."*

### Prompt 2: Parameter Comparison Table
> *"Compare the ionic conductivity, energy density, and TRL across all accepted papers. Highlight the top 3 highest-scoring technologies."*

### Prompt 3: Deep Screening Audit
> *"List the papers that were rejected during full-text screening along with Gemini's rationale for rejection."*

---

## 🛠️ Primary MCP Tools for Results & Extractions

### 1. `get_paper_extractions_matrix` (Primary Scorecard Tool)
This is the **core tool** for retrieving run results. It aggregates all accepted papers, their composite signal scores, screening decisions, and dynamic extraction definitions in a **single structured call**.

#### Parameters:
* `process_id` *(optional)*: Filter by Research Agent Process UUID.
* `pipeline_run_id` *(optional)*: Filter by Pipeline Run UUID.
* `workspace_id` *(optional)*: Filter by Workspace UUID.
* `screening_status` *(optional)*: Filter by `accepted` (default) or `rejected`.
* `limit` *(optional)*: Max number of papers to return.

#### Example Tool Invocation:
```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "screening_status": "accepted"
}
```

#### Example Output Rendered by Claude Code:

### 🏆 Technology Assessment Scorecard

| Rank | Paper Title | Authors | Energy Density | Conductivity | TRL | Signal Score |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: |
| 🥇 **1** | **High-Conductivity Sulfide Solid Electrolytes for 450 Wh/kg Pouch Cells** | Zhang, L., et al. (2026) | **432.5 Wh/kg** | 12.8 mS/cm | **5** | **94.2** |
| 🥈 **2** | **Halide-Garnet Composite Interlayers for Dendrite-Free Anodes** | Müller, H., et al. (2026) | **395.0 Wh/kg** | 8.4 mS/cm | **4** | **82.5** |
| 🥉 **3** | **Scalable Dry-Coating Process for Polymer Solid-State Batteries** | Chen, W., et al. (2025) | **340.0 Wh/kg** | 3.2 mS/cm | **6** | **76.8** |

---

#### 🔍 Detailed Findings & Evidence Quotes:

1. **High-Conductivity Sulfide Solid Electrolytes for 450 Wh/kg Pouch Cells**
   * **DOI / ArXiv**: `arXiv:2602.04182` | **Status**: `accepted`
   * **Signal Score**: `94.2 / 100`
   * **Battery Specs**:
     * *Electrolyte Type*: Sulfide ($Li_{10}GeP_2S_{12}$ derivative)
     * *Energy Density*: $432.5\text{ Wh/kg}$
     * *Room Temp Conductivity*: $12.8\text{ mS/cm}$
     * *Cycle Retention*: $88.4\%\text{ after } 500\text{ cycles}$
   * **Verbatim Evidence Quote**:
     > *"The fabricated pouch cell demonstrated a gravimetric energy density of 432.5 Wh kg−1 at 0.1 C and retained 88.4% capacity after 500 cycles at room temperature." (Page 4, Table 2)*
   * **TRL Assessment**: Level 5 (Component validation in relevant environment / pouch cell).

---

### 2. `list_papers` (Bibliographic Explorer)
List all ingested papers with metadata, abstracts, and screening statuses:

```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "limit": 20
}
```

### 3. `list_extractions` & `get_extraction` (Low-Level Audit)
Inspect raw extraction objects, confidence scores, and validation flags:

```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "validation_status": "pass",
  "limit": 10
}
```

---

## 🎯 Next Steps
Want to interrogate a specific paper on its experimental methodology, verify circuit depths, or ask follow-up questions?
* Deep dive with AI chat: **[Guide 07: Chatting with Papers via MCP](./07_chatting_with_papers_mcp.md)**
