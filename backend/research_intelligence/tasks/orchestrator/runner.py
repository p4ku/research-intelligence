"""
Autonomous Research Agent Process Runner.

Encapsulates the lifecycle, concurrency control, and DAG orchestration for
ResearchAgentProcess instances.
"""

import logging
from typing import Dict, Any, Optional
from django.conf import settings
from django.utils import timezone
from django.db import close_old_connections, transaction, connection

from research_intelligence.models import (
    PipelineRun,
    ResearchAgentProcess,
)
from research_intelligence.utils.mailer import send_mailgun_message
from research_intelligence.tasks.orchestrator.dag import build_default_slr_dag

logger = logging.getLogger(__name__)


class ResearchAgentRunner:
    """
    Autonomous Execution Engine for ResearchAgentProcesses.

    Responsibilities:
    1. Concurrency & Locking: Uses database row locks (select_for_update on Postgres)
       to prevent race conditions across parallel Celery workers.
    2. Lifecycle Management: Handles initialization (INITIALIZED -> RUNNING),
       step transitions, pauses, aborts, and terminal completion.
    3. DAG Orchestration: Instantiates and executes the WorkflowDAG for the agent's workspace.
    4. Completion Notifications: Sends rich email digests to active workspace subscribers
       via Mailgun upon pipeline completion.
    """

    @classmethod
    def tick(cls, process_id: str) -> Dict[str, Any]:
        """
        Executes a single state transition tick for a ResearchAgentProcess.
        
        Evaluates the current state of the agent, initializes the underlying
        PipelineRun if needed, builds the DAG for the workspace, and evaluates/dispatches
        all ready pipeline nodes.

        Args:
            process_id: UUID string of the ResearchAgentProcess to advance.

        Returns:
            Dict[str, Any]: Result dictionary containing success status, current step,
                            and state transition details.
        """
        close_old_connections()
        with transaction.atomic():
            try:
                if connection.vendor == 'postgresql':
                    process = ResearchAgentProcess.objects.select_for_update().get(pk=process_id)
                else:
                    process = ResearchAgentProcess.objects.get(pk=process_id)
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

    @classmethod
    def handle_component_completion(cls, pipeline_run_id_or_obj):
        """
        Triggered whenever a ComponentRun finishes to advance any attached
        running ResearchAgentProcesses.

        Args:
            pipeline_run_id_or_obj: PipelineRun instance or UUID string.
        """
        if not pipeline_run_id_or_obj:
            return
        try:
            if isinstance(pipeline_run_id_or_obj, str):
                pipeline_run = PipelineRun.objects.get(pk=pipeline_run_id_or_obj)
            else:
                pipeline_run = pipeline_run_id_or_obj

            # Refresh and aggregate cost on pipeline_run
            comp_costs = sum(
                float((cr.metrics or {}).get("usd_cost") or 0.0)
                for cr in pipeline_run.component_runs.all()
            )
            if comp_costs > float(pipeline_run.usd_cost or 0.0):
                pipeline_run.usd_cost = comp_costs
                pipeline_run.save(update_fields=['usd_cost'])

            running_agents = list(pipeline_run.agent_processes.filter(status='running'))
            if not running_agents and pipeline_run.workspace:
                orphan_agents = list(ResearchAgentProcess.objects.filter(
                    workspace=pipeline_run.workspace,
                    status='running',
                    pipeline_run__isnull=True
                ))
                for o_agent in orphan_agents:
                    o_agent.pipeline_run = pipeline_run
                    o_agent.save(update_fields=['pipeline_run'])
                    running_agents.append(o_agent)

            if running_agents:
                from research_intelligence.tasks.orchestrator.dag.base_node import safe_dispatch_on_commit
                from research_intelligence.tasks.orchestrator.agent_engine import run_agent_process_tick
                for agent_proc in running_agents:
                    proc_id = str(agent_proc.id)
                    def _dispatch_tick(target_id=proc_id):
                        try:
                            run_agent_process_tick.delay(target_id)
                        except Exception:
                            try:
                                cls.tick(target_id)
                            except Exception as sync_err:
                                logger.warning(f"Fallback tick execution failed for agent '{target_id}': {sync_err}")
                    safe_dispatch_on_commit(_dispatch_tick)
            else:
                # Check if all component runs are done for this pipeline run
                pending_runs = pipeline_run.component_runs.filter(status__in=['pending', 'running'])
                if not pending_runs.exists() and pipeline_run.component_runs.filter(status='completed').exists():
                    last_comp = pipeline_run.component_runs.order_by('-completed_at', '-id').first()
                    if last_comp and last_comp.step_type in ['signal_score', 'extraction', 'reporting']:
                        pipeline_run.status = 'completed'
                        pipeline_run.current_stage = 'completed'
                        if not pipeline_run.completed_at:
                            pipeline_run.completed_at = timezone.now()
                        pipeline_run.save(update_fields=['status', 'current_stage', 'completed_at', 'usd_cost'])
        except Exception as e:
            logger.warning(f"Failed to handle component completion tick: {e}")

    @classmethod
    def send_completion_notification(cls, agent_process: ResearchAgentProcess):
        """
        Sends an email digest notification via Mailgun when an agent process completes or fails.
        Notifies all active workspace subscribers and any explicit override email.

        Args:
            agent_process: ResearchAgentProcess that has reached a terminal state.
        """
        recipients = set()

        # Explicit override in config or workspace setting
        override_email = (
            agent_process.configuration_override.get("notification_email")
            or agent_process.workspace.notification_email
        )
        if override_email:
            recipients.add(override_email.strip())

        # Determine event type
        is_error = agent_process.status in ['failed', 'aborted']
        target_types = ['pipeline_errors', 'all'] if is_error else ['result_report', 'pipeline_status', 'all']

        # Workspace Active Subscribers filtered by subscription_type
        subscribers = agent_process.workspace.subscribers.filter(
            is_active=True,
            subscription_type__in=target_types
        )
        for s in subscribers:
            if s.email:
                recipients.add(s.email.strip())

        recipient_list = sorted(list(recipients))
        if not recipient_list:
            logger.info(f"📧 [NOTIFICATION] No active recipients/subscribers found for Workspace '{agent_process.workspace.name}' (event={agent_process.status}).")
            return


        from research_intelligence.tasks.auxiliary.email_digest import build_pipeline_run_digest_payload

        payload = build_pipeline_run_digest_payload(agent_process.pipeline_run, agent_process=agent_process)
        subject = payload["subject"]
        html_message = payload["html_content"]
        plain_message = payload["text_content"]

        import research_intelligence.tasks.orchestrator.agent_engine as ae
        mailer_fn = getattr(ae, 'send_mailgun_message', send_mailgun_message)

        for to_email in recipient_list:
            try:
                success, resp_or_err = mailer_fn(
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
