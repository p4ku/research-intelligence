"""
Zombie Process & Stale Task Watchdog.

Periodically inspects Celery tasks, PipelineRuns, ResearchAgentProcesses,
and ComponentRuns to detect dead workers, crashes, or unhandled task drops,
gracefully transitioning them to terminal states (FAILED/COMPLETED) and
closing execution timers to prevent endless hourglass indicators in the UI.
"""

import logging
import os
from datetime import timedelta
from typing import Dict, Any, Optional
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections, transaction

logger = logging.getLogger(__name__)

# Configurable timeout defaults via environment variables (180m = 3h component timeout, 360m = 6h pipeline timeout)
DEFAULT_MAX_COMPONENT_AGE_MINUTES: int = int(os.environ.get("ZOMBIE_WATCHDOG_COMPONENT_TIMEOUT_MINUTES", "180"))
DEFAULT_MAX_PIPELINE_AGE_MINUTES: int = int(os.environ.get("ZOMBIE_WATCHDOG_PIPELINE_TIMEOUT_MINUTES", "360"))


def reap_zombie_tasks(
    max_component_age_minutes: int = DEFAULT_MAX_COMPONENT_AGE_MINUTES,
    max_pipeline_age_minutes: int = DEFAULT_MAX_PIPELINE_AGE_MINUTES,
    force: bool = False,
    auto_retry: bool = False,
    max_retries: int = 2,
) -> Dict[str, Any]:
    """
    Finds and resolves orphaned/zombie ComponentRuns, PipelineRuns, and
    ResearchAgentProcesses stuck in 'running' or 'pending' states.
    Supports automatic task retry before declaring permanent failure.

    Args:
        max_component_age_minutes: Maximum elapsed minutes before an in-flight
                                   component task with no heartbeat is considered dead.
        max_pipeline_age_minutes: Maximum elapsed minutes for overall pipeline runs.
        force: If True, immediately terminates all running tasks regardless of age.
        auto_retry: If True, resets stalled components to 'pending' up to max_retries before failing.
        max_retries: Maximum number of automatic retries granted to a stalled component.

    Returns:
        Dict with counts of reaped and retried entities.
    """
    close_old_connections()
    
    # Check if overridden in environment during runtime
    env_comp = os.environ.get("ZOMBIE_WATCHDOG_COMPONENT_TIMEOUT_MINUTES")
    if env_comp and env_comp.isdigit() and max_component_age_minutes == DEFAULT_MAX_COMPONENT_AGE_MINUTES:
        max_component_age_minutes = int(env_comp)
    env_pipe = os.environ.get("ZOMBIE_WATCHDOG_PIPELINE_TIMEOUT_MINUTES")
    if env_pipe and env_pipe.isdigit() and max_pipeline_age_minutes == DEFAULT_MAX_PIPELINE_AGE_MINUTES:
        max_pipeline_age_minutes = int(env_pipe)

    now = timezone.now()
    comp_cutoff = now - timedelta(minutes=max_component_age_minutes)
    pipe_cutoff = now - timedelta(minutes=max_pipeline_age_minutes)

    stats = {
        "reaped_components": 0,
        "reaped_pipelines": 0,
        "reaped_agents": 0,
        "retried_components": 0,
        "details": []
    }

    pipelines_to_notify = []

    from research_intelligence.models import ComponentRun, PipelineRun, ResearchAgentProcess

    # -------------------------------------------------------------------------
    # 1. Inspect & Reap Stale ComponentRuns
    # -------------------------------------------------------------------------
    stale_comps_qs = ComponentRun.objects.filter(status__in=['running', 'pending'])
    if not force:
        stale_comps_qs = stale_comps_qs.filter(started_at__lt=comp_cutoff)

    for comp in stale_comps_qs:
        with transaction.atomic():
            age_min = round((now - comp.started_at).total_seconds() / 60.0, 1) if comp.started_at else 0
            m = comp.metrics or {}

            # If the worker has logged recent progress within the timeout window, it is actively running and not a zombie
            last_progress_at_str = m.get("last_progress_at")
            inactive_min = age_min
            if last_progress_at_str and not force:
                try:
                    from datetime import datetime
                    last_progress_dt = datetime.fromisoformat(last_progress_at_str)
                    if timezone.is_naive(last_progress_dt):
                        last_progress_dt = timezone.make_aware(last_progress_dt, timezone.get_current_timezone())
                    if last_progress_dt > comp_cutoff:
                        # Worker made progress recently (within timeout cutoff)
                        continue
                    inactive_min = round((now - last_progress_dt).total_seconds() / 60.0, 1)
                except Exception as parse_err:
                    logger.debug(f"Could not parse last_progress_at for ComponentRun '{comp.id}': {parse_err}")

            total_items = m.get("total_work_items") or m.get("total_to_screen") or m.get("total_screened") or m.get("total_processed") or m.get("total_papers") or 0
            done_items = (
                (m.get("passed", 0) + m.get("rejected", 0) + m.get("withdrawn", 0) + m.get("failed", 0))
                or (m.get("completed_extractions", 0) + m.get("failed_extractions", 0))
                or m.get("total_screened", 0)
                or m.get("total_processed", 0)
            )
            
            # If all items were processed but status was left running due to a dropped callback
            if total_items > 0 and done_items >= total_items:
                comp.status = 'completed'
                comp.completed_at = now
                comp.save(update_fields=['status', 'completed_at'])
                logger.info(f"✨ [ZOMBIE WATCHDOG RECOVERED] ComponentRun '{comp.id}' ({comp.component_name}) was fully processed ({done_items}/{total_items}). Marked completed.")
                stats["details"].append(f"ComponentRun {comp.id} ({comp.component_name}) -> recovered completed")
                if comp.pipeline_run:
                    pipelines_to_notify.append(comp.pipeline_run)
            elif auto_retry and not force and (comp.metrics or {}).get("watchdog_retries", 0) < max_retries and comp.pipeline_run and comp.pipeline_run.status == 'running':
                retries = (comp.metrics or {}).get("watchdog_retries", 0)
                m_data = dict(comp.metrics or {})
                m_data["watchdog_retries"] = retries + 1
                m_data["last_watchdog_retry_at"] = now.isoformat()
                comp.metrics = m_data
                comp.status = 'pending'
                comp.started_at = now
                comp.error_message = f"Transient stall or worker exit detected (inactive for {inactive_min}m). Auto-retrying ({retries + 1}/{max_retries})."
                comp.save(update_fields=['status', 'metrics', 'started_at', 'error_message'])
                stats["retried_components"] += 1
                stats["details"].append(f"ComponentRun {comp.id} ({comp.component_name}) -> auto-retried ({retries + 1}/{max_retries})")
                logger.warning(f"🔄 [WATCHDOG AUTO-RETRY] Stalled ComponentRun '{comp.id}' ({comp.component_name}) re-queued as pending (retry {retries + 1}/{max_retries}).")
                if comp.pipeline_run:
                    pipelines_to_notify.append(comp.pipeline_run)
            else:
                reason = f"Zombie task reaped: No worker progress for {inactive_min} minutes (exceeded {max_component_age_minutes}m timeout)."
                logger.warning(f"🧟 [ZOMBIE COMPONENT REAPED] ComponentRun '{comp.id}' ({comp.component_name}) | Age: {age_min}m | Inactive: {inactive_min}m | Task ID: {comp.celery_task_id}")
                comp.status = 'failed'
                comp.error_message = reason
                comp.completed_at = now
                comp.save(update_fields=['status', 'error_message', 'completed_at'])
                stats["reaped_components"] += 1
                stats["details"].append(f"ComponentRun {comp.id} ({comp.component_name}) -> failed")

                # Immediately fail the associated PipelineRun if active and queue notification
                if comp.pipeline_run and comp.pipeline_run.status == 'running':
                    comp.pipeline_run.status = 'failed'
                    comp.pipeline_run.status_message = f"Pipeline terminated: Component '{comp.component_name}' reaped by watchdog as zombie ({reason})"
                    if not comp.pipeline_run.stopped_at_stage:
                        comp.pipeline_run.stopped_at_stage = comp.step_type or comp.pipeline_run.current_stage
                    comp.pipeline_run.completed_at = now
                    comp.pipeline_run.save(update_fields=['status', 'status_message', 'stopped_at_stage', 'completed_at'])
                    stats["reaped_pipelines"] += 1
                    if (comp.pipeline_run.configuration_override or {}).get('_is_agent') or comp.pipeline_run.agent_processes.exists():
                        stats["reaped_agents"] += 1
                    pipelines_to_notify.append(comp.pipeline_run)

    # -------------------------------------------------------------------------
    # 2. Inspect & Reap Stale PipelineRuns
    # -------------------------------------------------------------------------
    running_pipelines = PipelineRun.objects.filter(status='running')
    for pr in running_pipelines:
        with transaction.atomic():
            has_active_comps = pr.component_runs.filter(status__in=['running', 'pending']).exists()
            has_comps = pr.component_runs.exists()
            pr_age_min = round((now - pr.started_at).total_seconds() / 60.0, 1) if pr.started_at else 0

            should_reap = False
            new_status = 'failed'
            new_message = ""

            if not has_active_comps and has_comps:
                has_failed = pr.component_runs.filter(status='failed').exists()
                has_aborted = pr.component_runs.filter(status='aborted').exists()
                if has_failed:
                    should_reap = True
                    new_status = 'failed'
                    new_message = "Pipeline marked failed: One or more component steps failed."
                elif has_aborted:
                    should_reap = True
                    new_status = 'aborted'
                    new_message = "Pipeline marked aborted: Component execution was cancelled."
                elif pr.current_stage == 'completed':
                    should_reap = True
                    new_status = 'completed'
                    new_message = "Pipeline marked completed: All component steps finished successfully."
                else:
                    # Pipeline is in-flight (current_stage != 'completed') and no components failed.
                    # Only reap as zombie if it has been stalled/inactive beyond the timeout cutoff, or if force=True.
                    last_comp = pr.component_runs.order_by('-completed_at').first()
                    is_stalled = False
                    if force:
                        is_stalled = True
                    elif pr.started_at and pr.started_at < pipe_cutoff:
                        is_stalled = True
                    elif last_comp and last_comp.completed_at and last_comp.completed_at < comp_cutoff:
                        is_stalled = True

                    if is_stalled:
                        should_reap = True
                        new_status = 'failed'
                        new_message = f"Zombie pipeline reaped: Inactive for {pr_age_min}m without completing final stage."
            elif force or (pr.started_at and pr.started_at < pipe_cutoff and not has_active_comps):
                should_reap = True
                new_status = 'failed'
                new_message = f"Zombie pipeline reaped: Inactive for {pr_age_min}m without running tasks."

            if should_reap:
                logger.warning(f"🧟 [ZOMBIE PIPELINE REAPED] PipelineRun '{pr.id}' -> {new_status} | Reason: {new_message}")
                pr.status = new_status
                if new_message:
                    pr.status_message = new_message
                if not pr.stopped_at_stage:
                    pr.stopped_at_stage = pr.current_stage
                pr.completed_at = now
                pr.save(update_fields=['status', 'status_message', 'stopped_at_stage', 'completed_at'])
                stats["reaped_pipelines"] += 1
                if (pr.configuration_override or {}).get('_is_agent') or pr.agent_processes.exists():
                    stats["reaped_agents"] += 1
                stats["details"].append(f"PipelineRun {pr.id} -> {new_status}")

    # -------------------------------------------------------------------------
    # 3. Inspect & Reap Stale ResearchAgentProcesses
    # -------------------------------------------------------------------------
    running_agents = ResearchAgentProcess.objects.filter(status='running')
    for agent in running_agents:
        with transaction.atomic():
            pr = agent.pipeline_run
            agent_age_min = round((now - agent.started_at).total_seconds() / 60.0, 1) if agent.started_at else 0
            should_reap_agent = False
            agent_final_status = 'failed'
            agent_stop_reason = ""

            if pr and pr.status in ('completed', 'failed', 'aborted'):
                should_reap_agent = True
                agent_final_status = pr.status
                agent_stop_reason = f"Zombie process reaped: {pr.status_message}" if pr.status_message else f"Synchronized with underlying PipelineRun status ({pr.status})."
            elif not pr and (force or (agent.started_at and agent.started_at < pipe_cutoff)):
                should_reap_agent = True
                agent_final_status = 'failed'
                agent_stop_reason = f"Zombie agent process reaped: Inactive for {agent_age_min}m without active pipeline run."
            elif force or (agent.updated_at and agent.updated_at < comp_cutoff and pr and pr.status == 'running' and not pr.component_runs.filter(status__in=['running', 'pending']).exists()):
                should_reap_agent = True
                agent_final_status = 'failed'
                agent_stop_reason = f"Zombie agent process reaped: No worker activity for {agent_age_min}m."

            if should_reap_agent:
                logger.warning(f"🧟 [ZOMBIE AGENT REAPED] AgentProcess '{agent.id}' ({agent.name}) -> {agent_final_status} | Stop Reason: {agent_stop_reason}")
                agent.status = agent_final_status
                agent.stopped_at_step = agent.current_step
                agent.stop_reason = agent_stop_reason
                if not agent.error_message and agent_final_status == 'failed':
                    agent.error_message = agent_stop_reason
                agent.completed_at = now
                history = list(agent.step_history or [])
                history.append({
                    "step": agent.current_step,
                    "event": "zombie_reaped",
                    "status": agent_final_status,
                    "message": agent_stop_reason,
                    "timestamp": now.isoformat()
                })
                agent.step_history = history
                agent.save(update_fields=['status', 'stopped_at_step', 'stop_reason', 'error_message', 'completed_at', 'step_history', 'updated_at'])
                stats["reaped_agents"] += 1
                stats["details"].append(f"ResearchAgentProcess {agent.id} -> {agent_final_status}")

    # -------------------------------------------------------------------------
    # 4. Notify Orchestrator of Reaped or Recovered Pipeline Runs
    # -------------------------------------------------------------------------
    seen_pr_ids = set()
    for pr in pipelines_to_notify:
        if pr and pr.id not in seen_pr_ids:
            seen_pr_ids.add(pr.id)
            try:
                from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
                notify_pipeline_orchestrator_tick(pr)
            except Exception as tick_err:
                logger.warning(f"Watchdog orchestrator tick notification failed: {tick_err}")

    close_old_connections()
    return stats


@shared_task(name="research_intelligence.tasks.auxiliary.zombie_watchdog.reap_zombie_tasks_task", acks_late=True, reject_on_worker_lost=True)
def reap_zombie_tasks_task(
    max_component_age_minutes: int = DEFAULT_MAX_COMPONENT_AGE_MINUTES,
    max_pipeline_age_minutes: int = DEFAULT_MAX_PIPELINE_AGE_MINUTES,
    force: bool = False,
    auto_retry: bool = True,
) -> Dict[str, Any]:
    """
    Celery Beat scheduled task executing periodic zombie process reaping with automatic retry resilience.
    """
    logger.info("🕒 [CELERY BEAT] Running periodic Zombie Process & Stale Task Watchdog...")
    return reap_zombie_tasks(
        max_component_age_minutes=max_component_age_minutes,
        max_pipeline_age_minutes=max_pipeline_age_minutes,
        force=force,
        auto_retry=auto_retry,
    )
