# Celery task pipeline
from celery import shared_task

@shared_task
def run_workspace_ingestion_pipeline(workspace_id):
    print(f"Running pipeline for workspace {workspace_id}")
    return True
