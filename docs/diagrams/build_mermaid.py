import base64
import os
import urllib.request
import urllib.parse

# Define the output directory
docs_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
images_dir = os.path.join(docs_dir, "images")
diagrams_dir = os.path.join(docs_dir, "diagrams")
os.makedirs(images_dir, exist_ok=True)
os.makedirs(diagrams_dir, exist_ok=True)

# 1. High-Level System Architecture Diagram in Mermaid with Blue Pod styling
architecture_mermaid = """graph TB
    subgraph Users ["Users Pod"]
        usr[Research Scientists & MCP Clients]
    end
    style Users fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Ingress ["Ingress & Gateway Pod"]
        nginx[Reverse Proxy & Cloud Foundry Router]
    end
    style Ingress fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Frontend ["Frontend Dashboard Pod"]
        frontend[Next.js Dashboard / SPA]
    end
    style Frontend fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Backend ["Backend API & MCP Server Pods"]
        api[Django REST API & Admin]
        mcp[FastMCP SSE Server]
    end
    style Backend fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph DataState ["Message Broker & Cache Pod"]
        broker[(Redis <br> Broker & Cache)]
    end
    style DataState fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Workers ["Celery Pipeline Workers Pod"]
        beat[Celery Beat <br> Cron Schedules]
        w1[Celery Pipeline Workers <br> Distributed Steps 1-8]
    end
    style Workers fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Database ["Database Pod"]
        db[(PostgreSQL + pgvector <br> Workspace & Document DB)]
    end
    style Database fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Storage ["Object Storage Pod"]
        minio[(S3 / MinIO Storage <br> PDFs & Layout Markdown)]
    end
    style Storage fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    usr ==>|HTTPS / WSS| nginx
    nginx --> frontend
    nginx --> api
    nginx --> mcp
    frontend ==>|REST Query| api
    mcp ==>|Tool Execution| api
    api -.->|Task Push| broker
    beat -.->|Schedules| broker
    broker ==>|Task Pull| w1
    w1 ==>|DB State & Locks| db
    api ==>|SQL / Relational| db
    w1 -.->|Task Status| broker
    api -.->|Cache / Session| broker
    api ==>|Manage Storage| minio
    w1 ==>|Read / Write Documents| minio

    %% Link styles for custom colored arrows
    linkStyle 0 stroke:#0055ff,stroke-width:3px;
    linkStyle 1 stroke:#0055ff,stroke-width:2px;
    linkStyle 2 stroke:#0055ff,stroke-width:2px;
    linkStyle 3 stroke:#0055ff,stroke-width:2px;
    linkStyle 4 stroke:#0088cc,stroke-width:3px;
    linkStyle 5 stroke:#0088cc,stroke-width:3px;
    linkStyle 6 stroke:#8c1aff,stroke-width:2px;
    linkStyle 7 stroke:#8c1aff,stroke-width:2px;
    linkStyle 8 stroke:#8c1aff,stroke-width:3px;
    linkStyle 9 stroke:#cc0000,stroke-width:3px;
    linkStyle 10 stroke:#cc0000,stroke-width:3px;
    linkStyle 11 stroke:#e65c00,stroke-width:2px;
    linkStyle 12 stroke:#e65c00,stroke-width:2px;
    linkStyle 13 stroke:#00aa55,stroke-width:3px;
    linkStyle 14 stroke:#00aa55,stroke-width:3px;
"""

# 2. Ingestion Pipeline Stages Diagram in Mermaid with Pod styling
pipeline_mermaid = """graph TB
    subgraph P1 ["Stage 1: Ingestion Node"]
        search[1. Search & Deduplication <br> arXiv, OpenAlex, Lens.org]
    end
    style P1 fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph P2 ["Stage 2: AI Triage Node"]
        abstract_screen[2. Abstract Screening <br> Fast Title & Abstract Evaluation via Gemini 3.7 Flash]
    end
    style P2 fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph P3 ["Stage 3: Fetch Node"]
        download[3. Parallel PDF Download <br> Content-Addressable DocumentRegistry SHA-256 Cache]
    end
    style P3 fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph P4 ["Stage 4: Converter Node (Optional)"]
        ocr[4. Layout OCR Parsing <br> PyPDF / Mistral OCR / Gemini Vision - Skipped if None]
    end
    style P4 fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph P5 ["Stage 5: Deep Evaluation Node"]
        full_text_screen[5. Full-Text Screening <br> Deep Multimodal Native PDF Analysis via Gemini 3.7 Flash]
    end
    style P5 fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph P6 ["Stage 6: Parameter Extraction Node"]
        extraction[6. Parameter & Claim Extraction <br> Dynamic JSON Schemas, Evidence Quotes & Confidence]
    end
    style P6 fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph P7 ["Stage 7: Ranking Node"]
        signal_score[7. Composite Signal Score <br> AST-Secured Sandboxed Custom Python Math Formula]
    end
    style P7 fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph P8 ["Stage 8: Reporting Node"]
        reporting[8. Executive Narrative & Alerts <br> Briefing Synthesis & Transactional Mailgun Alerts]
    end
    style P8 fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph KB ["Persistent Storage"]
        kb[(PostgreSQL + Storage <br> Workspace DB & Document Registry)]
    end
    style KB fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph UI ["User Interface"]
        user[Research Insights & Technology Scorecard]
    end
    style UI fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    search ==>|Candidate Papers| abstract_screen
    abstract_screen ==>|Abstract Passed| download
    download ==>|PDF Files| ocr
    ocr ==>|Binary PDF / OCR Text| full_text_screen
    full_text_screen ==>|Accepted Papers| extraction
    extraction ==>|Extracted Parameters| signal_score
    signal_score ==>|Ranked Scorecards| reporting

    extraction -.->|Save Extractions| kb
    signal_score -.->|Save Signal Scores| kb
    reporting ==>|Deliver Scorecard| user
    kb ==>|Serve Queries| user

    linkStyle 0 stroke:#0055ff,stroke-width:3px;
    linkStyle 1 stroke:#0055ff,stroke-width:3px;
    linkStyle 2 stroke:#0055ff,stroke-width:3px;
    linkStyle 3 stroke:#0055ff,stroke-width:3px;
    linkStyle 4 stroke:#0055ff,stroke-width:3px;
    linkStyle 5 stroke:#0055ff,stroke-width:3px;
    linkStyle 6 stroke:#0055ff,stroke-width:3px;
    linkStyle 7 stroke:#cc0000,stroke-width:2px;
    linkStyle 8 stroke:#cc0000,stroke-width:2px;
    linkStyle 9 stroke:#00aa55,stroke-width:3px;
    linkStyle 10 stroke:#0088cc,stroke-width:3px;
"""

# 3. LLM Providers Diagram in Mermaid with Blue Pod styling
llm_providers_mermaid = """graph LR
    subgraph Caller ["App Layer"]
        caller[Django App / Celery <br> Research Logic]
    end
    style Caller fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Interface ["LLM Abstraction Layer"]
        factory[LLMProviderFactory <br> factory.py]
        interface[BaseLLMProvider <br> base.py]
    end
    style Interface fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Drivers ["Concrete Drivers"]
        google[GoogleLLMProvider <br> google.py]
        openrouter[OpenRouterLLMProvider <br> openrouter.py]
    end
    style Drivers fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph SaaS ["External API Endpoints"]
        gemini[(Google Vertex AI / Gemini 3.7 Flash)]
        or_api[(OpenRouter API Gateway)]
    end
    style SaaS fill:#f2f2f2,stroke:#777777,stroke-width:2px

    caller ==>|Get Provider| factory
    factory -.->|Implements| interface
    interface ==> google
    interface ==> openrouter

    google ==>|HTTPS / Vertex| gemini
    openrouter ==>|HTTPS| or_api

    linkStyle 0 stroke:#0055ff,stroke-width:3px;
    linkStyle 1 stroke:#0066cc,stroke-width:2px;
    linkStyle 2 stroke:#0066cc,stroke-width:3px;
    linkStyle 3 stroke:#0066cc,stroke-width:3px;
    linkStyle 4 stroke:#33cc33,stroke-width:3px;
    linkStyle 5 stroke:#ff9900,stroke-width:3px;
"""

# 4. OCR Providers Diagram in Mermaid with Blue Pod styling
ocr_providers_mermaid = """graph LR
    subgraph Caller ["App Layer"]
        caller[Celery Step 4 Task <br> execute_ocr_job]
    end
    style Caller fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Interface ["OCR Abstraction Layer"]
        factory[OCRProviderFactory <br> factory.py]
        interface[BaseOCRProvider <br> base.py]
    end
    style Interface fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Drivers ["Concrete Drivers"]
        gemini_ocr[GeminiOCRProvider <br> gemini_provider.py]
        mistral[MistralOCRProvider <br> mistral_provider.py]
        pypdf[PyPDFOCRProvider <br> pypdf_provider.py]
    end
    style Drivers fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Backend ["Processing Backends"]
        gemini_api[(Google Gemini Vision <br> Multimodal API)]
        mistral_api[(Mistral OCR API <br> Cloud Engine)]
        pypdf_eng[PyPDF Engine <br> In-Process Baseline]
    end
    style Backend fill:#f2f2f2,stroke:#777777,stroke-width:2px

    caller ==>|Get Provider| factory
    factory -.->|Implements| interface
    interface ==> gemini_ocr
    interface ==> mistral
    interface ==> pypdf

    gemini_ocr ==>|HTTPS / Vertex| gemini_api
    mistral ==>|HTTPS| mistral_api
    pypdf ==>|In-Process Call| pypdf_eng

    linkStyle 0 stroke:#0055ff,stroke-width:3px;
    linkStyle 1 stroke:#0066cc,stroke-width:2px;
    linkStyle 2 stroke:#0066cc,stroke-width:3px;
    linkStyle 3 stroke:#0066cc,stroke-width:3px;
    linkStyle 4 stroke:#0066cc,stroke-width:3px;
    linkStyle 5 stroke:#33cc33,stroke-width:3px;
    linkStyle 6 stroke:#ff9900,stroke-width:3px;
    linkStyle 7 stroke:#cc0000,stroke-width:3px;
"""

diagrams = {
    "architecture": architecture_mermaid,
    "pipeline_stages": pipeline_mermaid,
    "llm_providers": llm_providers_mermaid,
    "ocr_providers": ocr_providers_mermaid
}

def render_diagram(name, mermaid_code):
    print(f"Rendering diagram: {name}...")
    
    # Save the raw .mmd file
    mmd_path = os.path.join(diagrams_dir, f"{name}.mmd")
    with open(mmd_path, "w") as f:
        f.write(mermaid_code)
    print(f"  Saved Mermaid source to: docs/diagrams/{name}.mmd")

    # Encode the Mermaid diagram to Base64
    encoded_str = base64.b64encode(mermaid_code.encode("utf-8")).decode("utf-8")
    
    # The URL for mermaid.ink
    url = f"https://mermaid.ink/img/{encoded_str}"
    
    # Define target image path
    image_path = os.path.join(images_dir, f"{name}.png")
    
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            with open(image_path, "wb") as f:
                f.write(response.read())
        print(f"  Successfully compiled and saved image to: docs/images/{name}.png")
    except Exception as e:
        print(f"  ❌ Error compiling diagram via mermaid.ink: {e}")
        print("  Please make sure you are connected to the internet.")

if __name__ == "__main__":
    for name, code in diagrams.items():
        render_diagram(name, code)
