import time
from celery import shared_task


@shared_task(name="research_intelligence.tasks.auxiliary.health_ping_task", time_limit=10)
def health_ping_task(payload: str = "ping") -> dict:
    """
    Lightweight health check task to verify Celery task dispatch,
    worker pickup, and Celery result backend connectivity.
    """
    return {
        "status": "pong",
        "payload": payload,
        "timestamp": time.time(),
    }
