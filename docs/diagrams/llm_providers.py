import os
from diagrams import Diagram, Cluster, Edge
from diagrams.programming.language import Python
from diagrams.programming.framework import Django
from diagrams.generic.compute import Cloud
from diagrams.generic.blank import Blank

output_dir = os.path.join(os.path.dirname(__file__), "..", "images")
os.makedirs(output_dir, exist_ok=True)

graph_attr = {
    "fontSize": "16",
    "bgcolor": "transparent",
}

output_path = os.path.join(output_dir, "llm_providers")

pod_attr = {
    "bgcolor": "#e6f2ff",
    "color": "#0066cc",
    "style": "rounded,bold",
}

with Diagram(
    name="Research Intelligence - Pluggable LLM Providers",
    show=False,
    filename=output_path,
    direction="LR",
    graph_attr=graph_attr
):
    caller = Django("Django App / Celery\n(Research Logic)")

    with Cluster("LLM Abstraction Layer (Pods)", graph_attr=pod_attr):
        factory = Python("LLMProviderFactory\n(factory.py)")
        interface = Python("BaseLLMProvider\n(base.py)")

    with Cluster("Concrete Drivers", graph_attr=pod_attr):
        google_driver = Python("GoogleLLMProvider\n(google.py)")
        openrouter_driver = Python("OpenRouterLLMProvider\n(openrouter.py)")
        openai_driver = Python("OpenAILLMProvider\n(openai.py - Future)")

    with Cluster("External API Endpoints (SaaS)", graph_attr={**pod_attr, "bgcolor": "#f2f2f2", "color": "#777777"}):
        google_gemini = Cloud("Google Gemini API")
        openrouter_api = Cloud("OpenRouter API")
        openai_api = Cloud("OpenAI API")

    # Routing Paths
    caller >> Edge(label="Get Provider", color="#0055ff", style="solid") >> factory
    factory >> Edge(label="Implements", color="#0066cc", style="dashed") >> interface
    
    interface >> Edge(color="#0066cc") >> google_driver
    interface >> Edge(color="#0066cc") >> openrouter_driver
    interface >> Edge(color="#0066cc", style="dotted") >> openai_driver

    google_driver >> Edge(label="HTTPS (Vertex/Google)", color="#33cc33", style="bold") >> google_gemini
    openrouter_driver >> Edge(label="HTTPS (OpenRouter)", color="#ff9900", style="bold") >> openrouter_api
    openai_driver >> Edge(label="HTTPS (OpenAI)", color="#9933ff", style="dotted") >> openai_api
