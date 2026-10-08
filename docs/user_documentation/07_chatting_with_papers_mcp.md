# 💬 Guide 07: Interrogating & Chatting with Papers via MCP (Ask Paper & Knowledge Explorer)

The **Schwarz Research Intelligence (SRI)** interactive paper exploration tool (`ask_paper`) turns ingested academic papers into dynamic, conversational scientific advisors powered by **Google Gemini 3.7 Flash**.

---

## 🌐 Quick Access
* **Live MCP SSE Endpoint**: `https://research-scanner.schwarz/mcp/sse` *(or `https://sri-prod.apps.01.cf.eu01.onstackit.cloud/mcp/sse`)*
* **Web App URL**: [https://research-scanner.schwarz/](https://research-scanner.schwarz/) *(or [Cloud Foundry mirror](https://sri-prod.apps.01.cf.eu01.onstackit.cloud/))*
* **Admin Portal**: [https://research-scanner.schwarz/admin/](https://research-scanner.schwarz/admin/) *(or [Cloud Foundry mirror](https://sri-prod.apps.01.cf.eu01.onstackit.cloud/admin/))*

---

## 🧠 What Makes SRI Paper Chat Unique?

Unlike standard document chat tools that only pass text fragments, `ask_paper` injects the **complete scientific context** of the review:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 AUTOMATICALLY INJECTED SCIENTIFIC CONTEXT                              │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘

 ┌───────────────────────────────────────┐
 │ 📄 Full Multimodal Document Content   │ ──► Raw layout-aware PDF binary or markdown text
 ├───────────────────────────────────────┤
 │ ⚖️ SLR Screening Decision & Rationale │ ──► Inclusion/exclusion criteria & exact reasoning
 ├───────────────────────────────────────┤
 │ 📊 Dynamic Parameter Extractions      │ ──► All extracted KPIs, schemas, and evidence quotes
 ├───────────────────────────────────────┤
 │ 🧮 Composite Signal Score Audit       │ ──► Computed ranking score & Python math formula
 ├───────────────────────────────────────┤
 │ 👁️ Visual Grounding & Bounding Boxes  │ ──► Figure, table, and equation visual coordinates
 ├───────────────────────────────────────┤
 │ 🛡️ Hallucination Guard Validation     │ ──► Automatic claim verification against source text
 ├───────────────────────────────────────┤
 │ ⚡ Gemini Context Caching             │ ──► Instant multi-turn recall with server-side caching
 └───────────────────────────────────────┘
```

---

## 🧭 Multi-Turn Conversation Workflow

```
 Turn 1 (Initiate Chat Session)
 ┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │ USER: "Explain how the authors fabricated the solid electrolyte pouch cell and verify conductivity." │
 │ └─► ask_paper(workspace_id=..., paper_id=..., question=..., deep_thinking=True)                      │
 │     └─► Returns Answer + Citations + session_id: "c8e1a90b-..."                                      │
 └──────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
 Turn 2+ (Continue Conversational Context)
 ┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │ USER: "Does this match the impedance spectroscopy shown in Figure 3?"                                │
 │ └─► ask_paper(workspace_id=..., session_id="c8e1a90b-...", question=...)                             │
 │     └─► Reuses server-cached tokens for instant, zero-cost conversational memory                      │
 └──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 💡 Real-World Prompts to Ask Claude Code

### 1. Methodology & Experimental Verification
> *"In Zhang et al. (2026), what exact solvent and sintering temperature did they use for the sulfide electrolyte membrane? Point to the exact table or figure."*

### 2. Deep Mathematical & Thermodynamic Derivations (`deep_thinking=True`)
> *"Derive the mathematical proof used in Section 3 for the quantum circuit upper bound. Verify if the asymptotic complexity claim $O(N \log N)$ holds under their error model."*

### 3. Cross-Paper Synthesis (Workspace Overview)
> *(Omit `paper_id`)*
> *"Across all accepted papers in this workspace, summarize the main degradation mechanisms identified for lithium metal anodes under fast charging (>2C)."*

### 4. SLR Decision Deep-Dive
> *"Why did the SLR pipeline accept paper A but reject paper B? Compare their reported volumetric energy densities against our workspace criteria."*

---

## 🛠️ MCP Tool: `ask_paper` Reference

### Parameters:
* `workspace_id` *(required)*: UUID of the workspace.
* `question` *(required)*: Detailed research question or instruction.
* `paper_id` *(optional)*: Target Paper UUID. *Omit for a workspace overview: the model then sees only the titles and signal scores of the top accepted papers, not their text.*
* `session_id` *(optional)*: UUID of an existing conversation session to continue.
* `deep_thinking` *(optional, boolean)*: Set to `true` to raise the model's thinking budget, get its thought trace back in `thinking_process`, and have it verify numerical claims against the document. Slower and costs more output tokens.

### Tool Invocation Example (Turn 1):
```json
{
  "workspace_id": "7b8e1a90-3f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "paper_id": "3a4b5c6d-7e8f-9a0b-1c2d-3e4f5a6b7c8d",
  "question": "What is the primary degradation mechanism of the sulfide electrolyte at 4.5V, and what coating is proposed to mitigate it?",
  "deep_thinking": true
}
```

### Tool Response Payload:
```json
{
  "status": "completed",
  "session_id": "c8e1a90b-4f2d-4b5c-8a1e-9d0c2e3f4a5b",
  "message_id": "1f2e3d4c-5b6a-7890-bcde-f0123456789a",
  "paper_id": "3a4b5c6d-7e8f-9a0b-1c2d-3e4f5a6b7c8d",
  "paper_title": "High-Conductivity Sulfide Solid Electrolytes for 450 Wh/kg Pouch Cells",
  "answer": "Above 4.2 V the sulfide framework oxidises [Fig 4, quote: \"irreversible oxidation peaks beginning at 2.3 V with severe interfacial degradation above 4.2 V\"]. The authors mitigate this with a 5 nm LiNbO3 coating on the cathode particles [Table 2, quote: \"88.4% capacity retention after 500 cycles\"].",
  "thinking_process": "...",
  "citations": [],
  "visual_citations": [
    { "label": "Fig 4", "quote": "irreversible oxidation peaks beginning at 2.3 V with severe interfacial degradation above 4.2 V", "verified_in_source": true },
    { "label": "Table 2", "quote": "88.4% capacity retention after 500 cycles", "verified_in_source": true }
  ],
  "hallucination_guard": { "verified": true, "grounding_score": 1.0, "verified_count": 2, "total_count": 2, "status": "PASS" },
  "deep_thinking": true,
  "llm_model": "google/gemini-3.8-flash",
  "tokens_in": 18421,
  "tokens_out": 1930,
  "tokens_cached": 17800,
  "total_tokens": 20351,
  "usd_cost": 0.0112,
  "session_total_tokens": 20351,
  "session_total_usd_cost": 0.0112,
  "workspace_monthly_tokens": 1483902,
  "workspace_monthly_usd": 4.87
}
```
Markers carry a page number (`[Page 5, Fig 4, quote: "..."]`) and a `box_2d` only when the paper was sent as a PDF; the usual OCR-markdown path has no page numbers. Generation failures return `{ "status": "failed", "message_id", "session_id", "error" }`; bad requests return `{ "status": "error", "error" }`.

---

## 🎯 Summary
With `ask_paper` and the SRI platform, enterprise research teams can:
1. Extract precise engineering parameters in minutes.
2. Verify claims directly against original PDF figures and equations.
3. Rapidly synthesize evidence across hundreds of academic publications.

For full system details and pipeline configuration, explore the complete [User Documentation Index](./README.md).
