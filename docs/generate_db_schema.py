#!/usr/bin/env python3
"""
Database Schema Diagram Generator for Schwarz Research Intelligence.

Generates two comprehensive schema diagrams:
1. High-Level Overview (Domain entities and relationships without individual columns)
2. Detailed ERD (Full columns, data types, primary keys, foreign keys, and relations)

Outputs:
- docs/diagrams/db_schema_overview.mmd
- docs/diagrams/db_schema_detailed.mmd
- docs/images/db_schema_overview.png
- docs/images/db_schema_detailed.png
"""

import os
import sys
import json
import base64
import urllib.request
import urllib.parse

# Directory paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
DIAGRAMS_DIR = os.path.join(DOCS_DIR, "diagrams")
IMAGES_DIR = os.path.join(DOCS_DIR, "images")

os.makedirs(DIAGRAMS_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)


# ==============================================================================
# 1. HIGH-LEVEL SCHEMA OVERVIEW (No Column Clutter)
# ==============================================================================
DB_SCHEMA_OVERVIEW_MERMAID = """graph TB
    subgraph IdentityDomain ["🔐 Tenancy & Authentication"]
        User["User (Django Auth)"]
        Workspace["🏢 Workspace (Tenant Root)"]
        WorkspaceMember["👤 WorkspaceMember (Role/RBAC)"]
        APIKey["🔑 APIKey (MCP & FastMCP Token)"]
        UserActivityLog["📜 UserActivityLog (Audit Trail)"]
    end
    style IdentityDomain fill:#e8f0fe,stroke:#1a73e8,stroke-width:2px

    subgraph ConfigDomain ["⚙️ Query & Schema Configuration"]
        Scraper["📡 Scraper (arXiv / OpenAlex / Lens)"]
        ExtractionDefinition["📋 ExtractionDefinition (Pydantic Schema)"]
        Subscriber["📬 Subscriber (Email Alerts)"]
    end
    style ConfigDomain fill:#e6f4ea,stroke:#137333,stroke-width:2px

    subgraph ExecutionDomain ["⚡ Pipeline & Orchestration Engine"]
        PipelineRun["🚀 PipelineRun (Batch Execution)"]
        ResearchAgentProcess["🤖 ResearchAgentProcess (State Machine)"]
        ComponentRun["🧱 ComponentRun (Step Execution)"]
    end
    style ExecutionDomain fill:#fef7e0,stroke:#b06000,stroke-width:2px

    subgraph DocumentDomain ["📚 Document Ingestion & Storage"]
        Paper["📄 Paper (Ingested Literature)"]
        DocumentRegistry["⚡ DocumentRegistry (Global SHA256 PDF Cache)"]
    end
    style DocumentDomain fill:#f3e8fd,stroke:#7627bb,stroke-width:2px

    subgraph ExtractionDomain ["🎯 Intelligence, Metrics & Results"]
        Extraction["🧩 Extraction (Structured Fields)"]
        PaperMetric["📊 PaperMetric (Novelty, Rigour, TRL)"]
        NarrativeReport["📑 NarrativeReport (Synthesis Doc)"]
        HITLCorrection["✍️ HITLCorrection (Human Review)"]
    end
    style ExtractionDomain fill:#fce8e6,stroke:#c5221f,stroke-width:2px

    %% Identity Relationships
    User -->|has role in| WorkspaceMember
    User -->|owns| APIKey
    User -->|performed| UserActivityLog
    Workspace -->|has members| WorkspaceMember
    Workspace -->|authorized by| APIKey
    Workspace -->|logged in| UserActivityLog

    %% Config Relationships
    Workspace -->|configures| Scraper
    Workspace -->|defines schema for| ExtractionDefinition
    Workspace -->|notifies| Subscriber

    %% Execution Relationships
    Workspace -->|executes| PipelineRun
    Workspace -->|monitors| ResearchAgentProcess
    PipelineRun -->|orchestrated by| ResearchAgentProcess
    PipelineRun -->|spawns| ComponentRun

    %% Document Relationships
    Workspace -->|contains| Paper
    PipelineRun -->|batches| Paper
    Paper -.->|cached by SHA256| DocumentRegistry

    %% Intelligence Relationships
    Paper -->|extracts| Extraction
    ExtractionDefinition -->|validates| Extraction
    Paper -->|evaluated in| PaperMetric
    Workspace -->|consolidates| PaperMetric
    PipelineRun -->|generates| NarrativeReport
    Workspace -->|publishes| NarrativeReport
    Paper -->|human feedback| HITLCorrection
    Workspace -->|tracks corrections| HITLCorrection

    %% Styling links
    linkStyle 0,1,2,3,4,5 stroke:#1a73e8,stroke-width:2px;
    linkStyle 6,7,8 stroke:#137333,stroke-width:2px;
    linkStyle 9,10,11,12 stroke:#b06000,stroke-width:2px;
    linkStyle 13,14,15 stroke:#7627bb,stroke-width:2px;
    linkStyle 16,17,18,19,20,21,22,23 stroke:#c5221f,stroke-width:2px;
"""


# ==============================================================================
# 2. DETAILED ERD WITH FULL COLUMNS AND DATA TYPES
# ==============================================================================
DB_SCHEMA_DETAILED_MERMAID = """erDiagram
    Workspace ||--o{ WorkspaceMember : "has"
    Workspace ||--o{ APIKey : "secures"
    Workspace ||--o{ UserActivityLog : "audits"
    Workspace ||--o{ Scraper : "configures"
    Workspace ||--o{ ExtractionDefinition : "defines"
    Workspace ||--o{ Subscriber : "notifies"
    Workspace ||--o{ PipelineRun : "executes"
    Workspace ||--o{ ResearchAgentProcess : "manages"
    Workspace ||--o{ Paper : "owns"
    Workspace ||--o{ Extraction : "contains"
    Workspace ||--o{ PaperMetric : "evaluates"
    Workspace ||--o{ NarrativeReport : "publishes"
    Workspace ||--o{ HITLCorrection : "tracks"

    User ||--o{ WorkspaceMember : "member_of"
    User ||--o{ APIKey : "created_by"
    User ||--o{ UserActivityLog : "acts"

    PipelineRun ||--o{ ComponentRun : "executes_steps"
    PipelineRun ||--o{ ResearchAgentProcess : "orchestrated_by"
    PipelineRun ||--o{ Paper : "processes"
    PipelineRun ||--o{ NarrativeReport : "outputs"

    Paper ||--o{ Extraction : "yields"
    Paper ||--o{ PaperMetric : "scored_by"
    Paper ||--o{ HITLCorrection : "corrected_by"

    ExtractionDefinition ||--o{ Extraction : "conforms_to"

    Workspace {
        uuid id PK
        string name
        text description
        string ocr_provider
        string llm_provider
        string screening_llm_model
        text abstract_acceptance_criteria
        text abstract_rejection_criteria
        text full_text_acceptance_criteria
        text full_text_rejection_criteria
        int monthly_token_quota
        int tokens_consumed_this_month
        datetime created_at
        datetime updated_at
    }

    WorkspaceMember {
        uuid id PK
        uuid workspace_id FK
        int user_id FK
        string role
        datetime joined_at
    }

    APIKey {
        uuid id PK
        string key_id UK
        string hashed_secret
        string name
        int user_id FK
        uuid workspace_id FK
        json scopes
        boolean is_active
        datetime last_used_at
        datetime created_at
    }

    UserActivityLog {
        uuid id PK
        int user_id FK
        uuid workspace_id FK
        string user_username
        string user_email
        string workspace_name
        string interface
        string action_name
        string status
        json input_params
        json output_summary
        text error_message
        float execution_time_ms
        string api_key_id
        string ip_address
        string user_agent
        datetime timestamp
    }

    Scraper {
        uuid id PK
        uuid workspace_id FK
        string provider
        string search_query
        int n_last_days
        json provider_params
        string schedule_cron
        int max_results_per_run
        boolean is_active
        datetime last_run_at
        datetime created_at
    }

    ExtractionDefinition {
        uuid id PK
        uuid workspace_id FK
        string name
        string exit_metric
        string llm_model
        text system_prompt
        text user_prompt_template
        json response_schema
        json example_json
        datetime created_at
        datetime updated_at
    }

    Subscriber {
        uuid id PK
        uuid workspace_id FK
        string email
        string notification_frequency
        boolean is_active
        datetime created_at
    }

    PipelineRun {
        uuid id PK
        uuid workspace_id FK
        string status
        string current_stage
        decimal usd_cost
        bigint tokens_in
        bigint tokens_out
        bigint tokens_consumed
        int total_papers_fetched
        int total_papers_passed_screening
        json metrics
        json error_details
        datetime run_date
        datetime started_at
        datetime completed_at
    }

    ResearchAgentProcess {
        uuid id PK
        uuid workspace_id FK
        uuid pipeline_run_id FK
        string name
        string status
        string current_step
        json configuration_override
        json step_history
        text error_message
        datetime started_at
        datetime completed_at
    }

    ComponentRun {
        uuid id PK
        uuid pipeline_run_id FK
        string component_name
        string step_type
        string status
        string celery_task_id
        string raw_storage_path
        json input_params
        json output_data
        json metrics
        text error_traceback
        datetime started_at
        datetime completed_at
    }

    DocumentRegistry {
        uuid id PK
        string sha256_hash UK
        string canonical_pdf_path
        string canonical_ocr_md_path
        string title
        string doi
        string arxiv_id
        bigint pdf_file_size_bytes
        string primary_source
        string ocr_provider
        int access_count
        datetime first_ingested_at
        datetime last_accessed_at
    }

    Paper {
        uuid id PK
        uuid workspace_id FK
        uuid pipeline_run_id FK
        string hash_id
        string title
        string doi
        string arxiv_id
        string primary_category
        text abstract
        string authors
        date published_date
        string pdf_url
        string source_database
        string raw_pdf_path
        string ocr_md_path
        string screening_status
        text screening_reasoning
        datetime ingested_at
    }

    Extraction {
        uuid id PK
        uuid workspace_id FK
        uuid paper_id FK
        uuid extraction_definition_id FK
        string category
        json fields_data
        boolean is_hitl_validated
        string validation_status
        boolean review_required
        float confidence_score
        string confidence_method
        json version_info
        datetime created_at
    }

    PaperMetric {
        uuid id PK
        uuid workspace_id FK
        uuid paper_id FK
        string metric_name
        float score_value
        text qualitative_label
        text justification
        json raw_evidence
        datetime calculated_at
    }

    NarrativeReport {
        uuid id PK
        uuid workspace_id FK
        uuid pipeline_run_id FK
        string title
        string report_type
        text executive_summary
        text full_content_markdown
        json structured_insights
        string generated_by_model
        datetime generated_at
    }

    HITLCorrection {
        uuid id PK
        uuid workspace_id FK
        uuid paper_id FK
        int user_id FK
        string correction_target
        json original_value
        json corrected_value
        text reviewer_comment
        datetime applied_at
    }
"""


def render_to_file(diagram_name: str, mermaid_source: str):
    """
    Saves the Mermaid (.mmd) source file and compiles it into PNG and SVG images.
    Prioritizes local npx @mermaid-js/mermaid-cli, with cloud fallback to mermaid.ink.
    """
    import subprocess
    import shutil

    print(f"\n📊 Rendering: {diagram_name}")

    # 1. Save raw .mmd file
    mmd_path = os.path.join(DIAGRAMS_DIR, f"{diagram_name}.mmd")
    with open(mmd_path, "w", encoding="utf-8") as f:
        f.write(mermaid_source.strip() + "\n")
    print(f"  ✅ Saved Mermaid Source: docs/diagrams/{diagram_name}.mmd")

    png_path = os.path.join(IMAGES_DIR, f"{diagram_name}.png")
    svg_path = os.path.join(IMAGES_DIR, f"{diagram_name}.svg")

    # 2. Try rendering with npx @mermaid-js/mermaid-cli first
    rendered_via_cli = False
    if shutil.which("npx"):
        try:
            print("  🎨 Rendering via local @mermaid-js/mermaid-cli (High-Res Retina 3x)...")
            subprocess.run(
                ["npx", "-y", "@mermaid-js/mermaid-cli", "-i", mmd_path, "-o", png_path, "-b", "white", "-s", "3", "-w", "3200"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            subprocess.run(
                ["npx", "-y", "@mermaid-js/mermaid-cli", "-i", mmd_path, "-o", svg_path, "-b", "white"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print(f"  ✅ Compiled PNG: docs/images/{diagram_name}.png ({os.path.getsize(png_path):,} bytes)")
            print(f"  ✅ Compiled SVG: docs/images/{diagram_name}.svg ({os.path.getsize(svg_path):,} bytes)")
            rendered_via_cli = True
        except Exception as e:
            print(f"  ⚠️ Local mermaid-cli failed ({e}). Falling back to mermaid.ink...")

    # 3. Fallback to mermaid.ink online API
    if not rendered_via_cli:
        import zlib
        # Pako-compatible deflate compression for Mermaid
        compressor = zlib.compressobj(level=9, wbits=15)
        deflated = compressor.compress(json.dumps({"code": mermaid_source, "mermaid": {"theme": "default"}}).encode("utf-8")) + compressor.flush()
        b64_pako = base64.urlsafe_b64encode(deflated).decode("utf-8").replace("=", "")
        pako_url = f"https://mermaid.ink/img/pako:{b64_pako}"

        try:
            req = urllib.request.Request(
                pako_url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=25) as response:
                with open(png_path, "wb") as f:
                    f.write(response.read())
            print(f"  ✅ Compiled PNG via mermaid.ink: docs/images/{diagram_name}.png ({os.path.getsize(png_path):,} bytes)")
        except Exception as e:
            print(f"  ⚠️ mermaid.ink PNG compile failed: {e}")

        svg_url = f"https://mermaid.ink/svg/pako:{b64_pako}"
        try:
            req = urllib.request.Request(
                svg_url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=25) as response:
                with open(svg_path, "wb") as f:
                    f.write(response.read())
            print(f"  ✅ Compiled SVG via mermaid.ink: docs/images/{diagram_name}.svg ({os.path.getsize(svg_path):,} bytes)")
        except Exception as e:
            print(f"  ⚠️ mermaid.ink SVG compile failed: {e}")


def main():
    print("=" * 65)
    print("🏗️  Schwarz Research Intelligence - DB Schema Diagram Generator")
    print("=" * 65)

    render_to_file("db_schema_overview", DB_SCHEMA_OVERVIEW_MERMAID)
    render_to_file("db_schema_detailed", DB_SCHEMA_DETAILED_MERMAID)

    print("\n" + "=" * 65)
    print("🎉 All database schema diagrams successfully generated!")
    print(f"📁 Images location: {IMAGES_DIR}")
    print(f"📁 Sources location: {DIAGRAMS_DIR}")
    print("=" * 65)


if __name__ == "__main__":
    main()
