"""
Celery Tasks & Public Interfaces for PipelineRun & ResearchAgentProcess Orchestration.

Exposes Celery tasks (@shared_task) and execution functions backed by
PipelineRunner (primary) and ResearchAgentRunner (compatibility).
"""

import logging
from celery import shared_task
from research_intelligence.utils.mailer import send_mailgun_message
from .runner import PipelineRunner, ResearchAgentRunner

logger = logging.getLogger(__name__)


def notify_pipeline_orchestrator_tick(pipeline_run_id_or_obj):
    """
    Called whenever a ComponentRun finishes to advance execution of the PipelineRun
    and any attached ResearchAgentProcesses.
    """
    return PipelineRunner.handle_component_completion(pipeline_run_id_or_obj)


def tick_pipeline_run(pipeline_run_id: str) -> dict:
    """
    Executes a single state transition tick for a PipelineRun.
    Delegates to PipelineRunner.tick().
    """
    return PipelineRunner.tick(pipeline_run_id)


def tick_agent_process(process_id: str) -> dict:
    """
    Executes a single state transition tick for a ResearchAgentProcess.
    Delegates to ResearchAgentRunner.tick().
    """
    return ResearchAgentRunner.tick(process_id)


def _send_agent_notification(agent_process_or_pipeline_run):
    """
    Sends an email notification with formatted metrics when a run completes or fails.
    Delegates to PipelineRunner.send_completion_notification().
    """
    return PipelineRunner.send_completion_notification(agent_process_or_pipeline_run)


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True, max_retries=2, default_retry_delay=5)
def run_pipeline_tick(self, pipeline_run_id: str):
    """
    Celery task that executes a single state transition tick for a PipelineRun.
    """
    from django.db import close_old_connections
    close_old_connections()
    return PipelineRunner.tick(pipeline_run_id)


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True, max_retries=2, default_retry_delay=5)
def run_agent_process_tick(self, process_id: str):
    """
    Celery task that executes a single state transition tick for a ResearchAgentProcess.
    """
    from django.db import close_old_connections
    close_old_connections()
    return ResearchAgentRunner.tick(process_id)
