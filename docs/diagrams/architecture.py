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
    name="Research Intelligence - System Architecture (K8s Pods & Personas)",
    show=False,
    filename=output_path,
    direction="TB",
    graph_attr=graph_attr
):
    with Cluster("User Personas & Clients", graph_attr=pod_attr):
        manager = Users("Manager / Researcher\n(Frontend Web User)")
        power_user = Users("Power User / AI Agent\n(MCP Client: Claude / Cursor)")
        admin_user = Users("Administrator / Lead\n(Django Admin User)")

    with Cluster("Ingress & Gateway Pod", graph_attr=pod_attr):
        nginx = Nginx("Reverse Proxy / Gateway Router\n(Port 80/443)")

    with Cluster("Frontend Dashboard Pod", graph_attr=pod_attr):
        frontend = React("Next.js Dashboard / SPA\n(Web UI, Scorecards, Chat)")

    with Cluster("Backend API & MCP Server Pods", graph_attr=pod_attr):
        backend_api = Django("Django REST API\n(/api/ - Auth, Papers, Runs)")
        django_admin = Django("Django Admin Portal\n(/admin/ - RBAC, Quotas)")
        mcp_server = Django("FastMCP SSE Server\n(Port 8001 / SSE Tools)")

    with Cluster("Message Broker & Cache Pod", graph_attr=pod_attr):
        task_broker = Redis("Redis In-Memory\n(Broker & Cache)")

    with Cluster("Celery Pipeline Workers Pod", graph_attr=pod_attr):
        celery_beat = Celery("Celery Beat (Cron / Watchdog)")
        celery_workers = Celery("Celery Pipeline Workers\n(8-Stage SLR DAG)")

    with Cluster("Database Pod (Persistent State)", graph_attr=pod_attr):
        db = PostgreSQL("PostgreSQL + pgvector\n(Workspaces, Papers, Extractions)")

    with Cluster("Object Storage Pod", graph_attr=pod_attr):
        file_storage = S3("MinIO / S3 Storage\n(PDFs, Markdown, Reports)")

    # Routing Paths with custom edges
    manager >> Edge(label="HTTPS / Browser", color="#0055ff", style="bold") >> nginx
    power_user >> Edge(label="HTTPS / SSE MCP", color="#0055ff", style="bold") >> nginx
    admin_user >> Edge(label="HTTPS / Admin Portal", color="#0055ff", style="bold") >> nginx

    nginx >> Edge(color="#0055ff", style="solid") >> frontend
    nginx >> Edge(color="#0055ff", style="solid") >> backend_api
    nginx >> Edge(color="#0055ff", style="solid") >> django_admin
    nginx >> Edge(color="#0055ff", style="solid") >> mcp_server

    frontend >> Edge(label="REST / JWT", color="#0088cc", style="bold") >> backend_api
    mcp_server >> Edge(label="Tool Exec / Tasks", color="#0088cc", style="bold") >> backend_api
    django_admin >> Edge(label="Admin ORM", color="#cc0000", style="solid") >> db

    backend_api >> Edge(label="Task Push", color="#8c1aff", style="dashed") >> task_broker
    celery_beat >> Edge(label="Schedules", color="#8c1aff", style="dashed") >> task_broker

    task_broker >> Edge(label="Task Pull", color="#8c1aff", style="solid") >> celery_workers

    celery_workers >> Edge(label="DB State & Locks", color="#cc0000", style="solid") >> db
    backend_api >> Edge(label="SQL / pgvector", color="#cc0000", style="solid") >> db

    celery_workers >> Edge(label="Task Status", color="#e65c00", style="dotted") >> task_broker
    backend_api >> Edge(label="Cache / Session", color="#e65c00", style="dotted") >> task_broker

    backend_api >> Edge(label="Stream PDFs", color="#00aa55", style="solid") >> file_storage
    django_admin >> Edge(label="Storage Browser", color="#00aa55", style="solid") >> file_storage
    celery_workers >> Edge(label="Read/Write Docs", color="#00aa55", style="solid") >> file_storage
