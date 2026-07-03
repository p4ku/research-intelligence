from celery import shared_task

@shared_task
def generate_narrative_report_with_refinement(workspace_id):
    return True
