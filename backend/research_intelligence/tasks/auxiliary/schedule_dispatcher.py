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

    from research_intelligence.models import WorkflowSchedule

    due_schedules = WorkflowSchedule.objects.filter(
        is_active=True,
        next_run_at__isnull=False,
        next_run_at__lte=now
    ).select_related('workspace', 'created_by')

    dispatched = []
    errors = []

    for schedule in due_schedules:
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

                    agent = locked_sched.trigger_run()
                    dispatched.append({
                        "schedule_id": str(locked_sched.id),
                        "schedule_name": locked_sched.name,
                        "workspace_name": locked_sched.workspace.name,
                        "agent_id": str(agent.id),
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
