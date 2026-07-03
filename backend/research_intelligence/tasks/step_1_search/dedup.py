from celery import shared_task

@shared_task
def deduplicate_ingested_metadata():
    return True
