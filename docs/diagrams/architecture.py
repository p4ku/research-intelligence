import os
from diagrams import Diagram, Cluster, Edge
from diagrams.programming.framework import Django, React
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.inmemory import Redis
from diagrams.onprem.queue import Celery
from diagrams.onprem.network import Nginx
from diagrams.onprem.client import Users
from diagrams.aws.storage import S3

output_dir = os.path.join(os.path.dirname(__file__), "..", "images")
os.makedirs(output_dir, exist_ok=True)

graph_attr = {
    "fontSize": "16",
    "bgcolor": "transparent",
    "splines": "ortho", # Clean orthogonal lines
}

output_path = os.path.join(output_dir, "architecture")

# Sleek blue pod/node style attributes
pod_attr = {
    "bgcolor": "#e6f2ff",  # Light blue background
    "color": "#0066cc",    # Rich blue border
    "style": "rounded,bold",
}

with Diagram(
    name="Research Intelligence - System Architecture (K8s Pods / Nodes)",
    show=False,
    filename=output_path,
    direction="TB",
    graph_attr=graph_attr
):
    users = Users("Scientists / Client")

    with Cluster("Nginx Ingress Pod", graph_attr=pod_attr):
        nginx = Nginx("Nginx Ingress Proxy")

    with Cluster("Frontend Dashboard Pod", graph_attr=pod_attr):
        frontend = React("Next.js SPA / Dashboard")

    with Cluster("Backend API Pod", graph_attr=pod_attr):
        backend_api = Django("Django REST API")

    with Cluster("Message Broker & Cache Pod", graph_attr=pod_attr):
        task_broker = Redis("Redis In-Memory")

    with Cluster("Celery Pipeline Workers Pod", graph_attr=pod_attr):
        celery_beat = Celery("Celery Beat (Cron)")
        celery_workers = Celery("Celery Pipeline Workers")

    with Cluster("Database Pod (Persistent State)", graph_attr=pod_attr):
        db = PostgreSQL("PostgreSQL + pgvector")

    with Cluster("Object Storage Pod", graph_attr=pod_attr):
        file_storage = S3("MinIO (S3 Compatible)")

    # Routing Paths with custom edges (color, style, label)
    users >> Edge(label="HTTPS / WSS", color="#0055ff", style="bold") >> nginx
    
    nginx >> Edge(color="#0055ff", style="solid") >> frontend
    nginx >> Edge(color="#0055ff", style="solid") >> backend_api
    
    frontend >> Edge(label="REST / RAG Query", color="#0088cc", style="bold") >> backend_api
    
    backend_api >> Edge(label="Task Push", color="#8c1aff", style="dashed") >> task_broker
    celery_beat >> Edge(label="Schedules", color="#8c1aff", style="dashed") >> task_broker
    
    task_broker >> Edge(label="Task Pull", color="#8c1aff", style="solid") >> celery_workers
    
    celery_workers >> Edge(label="DB Write", color="#cc0000", style="solid") >> db
    backend_api >> Edge(label="SQL / pgvector", color="#cc0000", style="solid") >> db
    
    celery_workers >> Edge(label="Task Status", color="#e65c00", style="dotted") >> task_broker
    backend_api >> Edge(label="Cache / Session", color="#e65c00", style="dotted") >> task_broker

    backend_api >> Edge(label="Manage / Link", color="#00aa55", style="solid") >> file_storage
    celery_workers >> Edge(label="Read/Write Docs", color="#00aa55", style="solid") >> file_storage
