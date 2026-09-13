"""Minimal Celery app with the project's ack settings and one long task.

Runs inside the backend image so the Celery/kombu/redis versions are the deployed ones.
See run.sh for the full experiment; on its own:

    celery -A probe worker -c 1 --loglevel=info
    celery -A probe call probe.long_task
"""
import os
import time

from celery import Celery

app = Celery("probe", broker=os.environ.get("PROBE_BROKER_URL", "redis://redis:6379/1"))
app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_soft_shutdown_timeout=float(os.environ.get("CELERY_SOFT_SHUTDOWN_SECONDS", "3")),
    task_ignore_result=True,
)


@app.task(name="probe.long_task")
def long_task():
    for i in range(300):
        print(f"long_task tick {i}", flush=True)
        time.sleep(1)
    return "done"
