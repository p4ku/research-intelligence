import os
from diagrams import Diagram, Cluster, Edge
from diagrams.onprem.queue import Celery
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.client import Users
from diagrams.generic.compute import Cloud

# Determine the directory where this script is located
output_dir = os.path.join(os.path.dirname(__file__), "..", "images")
os.makedirs(output_dir, exist_ok=True)

graph_attr = {
    "fontSize": "16",
    "bgcolor": "transparent",
}

output_path = os.path.join(output_dir, "pipeline_stages")

with Diagram(
    name="Schwarz Research Intelligence - 8-Stage SLR DAG Pipeline",
    show=False,
    filename=output_path,
    direction="TB",
    graph_attr=graph_attr
):
    search = Celery("1. Search & Deduplication\n(arXiv, OpenAlex, Lens.org)")
    abstract_screen = Celery("2. Abstract Screening\n(AI Triage via Gemini 3.7)")
    download = Celery("3. Parallel PDF Download\n(DocumentRegistry SHA-256 Cache)")
    ocr = Celery("4. Layout OCR\n(PyPDF / Mistral / Gemini OCR)")
    full_text_screen = Celery("5. Full-Text Screening\n(Multimodal PDF Analysis)")
    extraction = Celery("6. Parameter Extraction\n(JSON Schemas & Confidence)")
    signal_score = Celery("7. Composite Signal Score\n(AST Sandboxed Python Formula)")
    reporting = Celery("8. Executive Reporting\n(Briefings & Mailgun Digests)")
    
    kb = PostgreSQL("Workspace DB & Storage\n(Postgres + Document Registry)")
    user = Users("Research Insights & Scorecard")

    # Sequential pipeline flow
    search >> Edge(label="Candidate Papers", color="darkblue") >> abstract_screen
    abstract_screen >> Edge(label="Abstract Passed", color="darkblue") >> download
    download >> Edge(label="PDF Files", color="darkblue") >> ocr
    ocr >> Edge(label="PDF Binary / MD Text", color="darkblue") >> full_text_screen
    full_text_screen >> Edge(label="Accepted Papers", color="darkblue") >> extraction
    extraction >> Edge(label="Extracted KPIs", color="darkblue") >> signal_score
    signal_score >> Edge(label="Ranked Papers", color="darkblue") >> reporting
    
    # Storage connections
    extraction >> Edge(label="Save Extractions", color="darkred", style="dashed") >> kb
    signal_score >> Edge(label="Save Signal Scores", color="darkred", style="dashed") >> kb
    reporting >> Edge(label="Serve Scorecard", color="darkgreen") >> user
    kb >> Edge(label="Data Store", color="darkgreen") >> user
