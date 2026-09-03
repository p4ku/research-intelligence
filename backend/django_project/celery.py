import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')

app = Celery('django_project')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


import sys
import logging
from celery.signals import after_setup_logger, after_setup_task_logger


@after_setup_logger.connect
@after_setup_task_logger.connect
def setup_celery_logging_to_stdout(logger, *args, **kwargs):
    """
    Ensure Celery logs to sys.stdout instead of sys.stderr by default.
    Prevents PaaS log collectors (like Cloud Foundry / STACKIT) from falsely
    classifying standard operational INFO/DEBUG logs as ERR in red text.
    """
    for handler in getattr(logger, 'handlers', []):
        if isinstance(handler, logging.StreamHandler) and hasattr(handler, 'stream'):
            if handler.stream in (sys.stderr, sys.__stderr__):
                handler.setStream(sys.stdout)
