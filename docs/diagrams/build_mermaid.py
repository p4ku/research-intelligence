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
        usr[Research Scientists]
    end
    style Users fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Ingress ["Nginx Ingress Pod"]
        nginx[Nginx Ingress Proxy]
    end
    style Ingress fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Frontend ["Frontend Dashboard Pod"]
        frontend[Next.js SPA / Dashboard]
    end
    style Frontend fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Backend ["Backend API Pod"]
        api[Django REST API]
    end
    style Backend fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph DataState ["Message Broker & Cache Pod"]
        broker[(Redis <br> Broker & Cache)]
    end
    style DataState fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Workers ["Celery Pipeline Workers Pod"]
        beat[Celery Beat <br> Cron]
        w1[Celery Pipeline Workers]
    end
    style Workers fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Database ["Database Pod"]
        db[(PostgreSQL <br> pgvector + App DB)]
    end
    style Database fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    usr ==>|HTTPS / WSS| nginx
    nginx --> frontend
    nginx --> api
    frontend ==>|REST / RAG Query| api
    api -.->|Task Push| broker
    beat -.->|Schedules| broker
    broker ==>|Task Pull| w1
    w1 ==>|DB Write| db
    api ==>|SQL / pgvector| db
    w1 -.->|Task Status| broker
    api -.->|Cache / Session| broker

    %% Link styles for custom colored arrows
    linkStyle 0 stroke:#0055ff,stroke-width:3px;
    linkStyle 1 stroke:#0055ff,stroke-width:2px;
    linkStyle 2 stroke:#0055ff,stroke-width:2px;
    linkStyle 3 stroke:#0088cc,stroke-width:3px;
    linkStyle 4 stroke:#8c1aff,stroke-width:2px;
    linkStyle 5 stroke:#8c1aff,stroke-width:2px;
    linkStyle 6 stroke:#8c1aff,stroke-width:3px;
    linkStyle 7 stroke:#cc0000,stroke-width:3px;
    linkStyle 8 stroke:#cc0000,stroke-width:3px;
    linkStyle 9 stroke:#e65c00,stroke-width:2px;
    linkStyle 10 stroke:#e65c00,stroke-width:2px;
"""

# 2. Ingestion Pipeline Stages Diagram in Mermaid with Pod styling
pipeline_mermaid = """graph TB
    subgraph P1 ["Ingestion Node"]
        scrapers[1. Scrapers / Search <br> arXiv, OpenAlex, Lens.org]
    end
    style P1 fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph P2 ["Converter Node"]
        ocr[2. OCR / PDF-to-MD <br> Docling / Mistral OCR]
    end
    style P2 fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph P3 ["Evaluation Node"]
        screening[3. Screening <br> Two-Stage Abstract & Full]
    end
    style P3 fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph P4 ["Data Extraction Node"]
        extraction[4. Extraction <br> Claims, Parameters & TRL]
    end
    style P4 fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph P5 ["Intelligence Node"]
        research_intel[5. Research Intelligence <br> Hypothesis & Insights]
    end
    style P5 fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph KB ["Knowledge Base Pod"]
        kb[(PostgreSQL pgvector <br> RAG + Graph)]
    end
    style KB fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph UI ["User Interface"]
        user[Research Insights Dashboard]
    end
    style UI fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    scrapers ==>|PDF File| ocr
    ocr ==>|Markdown Text| screening
    screening ==>|Passed Papers| extraction
    extraction ==>|Structured JSON| research_intel

    extraction -.->|Save Claims| kb
    research_intel ==>|Read / Write Graph| kb
    kb ==>|Serve UI| user

    linkStyle 0 stroke:#0055ff,stroke-width:3px;
    linkStyle 1 stroke:#0055ff,stroke-width:3px;
    linkStyle 2 stroke:#0055ff,stroke-width:3px;
    linkStyle 3 stroke:#0055ff,stroke-width:3px;
    linkStyle 4 stroke:#cc0000,stroke-width:2px;
    linkStyle 5 stroke:#cc0000,stroke-width:3px;
    linkStyle 6 stroke:#0088cc,stroke-width:3px;
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
        openai[OpenAILLMProvider <br> openai.py - Future]
    end
    style Drivers fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph SaaS ["External API Endpoints"]
        gemini[(Google Gemini API)]
        or_api[(OpenRouter API)]
        oa_api[(OpenAI API)]
    end
    style SaaS fill:#f2f2f2,stroke:#777777,stroke-width:2px

    caller ==>|Get Provider| factory
    factory -.->|Implements| interface
    interface ==> google
    interface ==> openrouter
    interface -.->|Future| openai

    google ==>|HTTPS| gemini
    openrouter ==>|HTTPS| or_api
    openai -.->|HTTPS| oa_api

    linkStyle 0 stroke:#0055ff,stroke-width:3px;
    linkStyle 1 stroke:#0066cc,stroke-width:2px;
    linkStyle 2 stroke:#0066cc,stroke-width:3px;
    linkStyle 3 stroke:#0066cc,stroke-width:3px;
    linkStyle 4 stroke:#0066cc,stroke-width:2px,stroke-dasharray: 5 5;
    linkStyle 5 stroke:#33cc33,stroke-width:3px;
    linkStyle 6 stroke:#ff9900,stroke-width:3px;
    linkStyle 7 stroke:#9933ff,stroke-width:2px,stroke-dasharray: 5 5;
"""

# 4. OCR Providers Diagram in Mermaid with Blue Pod styling
ocr_providers_mermaid = """graph LR
    subgraph Caller ["App Layer"]
        caller[Celery Task <br> run_ocr_conversion]
    end
    style Caller fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Interface ["OCR Abstraction Layer"]
        factory[OCRProviderFactory <br> factory.py]
        interface[BaseOCRProvider <br> base.py]
    end
    style Interface fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Drivers ["Concrete Drivers"]
        docling[DoclingOCRProvider <br> docling_provider.py]
        mistral[MistralOCRProvider <br> mistral_provider.py]
        pypdf[PyPDFOCRProvider <br> pypdf_provider.py]
    end
    style Drivers fill:#e6f2ff,stroke:#0066cc,stroke-width:2px

    subgraph Backend ["Processing Backends"]
        docling_svc[Docling Service <br> Local Docker / CPU]
        mistral_api[(Mistral OCR API <br> Cloud Fallback)]
        pypdf_eng[PyPDF Engine <br> In-Process]
    end
    style Backend fill:#f2f2f2,stroke:#777777,stroke-width:2px

    caller ==>|Get Provider| factory
    factory -.->|Implements| interface
    interface ==> docling
    interface ==> mistral
    interface ==> pypdf

    docling ==>|gRPC / HTTP| docling_svc
    mistral ==>|HTTPS| mistral_api
    pypdf ==>|Direct Call| pypdf_eng

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
