import logging
import uuid
import django.db
from celery import shared_task

from research_intelligence.models import PaperChatMessage
from .engine import PaperChatEngine

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="research_intelligence.tasks.chat.execute_paper_chat_task",
    max_retries=3,
    default_retry_delay=5,
)
def execute_paper_chat_task(self, message_id: str):
    """
    Celery background worker task for asynchronous LLM Paper Chat reasoning.
    Closes stale DB connections on worker thread entry and executes LLM generation.
    """
    django.db.close_old_connections()
    logger.info(f"🤖 [CELERY PAPER CHAT TASK] Starting generation for message '{message_id}' (Task: {self.request.id})")

    try:
        msg_uuid = uuid.UUID(message_id)
        message = PaperChatMessage.objects.select_related(
            'session',
            'session__paper',
            'session__workspace',
            'session__user'
        ).get(id=msg_uuid)
    except (ValueError, PaperChatMessage.DoesNotExist) as e:
        logger.error(f"PaperChatMessage '{message_id}' not found: {e}")
        return {"status": "failed", "error": f"Message '{message_id}' not found"}

    message.celery_task_id = self.request.id
    message.save(update_fields=['celery_task_id'])

    result = PaperChatEngine().execute(message)
    django.db.close_old_connections()
    return result
