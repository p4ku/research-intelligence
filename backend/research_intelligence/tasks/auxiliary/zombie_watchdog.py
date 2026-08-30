"""
Zombie Process & Stale Task Watchdog.

Periodically inspects Celery tasks, PipelineRuns, ResearchAgentProcesses,
and ComponentRuns to detect dead workers, crashes, or unhandled task drops,
gracefully transitioning them to terminal states (FAILED/COMPLETED) and
closing execution timers to prevent endless hourglass indicators in the UI.
"""

import logging
from datetime import timedelta
from typing import Dict, Any, Optional
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections, transaction

logger = logging.getLogger(__name__)


def reap_zombie_tasks(
    max_component_age_minutes: int = 30,
    max_pipeline_age_minutes: int = 60,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Finds and resolves orphaned/zombie ComponentRuns, PipelineRuns, and
    ResearchAgentProcesses stuck in 'running' or 'pending' states.

    Args:
        max_component_age_minutes: Maximum elapsed minutes before an in-flight
                                   component task with no heartbeat is considered dead.
        max_pipeline_age_minutes: Maximum elapsed minutes for overall pipeline runs.
        force: If True, immediately terminates all running tasks regardless of age.

    Returns:
        Dict with counts of reaped entities.
    """
    close_old_connections()
    now = timezone.now()
    comp_cutoff = now - timedelta(minutes=max_component_age_minutes)
    pipe_cutoff = now - timedelta(minutes=max_pipeline_age_minutes)

    stats = {
        "reaped_components": 0,
        "reaped_pipelines": 0,
        "reaped_agents": 0,
        "details": []
    }

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
            reason = f"Zombie task reaped: No worker progress for {age_min} minutes (exceeded {max_component_age_minutes}m timeout)."
            logger.warning(f"🧟 [ZOMBIE COMPONENT REAPED] ComponentRun '{comp.id}' ({comp.component_name}) | Age: {age_min}m | Task ID: {comp.celery_task_id}")

            comp.status = 'failed'
            comp.error_message = reason
            comp.completed_at = now
            comp.save(update_fields=['status', 'error_message', 'completed_at'])
            stats["reaped_components"] += 1
            stats["details"].append(f"ComponentRun {comp.id} ({comp.component_name}) -> failed")

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
                # All components are completed, failed, or skipped
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
                else:
                    # All succeeded but pipeline status wasn't synchronized
                    should_reap = True
                    new_status = 'completed'
                    new_message = "Pipeline marked completed: All component steps finished successfully."
            elif force or (pr.started_at and pr.started_at < pipe_cutoff and not has_active_comps):
                should_reap = True
                new_status = 'failed'
                new_message = f"Zombie pipeline reaped: Inactive for {pr_age_min}m without running tasks."

            if should_reap:
                logger.warning(f"🧟 [ZOMBIE PIPELINE REAPED] PipelineRun '{pr.id}' -> {new_status} | Reason: {new_message}")
                pr.status = new_status
                if new_message:
                    pr.status_message = new_message
                pr.completed_at = now
                pr.save(update_fields=['status', 'status_message', 'completed_at'])
                stats["reaped_pipelines"] += 1
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

    close_old_connections()
    return stats


@shared_task(name="research_intelligence.tasks.auxiliary.zombie_watchdog.reap_zombie_tasks_task")
def reap_zombie_tasks_task(max_component_age_minutes: int = 30, max_pipeline_age_minutes: int = 60) -> Dict[str, Any]:
    """
    Celery Beat scheduled task executing periodic zombie process reaping.
    """
    logger.info("🕒 [CELERY BEAT] Running periodic Zombie Process & Stale Task Watchdog...")
    return reap_zombie_tasks(
        max_component_age_minutes=max_component_age_minutes,
        max_pipeline_age_minutes=max_pipeline_age_minutes,
        force=False,
    )
