import os
from diagrams import Diagram, Cluster, Edge
from diagrams.onprem.queue import Celery
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.client import Users

# Determine the directory where this script is located
output_dir = os.path.join(os.path.dirname(__file__), "..", "images")
os.makedirs(output_dir, exist_ok=True)

graph_attr = {
    "fontSize": "16",
    "bgcolor": "transparent",
}

output_path = os.path.join(output_dir, "pipeline_stages")

with Diagram(
    name="Research Intelligence - Ingestion & Extraction Pipeline Stages",
    show=False,
    filename=output_path,
    direction="TB",
    graph_attr=graph_attr
):
    scrapers = Celery("1. Scrapers / Search\n(arXiv, OpenAlex, Lens.org)")
    ocr = Celery("2. OCR / PDF-to-MD\n(Docling / Mistral OCR)")
    screening = Celery("3. Screening\n(Two-Stage Abstract & Full)")
    extraction = Celery("4. Extraction\n(Claims, Parameters & TRL)")
    research_intel = Celery("5. Research Intelligence\n(Hypothesis & Insights)")
    
    kb = PostgreSQL("Knowledge Base\n(pgvector + RAG + Graph)")
    user = Users("Research Insights Dashboard")

    # Sequential pipeline flow
    scrapers >> Edge(label="PDF File", color="darkblue") >> ocr
    ocr >> Edge(label="Markdown Text", color="darkblue") >> screening
    screening >> Edge(label="Passed Papers", color="darkblue") >> extraction
    extraction >> Edge(label="Structured JSON", color="darkblue") >> research_intel
    
    # Storage connections
    extraction >> Edge(label="Save Claims", color="darkred", style="dashed") >> kb
    research_intel >> Edge(label="Read / Write Graph", color="darkred") >> kb
    kb >> Edge(label="Serve UI", color="darkgreen") >> user
