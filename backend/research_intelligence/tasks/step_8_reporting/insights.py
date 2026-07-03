from celery import shared_task

@shared_task
def compile_workspace_insights(workspace_id):
    return True
