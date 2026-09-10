"""
Celery Task Liveness & Worker Inspection Utilities.

Provides lightweight, non-blocking inspection to determine whether a Celery task
is actively executing on a worker, reserved in memory, completed/failed in the
result backend, or orphaned/ghost (dead worker process with task still marked RUNNING).
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Set, Tuple

from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)


def get_active_celery_tasks_map(timeout: float = 0.3) -> Tuple[Dict[str, Dict[str, Any]], Set[str], bool]:
    """
    Queries Celery worker control inspector once with a short timeout.
    Returns:
        (active_map, reserved_set, inspector_online)
        where:
          - active_map: dict of task_id -> {"worker": worker_name, "time_start": float, ...}
          - reserved_set: set of pre-fetched task_ids waiting in worker memory
          - inspector_online: True if at least one worker answered or inspector was reachable
    """
    try:
        from django_project.celery import app as celery_app

        inspector = celery_app.control.inspect(timeout=timeout)
        if not inspector:
            return {}, set(), False

        active_dict = inspector.active() or {}
        reserved_dict = inspector.reserved() or {}

        active_map: Dict[str, Dict[str, Any]] = {}
        for worker_name, tasks in active_dict.items():
            for t in (tasks or []):
                tid = t.get("id")
                if tid:
                    active_map[tid] = {
                        "worker": worker_name,
                        "time_start": t.get("time_start"),
                        "name": t.get("name"),
                    }

        reserved_set: Set[str] = set()
        for worker_name, tasks in reserved_dict.items():
            for t in (tasks or []):
                tid = t.get("id")
                if tid:
                    reserved_set.add(tid)

        inspector_online = bool(active_dict or reserved_dict or inspector.ping())
        return active_map, reserved_set, inspector_online
    except Exception as e:
        logger.debug(f"Celery worker inspector query failed or timed out: {e}")
        return {}, set(), False


def check_task_liveness(
    task_id: Optional[str],
    component_status: str,
    active_map: Optional[Dict[str, Dict[str, Any]]] = None,
    reserved_set: Optional[Set[str]] = None,
    inspector_ok: bool = True,
    duration_seconds: float = 0.0,
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluates whether a task is actively running, queued, finished, or a ghost/zombie.

    Returns dict:
      {
        "state": "ACTIVE" | "RESERVED" | "GHOST" | "CRASHED" | "DESYNC" | "REVOKED" | "PENDING" | "COMPLETED" | "NONE",
        "worker": str or None,
        "is_alive": bool,
        "is_ghost": bool,
        "badge_text": str,
        "badge_bg": str,
        "badge_color": str,
        "tooltip": str
      }
    """
    if not task_id:
        return {
            "state": "NONE",
            "worker": None,
            "is_alive": False,
            "is_ghost": False,
            "badge_text": "-",
            "badge_bg": "#6c757d",
            "badge_color": "#ffffff",
            "tooltip": "No Celery task ID recorded",
        }

    # If component is already in a terminal state (completed, failed, aborted)
    if component_status in ("completed", "failed", "aborted", "skipped"):
        return {
            "state": "TERMINAL",
            "worker": None,
            "is_alive": False,
            "is_ghost": False,
            "badge_text": component_status.upper(),
            "badge_bg": "#6c757d",
            "badge_color": "#ffffff",
            "tooltip": f"Component run already {component_status}",
        }

    # 1. Check if the task is actively executing in a worker right now
    if active_map and task_id in active_map:
        worker_info = active_map[task_id]
        worker_name = worker_info.get("worker", "unknown")
        # Strip long prefix if present
        clean_worker = worker_name.replace("celery@", "")
        return {
            "state": "ACTIVE",
            "worker": worker_name,
            "is_alive": True,
            "is_ghost": False,
            "badge_text": f"● ACTIVE: {clean_worker}",
            "badge_bg": "#198754",  # Green
            "badge_color": "#ffffff",
            "tooltip": f"Actively executing on worker '{worker_name}'",
        }

    # 2. Check if reserved/prefetched in worker memory
    if reserved_set and task_id in reserved_set:
        return {
            "state": "RESERVED",
            "worker": None,
            "is_alive": True,
            "is_ghost": False,
            "badge_text": "● RESERVED",
            "badge_bg": "#ffc107",  # Yellow
            "badge_color": "#000000",
            "tooltip": "Task prefetched and waiting in worker queue",
        }

    # 3. Check Celery AsyncResult state (fast Redis GET)
    celery_backend_state = None
    try:
        from celery.result import AsyncResult
        res = AsyncResult(task_id)
        celery_backend_state = res.state
    except Exception:
        pass

    if celery_backend_state == "FAILURE":
        return {
            "state": "CRASHED",
            "worker": None,
            "is_alive": False,
            "is_ghost": True,
            "badge_text": "❌ CRASHED IN CELERY",
            "badge_bg": "#dc3545",  # Red
            "badge_color": "#ffffff",
            "tooltip": "Celery worker failed with an exception, but database status was not updated to FAILED",
        }

    if celery_backend_state == "SUCCESS":
        return {
            "state": "DESYNC",
            "worker": None,
            "is_alive": False,
            "is_ghost": False,
            "badge_text": "⚠️ CELERY FINISHED",
            "badge_bg": "#fd7e14",  # Orange
            "badge_color": "#ffffff",
            "tooltip": "Task finished in Celery backend, but database status is still RUNNING (desynchronized)",
        }

    if celery_backend_state == "REVOKED":
        return {
            "state": "REVOKED",
            "worker": None,
            "is_alive": False,
            "is_ghost": True,
            "badge_text": "🚫 REVOKED",
            "badge_bg": "#6c757d",  # Gray
            "badge_color": "#ffffff",
            "tooltip": "Task was revoked or killed",
        }

    # 4. If component is RUNNING but not found in active/reserved workers
    if component_status == "running":
        # Check recent progress from metrics
        last_progress = (metrics or {}).get("last_progress_at")
        recent_progress = False
        if last_progress:
            try:
                dt = datetime.fromisoformat(last_progress)
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt, timezone.get_current_timezone())
                if (timezone.now() - dt).total_seconds() < 120:
                    recent_progress = True
            except Exception:
                pass

        # If it has only just started (< 45s), it might be transitioning from broker queue to worker
        if duration_seconds < 45 and not recent_progress:
            return {
                "state": "STARTING",
                "worker": None,
                "is_alive": True,
                "is_ghost": False,
                "badge_text": "⏳ QUEUED / STARTING",
                "badge_bg": "#0dcaf0",  # Cyan
                "badge_color": "#000000",
                "tooltip": "Task sent to broker and initializing in worker",
            }

        # If inspector responded (online) and task is NOT on any worker:
        if inspector_ok:
            return {
                "state": "GHOST",
                "worker": None,
                "is_alive": False,
                "is_ghost": True,
                "badge_text": "💀 NO WORKER / GHOST",
                "badge_bg": "#dc3545",  # Red
                "badge_color": "#ffffff",
                "tooltip": f"Task is marked RUNNING for {int(duration_seconds)}s, but NO active Celery worker is processing this task ID! (Worker died, was killed, or task dropped)",
            }
        else:
            # Inspector timed out or no workers reachable
            return {
                "state": "UNKNOWN",
                "worker": None,
                "is_alive": False,
                "is_ghost": False,
                "badge_text": "❓ WORKERS UNREACHABLE",
                "badge_bg": "#6c757d",
                "badge_color": "#ffffff",
                "tooltip": "Could not contact Celery worker inspector to verify task status",
            }

    # Default pending state
    return {
        "state": "PENDING",
        "worker": None,
        "is_alive": False,
        "is_ghost": False,
        "badge_text": "PENDING",
        "badge_bg": "#6c757d",
        "badge_color": "#ffffff",
        "tooltip": "Task is pending execution",
    }


def render_celery_task_id_cell(task_id: Optional[str], liveness: Dict[str, Any]) -> str:
    """
    Renders formatted HTML for the CELERY TASK ID admin column with status badge.
    """
    if not task_id:
        return "-"

    badge_text = escape(liveness.get("badge_text", "-"))
    badge_bg = liveness.get("badge_bg", "#6c757d")
    badge_color = liveness.get("badge_color", "#ffffff")
    tooltip = escape(liveness.get("tooltip", ""))
    is_ghost = liveness.get("is_ghost", False)

    # Pulse animation style for ghost tasks
    pulse_style = "box-shadow: 0 0 4px #dc3545;" if is_ghost else ""

    short_id = task_id[:13] + "..." if len(task_id) > 16 else task_id

    html = f"""
    <div style="line-height: 1.25; min-width: 140px;">
        <div style="margin-bottom: 3px;">
            <span title="{tooltip}" style="background-color: {badge_bg}; color: {badge_color}; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; white-space: nowrap; display: inline-block; cursor: help; {pulse_style}">
                {badge_text}
            </span>
        </div>
        <div style="display: flex; align-items: center; gap: 4px;">
            <span style="font-family: monospace; font-size: 11px; color: #495057;" title="{escape(task_id)}">
                {escape(short_id)}
            </span>
            <a href="/admin/queue-monitor/" title="Open Live Queue & Worker Monitor" style="text-decoration: none; font-size: 11px; opacity: 0.7;">⚡</a>
        </div>
    </div>
    """
    return mark_safe(html)
