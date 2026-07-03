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
    name="Research Intelligence - Pluggable OCR Providers",
    show=False,
    filename=output_path,
    direction="LR",
    graph_attr=graph_attr
):
    caller = Celery("Celery Task\nrun_ocr_conversion")

    with Cluster("OCR Abstraction Layer (Pods)", graph_attr=pod_attr):
        factory = Python("OCRProviderFactory\n(factory.py)")
        interface = Python("BaseOCRProvider\n(base.py)")

    with Cluster("Concrete Drivers", graph_attr=pod_attr):
        docling_driver = Python("DoclingOCRProvider\n(docling_provider.py)")
        mistral_driver = Python("MistralOCRProvider\n(mistral_provider.py)")
        pypdf_driver = Python("PyPDFOCRProvider\n(pypdf_provider.py)")

    with Cluster("Processing Backends", graph_attr={**pod_attr, "bgcolor": "#f2f2f2", "color": "#777777"}):
        docling_service = Server("Docling Service\n(Local Docker / CPU)")
        mistral_api = Cloud("Mistral OCR API\n(Cloud Fallback)")
        pypdf_local = Server("PyPDF Engine\n(In-Process)")

    # Routing Paths
    caller >> Edge(label="Get Provider", color="#0055ff", style="solid") >> factory
    factory >> Edge(label="Implements", color="#0066cc", style="dashed") >> interface
    
    interface >> Edge(color="#0066cc") >> docling_driver
    interface >> Edge(color="#0066cc") >> mistral_driver
    interface >> Edge(color="#0066cc") >> pypdf_driver

    docling_driver >> Edge(label="gRPC / HTTP", color="#33cc33", style="bold") >> docling_service
    mistral_driver >> Edge(label="HTTPS (Mistral)", color="#ff9900", style="bold") >> mistral_api
    pypdf_driver >> Edge(label="Direct Call", color="#cc0000", style="bold") >> pypdf_local
