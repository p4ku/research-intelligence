"""
Autonomous Pipeline Run & Research Agent Process Runner.

Encapsulates the lifecycle, concurrency control, and DAG orchestration for
PipelineRun (primary) and ResearchAgentProcess (compatibility) instances.
"""

import logging
from typing import Dict, Any, Optional, Union
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


class PipelineRunner:
    """
    Primary Execution and State Machine Engine for PipelineRun instances.
    Operates directly on PipelineRun, orchestrating the WorkflowDAG.
    """

    @classmethod
    def tick(cls, pipeline_run_id_or_obj: Union[str, PipelineRun], agent_process: Optional[ResearchAgentProcess] = None) -> Dict[str, Any]:
        """
        Executes a single state transition tick for a PipelineRun.
        Evaluates the current state, builds the DAG for the workspace, and dispatches all ready nodes.
        """
        if not connection.in_atomic_block:
            close_old_connections()
        with transaction.atomic():
            pr_id = getattr(pipeline_run_id_or_obj, 'id', pipeline_run_id_or_obj)
            try:
                if connection.vendor == 'postgresql':
                    pipeline_run = PipelineRun.objects.select_for_update().get(pk=pr_id)
                else:
                    pipeline_run = PipelineRun.objects.get(pk=pr_id)
            except PipelineRun.DoesNotExist:
                logger.error(f"PipelineRun '{pr_id}' not found.")
                return {"success": False, "error": f"PipelineRun '{pr_id}' not found."}

            # If pipeline is in terminal or paused state, do not advance
            if pipeline_run.status in ['paused', 'aborted', 'failed', 'completed']:
                logger.info(f"PipelineRun '{pipeline_run.id}' is in status '{pipeline_run.status}'. No state transition taken.")
                return {
                    "success": True,
                    "status": pipeline_run.status,
                    "current_step": pipeline_run.current_stage,
                    "message": f"PipelineRun is in status '{pipeline_run.status}'."
                }

            workspace = pipeline_run.workspace
            config = dict(pipeline_run.configuration_override or {})
            if agent_process and getattr(agent_process, 'configuration_override', None):
                config = {**config, **agent_process.configuration_override}
            limit = config.get("limit")

            # Execute and dispatch via Workflow DAG
            dag = build_default_slr_dag(workspace=workspace, config=config)
            return dag.evaluate_and_dispatch(
                pipeline_run=pipeline_run,
                agent_process=agent_process,
                config=config,
                limit=limit
            )

    @classmethod
    def handle_component_completion(cls, pipeline_run_id_or_obj):
        """
        Triggered whenever a ComponentRun finishes to advance execution of the PipelineRun
        and any attached ResearchAgentProcesses.
        """
        if not pipeline_run_id_or_obj:
            return
        try:
            import uuid
            if isinstance(pipeline_run_id_or_obj, (str, uuid.UUID)):
                pipeline_run = PipelineRun.objects.get(pk=pipeline_run_id_or_obj)
            else:
                pipeline_run = pipeline_run_id_or_obj

            # Refresh and aggregate cost on pipeline_run
            comp_runs = list(pipeline_run.component_runs.all())
            comp_costs = sum(
                float((cr.metrics or {}).get("usd_cost") or 0.0)
                for cr in comp_runs
            )
            if comp_costs > float(pipeline_run.usd_cost or 0.0):
                pipeline_run.usd_cost = comp_costs
                pipeline_run.save(update_fields=['usd_cost'])

            # Check if an SLR audit gate should halt automated DAG progression
            try:
                from slr_review.tasks.orchestrator_hooks import intercept_component_completion
                recent_completed = [cr for cr in comp_runs if cr.status == 'completed']
                if recent_completed:
                    recent_completed.sort(key=lambda r: (r.completed_at or timezone.now(), getattr(r, 'id', 0) or 0), reverse=True)
                    last_comp = recent_completed[0]
                    comp_identifier = getattr(last_comp, 'component_name', None) or last_comp.step_type
                    gate_result = intercept_component_completion(pipeline_run, comp_identifier)
                    if gate_result.get("halt"):
                        logger.info(f"SLR Audit gate halted PipelineRun {pipeline_run.id} at stage '{gate_result.get('stage')}'.")
                        return
            except Exception as slr_err:
                logger.warning(f"SLR audit gate check encountered an error: {slr_err}")

            running_agents = list(pipeline_run.agent_processes.filter(status='running'))
            from research_intelligence.tasks.orchestrator.dag.base_node import safe_dispatch_on_commit

            if running_agents:
                from research_intelligence.tasks.orchestrator.agent_engine import run_agent_process_tick
                for agent_proc in running_agents:
                    proc_id = str(agent_proc.id)
                    def _dispatch_agent_tick(target_id=proc_id):
                        try:
                            run_agent_process_tick.delay(target_id)
                        except Exception:
                            try:
                                ResearchAgentRunner.tick(target_id)
                            except Exception as sync_err:
                                logger.warning(f"Fallback tick execution failed for agent '{target_id}': {sync_err}")
                    safe_dispatch_on_commit(_dispatch_agent_tick)
            elif (pipeline_run.configuration_override or {}).get('autonomous', False) or pipeline_run.schedule is not None:
                # Standalone autonomous pipeline run (scheduled or configured for autonomous progression)
                from research_intelligence.tasks.orchestrator.agent_engine import run_pipeline_tick
                pr_id = str(pipeline_run.id)
                def _dispatch_pipeline_tick(target_id=pr_id):
                    try:
                        run_pipeline_tick.delay(target_id)
                    except Exception:
                        try:
                            cls.tick(target_id)
                        except Exception as sync_err:
                            logger.warning(f"Fallback tick execution failed for pipeline '{target_id}': {sync_err}")
                safe_dispatch_on_commit(_dispatch_pipeline_tick)
            else:
                # Manual step execution: check if terminal component run completed
                has_pending = any(cr.status in ('pending', 'running') for cr in comp_runs)
                completed_runs = [cr for cr in comp_runs if cr.status == 'completed']
                if not has_pending and completed_runs:
                    completed_runs.sort(key=lambda r: (r.completed_at or timezone.now(), r.id or 0), reverse=True)
                    last_comp = completed_runs[0]
                    if last_comp and last_comp.step_type in ['reporting']:
                        pipeline_run.status = 'completed'
                        pipeline_run.current_stage = 'completed'
                        if not pipeline_run.completed_at:
                            pipeline_run.completed_at = timezone.now()
                        pipeline_run.save(update_fields=['status', 'current_stage', 'completed_at', 'usd_cost'])
        except Exception as e:
            logger.warning(f"Failed to handle component completion tick: {e}")

    @classmethod
    def send_completion_notification(cls, pipeline_run_or_agent, agent_process=None):
        """
        Sends an email digest notification via Mailgun when a pipeline run (or agent process)
        reaches a terminal state.
        """
        if isinstance(pipeline_run_or_agent, ResearchAgentProcess):
            agent_process = pipeline_run_or_agent
            pipeline_run = agent_process.pipeline_run
        else:
            pipeline_run = pipeline_run_or_agent
            if not agent_process and pipeline_run:
                agent_process = pipeline_run.agent_processes.first()

        workspace = (pipeline_run.workspace if pipeline_run else (agent_process.workspace if agent_process else None))
        if not workspace:
            return

        from research_intelligence.features import is_feature_enabled, Feature

        if not is_feature_enabled(Feature.EMAIL_NOTIFICATIONS):
            return

        recipients = set()
        cfg = {}
        if pipeline_run and pipeline_run.configuration_override:
            cfg.update(pipeline_run.configuration_override)
        if agent_process and agent_process.configuration_override:
            cfg.update(agent_process.configuration_override)

        cfg_emails = cfg.get("notification_emails") or cfg.get("notification_email")
        if cfg_emails:
            if isinstance(cfg_emails, list):
                for em in cfg_emails:
                    if em:
                        recipients.add(str(em).strip())
            else:
                for em in str(cfg_emails).split(","):
                    if em.strip():
                        recipients.add(em.strip())

        status = pipeline_run.status if pipeline_run else (agent_process.status if agent_process else 'completed')
        is_error = status in ['failed', 'aborted']
        target_types = ['pipeline_errors', 'all'] if is_error else ['result_report', 'pipeline_status', 'all']

        subscribers = workspace.subscribers.filter(
            is_active=True,
            subscription_type__in=target_types
        )
        for s in subscribers:
            if s.email:
                recipients.add(s.email.strip())

        recipient_list = sorted(list(recipients))
        if not recipient_list:
            logger.info(f"📧 [NOTIFICATION] No active recipients found for Workspace '{workspace.name}' (event={status}).")
            return

        from research_intelligence.tasks.auxiliary.email_digest import build_pipeline_run_digest_payload
        payload = build_pipeline_run_digest_payload(pipeline_run, agent_process=agent_process, workspace=workspace)
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


class ResearchAgentRunner:
    """
    Backwards-compatible facade over PipelineRunner for legacy ResearchAgentProcess instances.
    """

    @classmethod
    def tick(cls, process_id: str) -> Dict[str, Any]:
        """
        Executes a state transition tick for a ResearchAgentProcess by delegating to PipelineRunner.
        """
        if not connection.in_atomic_block:
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
            history = list(process.step_history or [])

            # State: INITIALIZED -> Transition to search
            if process.current_step == 'initialized':
                process.status = 'running'
                process.current_step = 'search'
                if config.get("reprocess_existing") and not process.reprocess_existing:
                    process.reprocess_existing = True
                history.append({
                    "step": "search",
                    "event": "started",
                    "pipeline_run_id": str(process.id),
                    "timestamp": timezone.now().isoformat()
                })
                process.step_history = history
                process.save(update_fields=['status', 'current_stage', 'reprocess_existing', 'step_history', 'updated_at'])

            return PipelineRunner.tick(process, agent_process=process)

    @classmethod
    def handle_component_completion(cls, pipeline_run_id_or_obj):
        return PipelineRunner.handle_component_completion(pipeline_run_id_or_obj)

    @classmethod
    def send_completion_notification(cls, agent_process: ResearchAgentProcess):
        return PipelineRunner.send_completion_notification(agent_process.pipeline_run, agent_process=agent_process)
