import os
from diagrams import Diagram, Cluster, Edge
from diagrams.programming.language import Python
from diagrams.onprem.queue import Celery
from diagrams.generic.compute import Cloud
from diagrams.onprem.compute import Server

output_dir = os.path.join(os.path.dirname(__file__), "..", "images")
os.makedirs(output_dir, exist_ok=True)

graph_attr = {
    "fontSize": "16",
    "bgcolor": "transparent",
}

output_path = os.path.join(output_dir, "ocr_providers")

pod_attr = {
    "bgcolor": "#e6f2ff",
    "color": "#0066cc",
    "style": "rounded,bold",
}

with Diagram(
    name="Schwarz Research Intelligence - Pluggable OCR Engines",
    show=False,
    filename=output_path,
    direction="LR",
    graph_attr=graph_attr
):
    caller = Celery("Celery Step 3 Task\nexecute_ocr_job")

    with Cluster("OCR Abstraction Layer (Factory)", graph_attr=pod_attr):
        factory = Python("OCRProviderFactory\n(factory.py)")
        interface = Python("BaseOCRProvider\n(base.py)")

    with Cluster("Concrete Drivers", graph_attr=pod_attr):
        gemini_driver = Python("GeminiOCRProvider\n(gemini_provider.py)")
        mistral_driver = Python("MistralOCRProvider\n(mistral_provider.py)")
        pypdf_driver = Python("PyPDFOCRProvider\n(pypdf_provider.py)")

    with Cluster("Processing Backends", graph_attr={**pod_attr, "bgcolor": "#f2f2f2", "color": "#777777"}):
        gemini_vision = Cloud("Google Gemini Vision\n(Multimodal API)")
        mistral_api = Cloud("Mistral OCR API\n(Cloud Fallback)")
        pypdf_local = Server("PyPDF Engine\n(In-Process Baseline)")

    # Routing Paths
    caller >> Edge(label="Get OCR Engine", color="#0055ff", style="solid") >> factory
    factory >> Edge(label="Implements", color="#0066cc", style="dashed") >> interface
    
    interface >> Edge(color="#0066cc") >> gemini_driver
    interface >> Edge(color="#0066cc") >> mistral_driver
    interface >> Edge(color="#0066cc") >> pypdf_driver

    gemini_driver >> Edge(label="HTTPS (Vertex/Google)", color="#33cc33", style="bold") >> gemini_vision
    mistral_driver >> Edge(label="HTTPS (Mistral)", color="#ff9900", style="bold") >> mistral_api
    pypdf_driver >> Edge(label="In-Process Call", color="#cc0000", style="bold") >> pypdf_local
