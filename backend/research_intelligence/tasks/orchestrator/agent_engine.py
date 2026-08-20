import logging
import time
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.db import close_old_connections, transaction, connection

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    ComponentRun,
    ResearchAgentProcess,
    Scraper,
)
from research_intelligence.utils.mailer import send_mailgun_message
from .dag import build_default_slr_dag

logger = logging.getLogger(__name__)


def notify_pipeline_orchestrator_tick(pipeline_run_id_or_obj):
    """
    Called whenever a ComponentRun finishes to trigger the autonomous state machine
    for any running ResearchAgentProcesses attached to this PipelineRun.
    """
    if not pipeline_run_id_or_obj:
        return
    try:
        if isinstance(pipeline_run_id_or_obj, str):
            pipeline_run = PipelineRun.objects.get(pk=pipeline_run_id_or_obj)
        else:
            pipeline_run = pipeline_run_id_or_obj

        running_agents = list(pipeline_run.agent_processes.filter(status='running'))
        if running_agents:
            for agent_proc in running_agents:
                try:
                    run_agent_process_tick.delay(str(agent_proc.id))
                except Exception:
                    # If Celery queueing fails or in sync environment, tick directly
                    try:
                        tick_agent_process(str(agent_proc.id))
                    except Exception as sync_err:
                        logger.warning(f"Fallback tick execution failed for agent '{agent_proc.id}': {sync_err}")
        else:
            # Check if all component runs are done for this pipeline run
            pending_runs = pipeline_run.component_runs.filter(status__in=['pending', 'running'])
            if not pending_runs.exists() and pipeline_run.component_runs.filter(status='completed').exists():
                last_comp = pipeline_run.component_runs.order_by('-completed_at', '-id').first()
                if last_comp and last_comp.step_type in ['signal_score', 'extraction']:
                    pipeline_run.status = 'completed'
                    pipeline_run.current_stage = 'completed'
                    if not pipeline_run.completed_at:
                        pipeline_run.completed_at = timezone.now()
                    pipeline_run.save(update_fields=['status', 'current_stage', 'completed_at'])
    except Exception as e:
        logger.warning(f"Failed to notify orchestrator tick: {e}")


def _send_agent_notification(agent_process: ResearchAgentProcess):
    """
    Sends an email notification with formatted metrics when an agent process completes or fails.
    Notifies all workspace active subscribers and any explicit override email.
    """
    recipients = set()

    # Explicit override in config or workspace setting
    override_email = (
        agent_process.configuration_override.get("notification_email")
        or agent_process.workspace.notification_email
    )
    if override_email:
        recipients.add(override_email.strip())

    # Workspace Active Subscribers ONLY
    subscribers = agent_process.workspace.subscribers.filter(is_active=True)
    for s in subscribers:
        if s.email:
            recipients.add(s.email.strip())

    recipient_list = sorted(list(recipients))
    if not recipient_list:
        logger.info(f"📧 [NOTIFICATION] No active recipients/subscribers found for Workspace '{agent_process.workspace.name}'.")
        return

    from research_intelligence.tasks.auxiliary.email_digest import build_pipeline_run_digest_payload

    payload = build_pipeline_run_digest_payload(agent_process.pipeline_run, agent_process=agent_process)
    subject = payload["subject"]
    html_message = payload["html_content"]
    plain_message = payload["text_content"]

    for to_email in recipient_list:
        try:
            success, resp_or_err = send_mailgun_message(
                to_email=to_email,
                subject=subject,
                text=plain_message,
                html=html_message
            )
            if success:
                logger.info(f"📧 [EMAIL NOTIFICATION SENT via Mailgun] To: {to_email} | Subject: '{subject}' | Response: {resp_or_err}")
            else:
                mailgun_url = getattr(settings, 'MAILGUN_API_URL', 'https://api.eu.mailgun.net/v3')
                mailgun_domain = getattr(settings, 'MAILGUN_SENDER_DOMAIN', 'soinventive.co.uk')
                has_key = bool(getattr(settings, 'MAILGUN_API_KEY', ''))
                logger.warning(
                    f"⚠️ [MAILGUN NOTIFICATION FAILED] To: {to_email} | "
                    f"Mailgun URL: {mailgun_url} | Domain: {mailgun_domain} | "
                    f"API Key Set: {has_key} | Error: {resp_or_err}"
                )
        except Exception as mail_err:
            logger.warning(f"⚠️ [MAIL NOTIFICATION EXCEPTION] To: {to_email} | Error: {mail_err}")


def tick_agent_process(process_id: str) -> dict:
    """
    Autonomous State Machine Orchestrator logic function powered by WorkflowDAG.
    Evaluates current step of a ResearchAgentProcess and drives it sequentially to the next pipeline stage.
    Uses database row locks to prevent race conditions across parallel Celery workers.
    """
    close_old_connections()
    with transaction.atomic():
        try:
            if connection.vendor == 'postgresql':
                process = ResearchAgentProcess.objects.select_for_update().select_related('workspace', 'pipeline_run').get(pk=process_id)
            else:
                process = ResearchAgentProcess.objects.select_related('workspace', 'pipeline_run').get(pk=process_id)
        except ResearchAgentProcess.DoesNotExist:
            logger.error(f"ResearchAgentProcess '{process_id}' not found.")
            return {"success": False, "error": f"ResearchAgentProcess '{process_id}' not found."}

        # If agent is in terminal or paused state, do not advance
        if process.status in ['paused', 'aborted', 'failed', 'completed']:
            logger.info(f"Agent process '{process.id}' is in status '{process.status}'. No state transition taken.")
            return {
                "success": True,
                "status": process.status,
                "current_step": process.current_step,
                "message": f"Agent process is in status '{process.status}'."
            }

        workspace = process.workspace
        config = process.configuration_override or {}
        limit = config.get("limit", 50)
        history = list(process.step_history or [])

        # 1. State: INITIALIZED -> Initialize PipelineRun
        if process.current_step == 'initialized' or not process.pipeline_run:
            reprocess_existing = config.get("reprocess_existing", False)
            pipeline_run = PipelineRun.objects.create(
                workspace=workspace,
                status='running',
                current_stage='search',
                reprocess_existing=reprocess_existing,
                triggered_by=process.triggered_by
            )
            process.pipeline_run = pipeline_run
            process.status = 'running'
            process.current_step = 'search'

            history.append({
                "step": "search",
                "event": "started",
                "pipeline_run_id": str(pipeline_run.id),
                "timestamp": timezone.now().isoformat()
            })
            process.step_history = history
            process.save(update_fields=['pipeline_run', 'status', 'current_step', 'step_history', 'updated_at'])

        pipeline_run = process.pipeline_run

        # Execute and dispatch via Workflow DAG
        dag = build_default_slr_dag(workspace=workspace, config=config)
        return dag.evaluate_and_dispatch(
            pipeline_run=pipeline_run,
            agent_process=process,
            config=config,
            limit=limit
        )


@shared_task(bind=True)
def run_agent_process_tick(self, process_id: str):
    """
    Celery task that executes a single state transition tick for a ResearchAgentProcess.
    """
    return tick_agent_process(process_id)
