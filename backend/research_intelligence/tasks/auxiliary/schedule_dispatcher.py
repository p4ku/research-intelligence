"""
Workflow Schedule Dispatcher.

Periodically queries active WorkflowSchedule models whose next_run_at <= timezone.now(),
dispatches autonomous SLR pipeline runs, and recalculates subsequent next_run_at timestamps.
"""

import logging
from typing import Dict, Any, List
from celery import shared_task
from django.utils import timezone
from django.db import close_old_connections, transaction

logger = logging.getLogger(__name__)


def dispatch_due_workflow_schedules(dry_run: bool = False) -> Dict[str, Any]:
    """
    Finds and triggers all active WorkflowSchedule records that are due for execution.

    Args:
        dry_run: If True, only inspects and returns what would run without triggering.

    Returns:
        Dict with summary metrics and dispatched schedule details.
    """
    close_old_connections()
    now = timezone.now()

    from research_intelligence.features import is_feature_enabled, Feature

    if not is_feature_enabled(Feature.SCHEDULING):
        logger.info("⏸️ [SCHEDULE DISPATCHER] Feature SCHEDULING is disabled. Skipping dispatch.")
        return {
            "status": "disabled",
            "dispatched_count": 0,
            "dispatched": [],
            "skipped_overlap_count": 0,
            "skipped_overlap": [],
            "errors_count": 0,
            "errors": [],
            "checked_at": now.isoformat()
        }

    from research_intelligence.models import WorkflowSchedule

    due_schedules = WorkflowSchedule.objects.filter(
        is_active=True,
        next_run_at__isnull=False,
        next_run_at__lte=now
    ).select_related('workspace', 'created_by')

    dispatched = []
    skipped_overlap = []
    errors = []

    for idx, schedule in enumerate(due_schedules):
        try:
            if not dry_run:
                with transaction.atomic():
                    # Re-verify lock to prevent race conditions across parallel celery beat workers
                    locked_sched = WorkflowSchedule.objects.select_for_update(skip_locked=True).filter(
                        id=schedule.id,
                        is_active=True,
                        next_run_at__lte=now
                    ).first()

                    if not locked_sched:
                        continue

                    # Overlap Guard: Skip if previous run is still active
                    if locked_sched.prevent_overlap and locked_sched.last_pipeline_run:
                        current_status = locked_sched.current_execution_status
                        if current_status in ('running', 'pending'):
                            logger.warning(
                                f"⚠️ [SCHEDULE OVERLAP PREVENTED] Schedule '{locked_sched.name}' ({locked_sched.id}) "
                                f"skipped: previous PipelineRun '{locked_sched.last_pipeline_run.id}' is still in status '{current_status}'."
                            )
                            # Advance next_run_at to next cycle to avoid busy-spin
                            locked_sched.next_run_at = locked_sched.compute_next_run(base_time=now)
                            locked_sched.save(update_fields=['next_run_at', 'updated_at'])
                            skipped_overlap.append({
                                "schedule_id": str(locked_sched.id),
                                "schedule_name": locked_sched.name,
                                "previous_run_status": current_status,
                                "next_run_at": locked_sched.next_run_at.isoformat() if locked_sched.next_run_at else None
                            })
                            continue

                    # Stagger multiple simultaneous dispatches by 0s, 5s, 10s... up to max 45s
                    jitter_sec = min(45, idx * 5)
                    agent = locked_sched.trigger_run(jitter_seconds=jitter_sec)
                    if agent:
                        dispatched.append({
                            "schedule_id": str(locked_sched.id),
                            "schedule_name": locked_sched.name,
                            "workspace_name": locked_sched.workspace.name,
                            "agent_id": str(agent.id),
                            "jitter_seconds": jitter_sec,
                            "next_run_at": locked_sched.next_run_at.isoformat() if locked_sched.next_run_at else None
                        })
            else:
                dispatched.append({
                    "schedule_id": str(schedule.id),
                    "schedule_name": schedule.name,
                    "workspace_name": schedule.workspace.name,
                    "is_due": True,
                })
        except Exception as e:
            logger.error(f"❌ [SCHEDULE DISPATCH ERROR] Failed to dispatch schedule '{schedule.id}' ({schedule.name}): {e}", exc_info=True)
            errors.append({
                "schedule_id": str(schedule.id),
                "schedule_name": schedule.name,
                "error": str(e)
            })

    close_old_connections()
    return {
        "dispatched_count": len(dispatched),
        "dispatched": dispatched,
        "skipped_overlap_count": len(skipped_overlap),
        "skipped_overlap": skipped_overlap,
        "errors_count": len(errors),
        "errors": errors,
        "checked_at": now.isoformat()
    }


@shared_task(name="research_intelligence.tasks.auxiliary.schedule_dispatcher.dispatch_scheduled_workflow_runs_task")
def dispatch_scheduled_workflow_runs_task() -> Dict[str, Any]:
    """
    Celery Beat scheduled task executing periodic workflow schedule dispatching (runs every 60s).
    """
    return dispatch_due_workflow_schedules(dry_run=False)
