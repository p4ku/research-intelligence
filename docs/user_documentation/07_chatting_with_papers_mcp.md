# 💬 Guide 07: Interrogating & Chatting with Papers via MCP (Ask Paper & Knowledge Explorer)

The **Schwarz Research Intelligence (SRI)** interactive paper exploration tool (`ask_paper`) turns ingested academic papers into dynamic, conversational scientific advisors powered by **Google Gemini 3.7 Flash**.

---

## 🌐 Quick Access
* **Live MCP SSE Endpoint**: `https://sri-prod.apps.01.cf.eu01.onstackit.cloud/mcp/sse`
* **Web App URL**: [https://sri-prod.apps.01.cf.eu01.onstackit.cloud/](https://sri-prod.apps.01.cf.eu01.onstackit.cloud/)
* **Admin Portal**: [https://sri-prod.apps.01.cf.eu01.onstackit.cloud/admin/](https://sri-prod.apps.01.cf.eu01.onstackit.cloud/admin/)

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
* `paper_id` *(optional)*: Target Paper UUID. *Omit to perform multi-document synthesis across the entire workspace.*
* `session_id` *(optional)*: UUID of an existing conversation session to continue.
* `deep_thinking` *(optional, boolean)*: Set to `true` to enable deep mathematical/thermodynamic derivation scratchpad reasoning.

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
  "answer": "The primary degradation mechanism above 4.2V vs Li/Li+ is the electrochemical oxidation of sulfur anions in the Li10GeP2S12 framework, forming insulating S0, P2S5, and GeS2 interfacial species that increase cell impedance (Section 3.2, Page 5).\n\nTo mitigate this, the authors applied an atomic layer deposition (ALD) nano-coating of LiNbO3 (approx. 5 nm thickness) onto the NCM811 cathode particles. This coating suppressed oxidative decomposition up to 4.5V, maintaining 88.4% capacity retention after 500 cycles at 25°C.",
  "citations": [
    {
      "claim": "electrochemical oxidation of sulfur anions in the Li10GeP2S12 framework",
      "verbatim_quote": "Cyclic voltammetry reveals irreversible oxidation peaks beginning at 2.3 V with severe interfacial degradation above 4.2 V vs Li/Li+ due to sulfur oxidation.",
      "page_number": 5
    }
  ],
  "visual_citations": [
    {
      "caption": "Figure 4: In situ XPS spectra of the electrolyte-cathode interface at 4.5V",
      "page_number": 6,
      "bounding_box": [120, 340, 480, 720]
    }
  ],
  "hallucination_guard": {
    "status": "verified",
    "faithfulness_score": 1.0
  },
  "deep_thinking": true,
  "usd_cost": 0.0042,
  "cached_content": "active"
}
```

---

## 🎯 Summary
With `ask_paper` and the SRI platform, enterprise research teams can:
1. Extract precise engineering parameters in minutes.
2. Verify claims directly against original PDF figures and equations.
3. Rapidly synthesize evidence across hundreds of academic publications.

For full system details and pipeline configuration, explore the complete [User Documentation Index](./README.md).
