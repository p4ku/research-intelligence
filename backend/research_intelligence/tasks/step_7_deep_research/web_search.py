from celery import shared_task

@shared_task
def run_web_search_scraping(query_text):
    return True
