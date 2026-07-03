from celery import shared_task

@shared_task
def run_hypothesis_evaluation(workspace_id):
    return True
