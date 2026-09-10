import base64
import json
import logging
import os
import ssl
import time
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views import View
from django.views.decorators.clickjacking import xframe_options_sameorigin

from research_intelligence.models import ComponentRun, PipelineRun
from research_intelligence.tasks.auxiliary.zombie_watchdog import reap_zombie_tasks

logger = logging.getLogger(__name__)


def format_elapsed_time(seconds: float) -> str:
    """Formats seconds into human-readable elapsed duration (e.g. 14s, 3m 20s, 1h 05m)."""
    if seconds is None or seconds < 0:
        return "0s"
    sec = int(seconds)
    if sec < 60:
        return f"{sec}s"
    minutes, rem_sec = divmod(sec, 60)
    if minutes < 60:
        return f"{minutes}m {rem_sec:02d}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins:02d}m {rem_sec:02d}s"


def decode_celery_message(raw_msg: str | bytes) -> dict:
    """Decodes a raw Celery message payload retrieved from a Redis queue."""
    try:
        if isinstance(raw_msg, bytes):
            raw_msg = raw_msg.decode("utf-8", errors="replace")
        data = json.loads(raw_msg)
        headers = data.get("headers", {})
        task_name = headers.get("task") or data.get("task", "Unknown Task")
        task_id = headers.get("id") or data.get("id", "")
        argsrepr = headers.get("argsrepr", "")
        kwargsrepr = headers.get("kwargsrepr", "")
        eta = headers.get("eta")
        retries = headers.get("retries", 0)

        # Decode base64 body if args/kwargs are not directly in headers
        if not argsrepr and data.get("body"):
            try:
                body_raw = data.get("body")
                body_decoded = base64.b64decode(body_raw).decode("utf-8", errors="replace")
                body_json = json.loads(body_decoded)
                if isinstance(body_json, list) and len(body_json) >= 2:
                    args_list, kwargs_dict = body_json[0], body_json[1]
                    argsrepr = str(args_list)
                    kwargsrepr = str(kwargs_dict) if kwargs_dict else ""
            except Exception:
                pass

        return {
            "task": task_name,
            "id": task_id,
            "args": argsrepr or "-",
            "kwargs": kwargsrepr or "",
            "eta": eta,
            "retries": retries,
        }
    except Exception as e:
        return {
            "task": "Raw Message",
            "id": "",
            "args": str(raw_msg)[:200],
            "kwargs": "",
            "eta": None,
            "retries": 0,
        }


@method_decorator(xframe_options_sameorigin, name="dispatch")
class QueueMonitorView(View):
    """
    Django Admin Class-Based View for monitoring:
    1. Celery queues and pending task messages in Redis.
    2. Actively running tasks and workers with start time and elapsed duration.
    3. In-flight PipelineRuns and ComponentRuns from the database.
    4. Worker nodes health, concurrency, and watchdog cleanup actions.
    """

    KNOWN_QUEUES = ["celery", "tenant-default", "tenant-bulk-scraping"]

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            messages.error(request, "Staff permission required to access Queue & Worker Monitor.")
            return HttpResponseRedirect(reverse("admin:login"))
        return super().dispatch(request, *args, **kwargs)

    # -------------------------------------------------------------------------
    # Redis & Broker Connection Helpers
    # -------------------------------------------------------------------------
    def get_redis_client(self):
        """Creates a short-timeout Redis client instance using CELERY_BROKER_URL."""
        try:
            import redis

            broker_url = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
            clean_url = broker_url.replace("ssl_cert_reqs=CERT_NONE", "ssl_cert_reqs=none")
            if "rediss://" in clean_url:
                r = redis.from_url(clean_url, ssl_cert_reqs=ssl.CERT_NONE, socket_connect_timeout=1.5)
            else:
                r = redis.from_url(clean_url, socket_connect_timeout=1.5)
            r.ping()
            return r
        except Exception as e:
            logger.debug(f"Redis connection check failed: {e}")
            return None

    def get_queue_statistics(self, redis_client) -> tuple[list[dict], list[dict], str]:
        """
        Inspects Redis list queues and extracts pending message counts and details.
        Returns (queue_summaries, queued_tasks_preview, error_message).
        """
        if not redis_client:
            broker_url = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
            # Mask credentials in display
            safe_url = broker_url.split("@")[-1] if "@" in broker_url else broker_url
            return [], [], f"Redis broker offline or unreachable ({safe_url})"

        queue_summaries = []
        queued_messages = []
        try:
            # Discover active list keys in Redis
            all_queues = list(self.KNOWN_QUEUES)
            try:
                # Scan for any additional keys of list type
                for key in redis_client.scan_iter(count=100):
                    key_str = key.decode("utf-8") if isinstance(key, bytes) else str(key)
                    if key_str not in all_queues and not key_str.startswith("_kombu"):
                        try:
                            if redis_client.type(key_str) in (b"list", "list"):
                                all_queues.append(key_str)
                        except Exception:
                            pass
            except Exception:
                pass

            for q in all_queues:
                try:
                    q_len = redis_client.llen(q)
                except Exception:
                    q_len = 0

                queue_summaries.append({
                    "name": q,
                    "count": q_len,
                    "status": "Active" if q_len > 0 else "Empty",
                })

                # Fetch up to first 20 items from non-empty queue
                if q_len > 0:
                    try:
                        raw_items = redis_client.lrange(q, 0, 19)
                        for idx, item in enumerate(raw_items):
                            decoded = decode_celery_message(item)
                            decoded["queue"] = q
                            decoded["position"] = idx + 1
                            queued_messages.append(decoded)
                    except Exception as e:
                        logger.debug(f"Error reading queue {q}: {e}")

            return queue_summaries, queued_messages, ""
        except Exception as e:
            return [], [], f"Error querying Redis queues: {str(e)}"

    # -------------------------------------------------------------------------
    # Celery Worker Inspector Helpers
    # -------------------------------------------------------------------------
    def get_celery_worker_data(self) -> tuple[list[dict], list[dict], str]:
        """
        Uses Celery control inspector to fetch currently active tasks and worker node stats.
        Returns (active_worker_tasks, worker_nodes, error_message).
        """
        try:
            from django_project.celery import app as celery_app

            inspector = celery_app.control.inspect(timeout=0.8)
            if not inspector:
                return [], [], "Celery control inspector unavailable"

            ping_data = inspector.ping() or {}
            active_data = inspector.active() or {}
            stats_data = inspector.stats() or {}

            worker_nodes = []
            active_tasks = []
            now_ts = time.time()

            for worker_name, ping_res in ping_data.items():
                stats = stats_data.get(worker_name, {})
                active_for_worker = active_data.get(worker_name, [])
                total_processed = stats.get("total", {})
                processed_count = sum(total_processed.values()) if isinstance(total_processed, dict) else "-"

                worker_nodes.append({
                    "name": worker_name,
                    "status": "Online" if ping_res else "Offline",
                    "concurrency": stats.get("pool", {}).get("max-concurrency", "-"),
                    "active_count": len(active_for_worker),
                    "processed_count": processed_count,
                })

            for worker_name, tasks in active_data.items():
                for t in tasks:
                    start_ts = t.get("time_start")
                    elapsed_sec = max(0.0, now_ts - float(start_ts)) if start_ts else None
                    active_tasks.append({
                        "worker": worker_name,
                        "id": t.get("id", ""),
                        "name": t.get("name", "Unknown"),
                        "start_time": datetime.fromtimestamp(start_ts, tz=dt_timezone.utc).strftime("%H:%M:%S UTC") if start_ts else "-",
                        "elapsed_seconds": elapsed_sec,
                        "elapsed_display": format_elapsed_time(elapsed_sec) if elapsed_sec is not None else "-",
                        "args": str(t.get("args", "-"))[:150],
                        "kwargs": str(t.get("kwargs", ""))[:150] if t.get("kwargs") else "",
                    })

            return active_tasks, worker_nodes, ""
        except Exception as e:
            return [], [], f"Celery workers offline or unreachable: {str(e)}"

    # -------------------------------------------------------------------------
    # Database In-Flight Pipeline & Component Runs
    # -------------------------------------------------------------------------
    def get_db_active_runs(self) -> tuple[list[dict], list[dict], list[dict]]:
        """
        Queries running and pending ComponentRuns and PipelineRuns from the database.
        Returns (running_components, running_pipelines, pending_components).
        """
        now = timezone.now()

        # Running ComponentRuns
        running_components = []
        try:
            cr_qs = (
                ComponentRun.objects.filter(status="running")
                .select_related("pipeline_run", "scraper", "pipeline_run__workspace")
                .order_by("started_at")[:50]
            )
            for cr in cr_qs:
                started = cr.started_at
                elapsed_sec = (now - started).total_seconds() if started else 0.0
                ws_name = cr.pipeline_run.workspace.name if cr.pipeline_run and cr.pipeline_run.workspace else "-"
                pr_name = cr.pipeline_run.name if cr.pipeline_run else "-"

                running_components.append({
                    "id": str(cr.id),
                    "component_name": cr.component_name,
                    "step_type": cr.step_type,
                    "workspace": ws_name,
                    "pipeline_run_name": pr_name,
                    "pipeline_run_id": str(cr.pipeline_run_id) if cr.pipeline_run_id else "",
                    "celery_task_id": cr.celery_task_id or "-",
                    "started_at_str": started.strftime("%H:%M:%S (%Y-%m-%d)") if started else "-",
                    "elapsed_seconds": elapsed_sec,
                    "elapsed_display": format_elapsed_time(elapsed_sec),
                    "is_stalled": elapsed_sec > 1800,  # 30 minutes threshold
                    "details": cr.input_params or {},
                })
        except Exception as e:
            logger.debug(f"Error fetching running ComponentRuns: {e}")

        # Running PipelineRuns
        running_pipelines = []
        try:
            pr_qs = (
                PipelineRun.objects.filter(status="running")
                .select_related("workspace")
                .order_by("started_at")[:30]
            )
            for pr in pr_qs:
                started = pr.started_at
                elapsed_sec = (now - started).total_seconds() if started else 0.0
                running_pipelines.append({
                    "id": str(pr.id),
                    "name": pr.name or f"Run #{pr.id}",
                    "workspace": pr.workspace.name if pr.workspace else "-",
                    "current_stage": pr.current_stage or "initialized",
                    "started_at_str": started.strftime("%H:%M:%S (%Y-%m-%d)") if started else "-",
                    "elapsed_seconds": elapsed_sec,
                    "elapsed_display": format_elapsed_time(elapsed_sec),
                    "total_papers": pr.total_papers_fetched or 0,
                    "is_stalled": elapsed_sec > 7200,  # 2 hours threshold
                })
        except Exception as e:
            logger.debug(f"Error fetching running PipelineRuns: {e}")

        # Pending ComponentRuns
        pending_components = []
        try:
            pend_qs = (
                ComponentRun.objects.filter(status="pending")
                .select_related("pipeline_run", "pipeline_run__workspace")
                .order_by("started_at")[:30]
            )
            for pc in pend_qs:
                created = pc.started_at
                wait_sec = (now - created).total_seconds() if created else 0.0
                pending_components.append({
                    "id": str(pc.id),
                    "component_name": pc.component_name,
                    "step_type": pc.step_type,
                    "workspace": pc.pipeline_run.workspace.name if pc.pipeline_run and pc.pipeline_run.workspace else "-",
                    "pipeline_run_name": pc.pipeline_run.name if pc.pipeline_run else "-",
                    "waiting_display": format_elapsed_time(wait_sec),
                })
        except Exception as e:
            logger.debug(f"Error fetching pending ComponentRuns: {e}")

        return running_components, running_pipelines, pending_components

    # -------------------------------------------------------------------------
    # Request Dispatcher & HTML Renderer
    # -------------------------------------------------------------------------
    def get(self, request):
        action = request.GET.get("action")
        base_url = reverse("admin:queue-monitor")

        # Optional action: Trigger Zombie Watchdog immediately
        if action == "run_watchdog":
            try:
                res = reap_zombie_tasks()
                reaped_comp = res.get("reaped_components", 0)
                reaped_pipe = res.get("reaped_pipelines", 0)
                messages.success(
                    request,
                    f"🧹 Zombie Watchdog executed successfully: Reaped {reaped_comp} stalled component(s) and {reaped_pipe} pipeline run(s)."
                )
            except Exception as e:
                messages.error(request, f"Error executing Zombie Watchdog: {str(e)}")
            return HttpResponseRedirect(base_url)

        # 1. Fetch data from all subsystems
        redis_client = self.get_redis_client()
        queue_summaries, queued_messages, redis_error = self.get_queue_statistics(redis_client)
        active_celery_tasks, worker_nodes, celery_error = self.get_celery_worker_data()
        running_components, running_pipelines, pending_components = self.get_db_active_runs()

        total_queued_messages = sum(q["count"] for q in queue_summaries)
        total_active_tasks = len(active_celery_tasks) + len(running_components)
        total_running_pipelines = len(running_pipelines)
        online_workers_count = len([w for w in worker_nodes if w["status"] == "Online"])

        # Auto-refresh parameter
        refresh_sec = request.GET.get("refresh", "0")
        if not refresh_sec.isdigit() or int(refresh_sec) not in (0, 5, 10, 30, 60):
            refresh_sec = "0"
        refresh_val = int(refresh_sec)

        # -------------------------------------------------------------------------
        # Template Rendering (Integrated into Django Admin)
        # -------------------------------------------------------------------------
        context = {
            **admin.site.each_context(request),
            "title": "Queue & Active Runs",
            "last_updated_str": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
            "auto_refresh_seconds": refresh_val,
            "redis_error": redis_error,
            "celery_error": celery_error,
            "total_queued_messages": total_queued_messages,
            "total_active_tasks": total_active_tasks,
            "total_running_pipelines": total_running_pipelines,
            "online_workers_count": online_workers_count,
            "queue_summaries": queue_summaries,
            "queued_messages": queued_messages,
            "active_celery_tasks": active_celery_tasks,
            "running_components": running_components,
            "running_pipelines": running_pipelines,
            "pending_components": pending_components,
            "worker_nodes": worker_nodes,
        }

        response = TemplateResponse(
            request,
            "admin/research_intelligence/queue_monitor.html",
            context,
        )
        response["X-Frame-Options"] = "SAMEORIGIN"
        return response


queue_monitor_view = QueueMonitorView.as_view()
