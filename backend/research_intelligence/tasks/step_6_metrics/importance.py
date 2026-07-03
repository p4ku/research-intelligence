from celery import shared_task

@shared_task
def calculate_paper_importance(paper_id):
    return True
