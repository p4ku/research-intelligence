# 📚 Research Intelligence - Reference Documentation & Scientific Papers

This directory contains key research documentation, blueprints, and scientific papers that serve as the foundation for the Research Intelligence system.

---

## 📖 User Documentation & Operational Guides

*   **[User Documentation Portal](./user_documentation/README.md)**: Product-ready operational guides tailored for all 3 system personas: **Manager / Researcher** (Next.js Web Dashboard), **Power User / AI Engineer** (FastMCP / Claude Code / Cursor), and **Administrator** (Django Admin Portal & Storage Browser).
*   **[System Architecture & Pipelines Blueprint](./architecture.md)**: Enterprise architecture documentation featuring the 3 core personas, routing layers, DAG state engines, pluggable LLM/OCR factories, and database persistence.
*   **[Security Architecture & Threat Model Specification](./SECURITY.md)**: Enterprise security blueprint detailing AST Sandboxing, RBAC matrices, SSRF prevention, Prompt Injection guards, JWT lifecycle, and audit logging.

---

## 🔗 Project Navigation

*   **[Root README.md](../README.md)**: Main project documentation, monorepo structure, and local quick-start.
*   **[PLAN.md](../PLAN.md)**: Approved architecture blueprint, detailing the 8 Celery worker stages, multitenancy design, and LLM cost-limiting guardrails.
*   **[Backend README.md](../backend/README.md)**: Detailed Django DB models, Celery task methods, Sentry configurations, and Google Agent API client info.
*   **[Frontend README.md](../frontend/README.md)**: Next.js page guides, App Router folders, and design/styling principles (glassmorphism).
*   **[CI/CD Workflow README.md](../.github/workflows/README.md)**: GitHub Actions integration rules, deployment targets (Hetzner, Schwarz Digits Cloud), and environment secrets lists.
