# 📋 System Requirements Specification (SRS)
**Document Version:** 1.0.0  
**Target Audience:** Engineering Leads, Architects, and Product Stakeholders  

---

## 1. System Objective & Scope
The **Research Intelligence (RI)** platform is an enterprise-grade agentic system designed to automate systematic literature reviews (SLRs) and technology readiness level (TRL) assessments. The system performs automated ingestion, deduplication, screening, parsing (OCR), dynamic JSON extraction, and weekly narrative/LaTeX report synthesis from scientific publications.

---

## 2. Functional Requirements (FR)

### FR-1: Multi-Source Ingestion & Scrapers
The system must support automated ingestion of scientific papers and patents from multiple metadata and full-text datasources.
*   **Datasources Required:**
    1.  **arXiv:** Retrieve scientific preprints, abstracts, metadata, and PDF links.
    2.  **OpenAlex:** Query global scholarly charts and access open-access documents.
    3.  **Lens.org:** Fetch comprehensive metadata, citation links, and patent/scholarly database records.
*   **Deduplication:** The ingestion pipeline must compute unique document identifiers (e.g., DOI, arXiv ID, or SHA-256 hash of PDF binary contents) to prevent duplicate processing.
*   **Ingestion Schedule:** Allow workspaces to configure scraper queries and execute them periodically.

### FR-2: Pluggable Document Parsing (OCR)
The system must expose a unified `BaseOCRProvider` interface to extract layout-preserving Markdown text from raw PDFs. The active provider is resolved dynamically via `OCRProviderFactory`.
*   **Docling:** High-fidelity layout analysis (tables, headers, math equations) optimized for local CPU/GPU execution.
*   **Mistral OCR:** High-fidelity cloud API fallback.
*   **PyPDF:** Lightweight, local, in-process engine for quick text extraction (fallback).

### FR-3: Pluggable LLM Decoupling
The system must isolate the core execution logic from specific LLM APIs. The `BaseLLMProvider` interface, resolved via `LLMProviderFactory`, must support:
*   **Google Agent API / Vertex AI:** Direct integration for primary high-performance processing (Gemini models).
*   **OpenRouter:** Fallback driver to route queries to alternative proprietary or open-source models (e.g., Claude, Llama, Mixtral).
*   **OpenAI:** Interface definition reserved for future direct integration.
*   **Capabilities Required:** Standardized system/user prompts, strict JSON schema output verification, temperature controls, and parameter constraints.

### FR-4: Orchestrated Asynchronous Pipeline & Batch Processing
All heavy compute steps must be offloaded from the web request thread to distributed background workers running in isolated task queues.
*   **Pipeline Stages:**
    1.  **Download:** Retrieve raw PDFs to object storage.
    2.  **OCR / Parsing:** Process PDFs and write Markdown files.
    3.  **Two-Stage Screening:**
        *   *Abstract Screening:* Filter irrelevant documents using abstract-only context.
        *   *Full-Text Screening:* Conduct deep text analysis against inclusion/exclusion criteria.
    4.  **Schema-Constrained Extraction:** Retrieve specific claims, models, parameters, or patent details into strict JSON fields.
    5.  **TRL Assessment:** Evaluate papers on the 1-9 Technology Readiness Level (TRL) scale.
    6.  **Weekly Narrative Synthesis:** Generate executive summaries, LaTeX bibliographies, BibTeX compilations, and PDF files.
*   **Task State Tracking:** Real-time visibility into pipeline stages (Pending, Running, Completed, Failed).

### FR-5: Narrative Report Critique Loop
The report compilation task must run a self-refinement critique loop of depth $K=5$ (where $K$ represents the maximum refinement iterations).
*   An AI Critique Agent evaluates generated text against target parameters and issues scores.
*   The system uses the critique to iteratively refine the LaTeX/Markdown content.
*   The final report must include the BibTeX reference library and be compiled into a downloadable PDF format.

---

## 3. Non-Functional Requirements (NFR)

### NFR-1: Multi-Tenancy & Workspace Isolation
The platform must support running multiple research projects concurrently across multiple users.
*   **Data Isolation:** All database objects (papers, extractions, runs, scrapers, subscribers) must be partitioned under a top-level `Workspace` foreign key.
*   **Custom Prompting:** Each workspace must support isolated overrides of screening and extraction prompt templates.
*   **Quotas & Budgeting:** Every workspace must enforce absolute monthly token consumption limits and USD budget caps. The system must halt pipeline runs once these thresholds are reached.

### NFR-2: Scalability & Performance Limits
The application architecture must scale horizontally to support active, concurrent user interactions and heavy document processing:
*   **Concurrent Users:** Scale to $\ge 100$ active concurrent users without performance degradation on the Next.js/Django REST API.
*   **Concurrent Projects:** Support $\ge 500$ parallel active research workspaces.
*   **Ingestion Throughput:** Celery worker architecture must be horizontally scalable by adding worker nodes to process 1,000+ PDFs concurrently during batch runs.

### NFR-3: S3-Compatible Storage Strategy
The system must decouple persistent databases from binary asset storage.
*   **Object Storage:** All PDFs, layout-preserving Markdown conversions, and generated PDF/LaTeX narrative reports must be stored in S3-compatible object storage (e.g., AWS S3, Cloudflare R2, or local MinIO).
*   **Link Generation:** The backend must support generating pre-signed URLs or proxying secure download streams to users for document downloads.

### NFR-4: Deployment & Portability
The codebase must be completely dockerized and decoupled from the host operating system.
*   **Containerization:** Define a multi-container environment (PostgreSQL with `pgvector`, Redis for messaging, MinIO for object storage, Django web app, Next.js frontend, Celery beat scheduler, and Celery task workers).
*   **Deployability:** The containerized stack must be portable for deployment to single-instance hosts (e.g., AWS EC2), container management services (e.g., AWS ECS), or orchestrated environments (e.g., Kubernetes).

### NFR-5: Auditing & Testability
*   **Unified Lineage (Audit Trail):** Every backend database/agent call must write to an immutable `AuditTrail` ledger. It must track the calling Celery task, execution time, tokens used (prompt and completion), input payloads, and output payloads.
*   **HITL Audit Trail:** Record all manual human-in-the-loop corrections (scientist operator, original value, corrected value, and reason).
*   **Automated Testing:** The codebase must maintain unit and integration test coverage for the Django endpoints, LLM/OCR providers, and Celery pipelines (verifiable via a automated test execution script).
