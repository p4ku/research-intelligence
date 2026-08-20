"""
Celery Task & Public Interface for Research Agent Process Orchestration.

Exposes Celery tasks (@shared_task) and backwards-compatible procedural functions
backed by the ResearchAgentRunner execution engine.
"""

import logging
from celery import shared_task
from research_intelligence.utils.mailer import send_mailgun_message
from .runner import ResearchAgentRunner

logger = logging.getLogger(__name__)


def notify_pipeline_orchestrator_tick(pipeline_run_id_or_obj):
    """
    Called whenever a ComponentRun finishes to trigger the autonomous state machine
    for any running ResearchAgentProcesses attached to this PipelineRun.
    """
    return ResearchAgentRunner.handle_component_completion(pipeline_run_id_or_obj)


def tick_agent_process(process_id: str) -> dict:
    """
    Executes a single state transition tick for a ResearchAgentProcess.
    Delegates to ResearchAgentRunner.tick().
    """
    return ResearchAgentRunner.tick(process_id)


def _send_agent_notification(agent_process):
    """
    Sends an email notification with formatted metrics when an agent process completes or fails.
    Delegates to ResearchAgentRunner.send_completion_notification().
    """
    return ResearchAgentRunner.send_completion_notification(agent_process)


@shared_task(bind=True)
def run_agent_process_tick(self, process_id: str):
    """
    Celery task that executes a single state transition tick for a ResearchAgentProcess.
    """
    from django.db import close_old_connections
    close_old_connections()
    return ResearchAgentRunner.tick(process_id)
