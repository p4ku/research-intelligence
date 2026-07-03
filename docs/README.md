# 📚 Research Intelligence - Reference Documentation & Scientific Papers

This directory contains key research documentation, blueprints, and scientific papers that serve as the foundation for the Research Intelligence system.

---

## 📄 Reference Documents in this Directory

*   **[AgentSLR: Automating Systematic Literature Reviews in Epidemiology with Agentic AI](./AgentSLR.pdf)**
    *   *Significance*: This paper serves as the methodology baseline for the system's pipeline. It describes the 6-stage ingestion pipeline, the two-stage screening process (abstract and full-text), ScreenPrompt construction, database deduplication strategies, schema-constrained data extractions, and the $K=5$ self-refinement critique loop for report generation.
*   **[Agentic AI Research Scanner Blueprints](./Agentic%20AI%20Research%20Scanner.pdf)**
    *   *Significance*: Design specifications mapping out the core query-to-insights pipeline, database requirements (PostgreSQL, Redis, vector extensions), and architecture components.
*   **[System Architecture & Pipelines](./architecture.md)**
    *   *Significance*: High-level component interactions, DB states, and detailed sequential ingestion/extraction pipeline stages. Includes compiled architecture diagrams.

---

## 🔗 Project Navigation

*   **[Root README.md](../README.md)**: Main project documentation, monorepo structure, and local quick-start.
*   **[PLAN.md](../PLAN.md)**: Approved architecture blueprint, detailing the 8 Celery worker stages, multitenancy design, and LLM cost-limiting guardrails.
*   **[Backend README.md](../backend/README.md)**: Detailed Django DB models, Celery task methods, Sentry configurations, and Google Agent API client info.
*   **[Frontend README.md](../frontend/README.md)**: Next.js page guides, App Router folders, and design/styling principles (glassmorphism).
*   **[CI/CD Workflow README.md](../.github/workflows/README.md)**: GitHub Actions integration rules, deployment targets (Hetzner, Schwarz Digits Cloud), and environment secrets lists.
