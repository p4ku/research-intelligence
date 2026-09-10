import base64
import json
import logging
import os
import ssl
import time
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
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
        # HTML Building
        # -------------------------------------------------------------------------
        # Render Django Messages
        from django.contrib.messages import get_messages
        msg_html = ""
        for m in get_messages(request):
            tag = m.tags or "info"
            bg = "#f8d7da" if "error" in tag else ("#d1e7dd" if "success" in tag else "#fff3cd")
            border = "#f5c2c7" if "error" in tag else ("#badbcc" if "success" in tag else "#ffecb5")
            color = "#842029" if "error" in tag else ("#0f5132" if "success" in tag else "#664d03")
            msg_html += f'<div style="margin-bottom: 12px; padding: 10px 14px; border-radius: 4px; background-color: {bg}; border: 1px solid {border}; color: {color}; font-size: 13px;">{escape(str(m))}</div>'

        # Alerts if Redis or Celery error
        system_warnings = ""
        if redis_error:
            system_warnings += f"""
            <div style="margin-bottom: 16px; padding: 12px 16px; background-color: #fff3cd; border: 1px solid #ffecb5; border-radius: 6px; color: #664d03; font-size: 13px;">
                ⚠️ <strong>Redis Broker Warning:</strong> {escape(redis_error)}. Real-time message queue introspection is paused.
            </div>
            """
        if celery_error and not redis_error:
            system_warnings += f"""
            <div style="margin-bottom: 16px; padding: 12px 16px; background-color: #e2e3e5; border: 1px solid #d3d6d8; border-radius: 6px; color: #383d41; font-size: 13px;">
                ℹ️ <strong>Celery Inspector Info:</strong> {escape(celery_error)}. In-flight status is being reported directly from the database.
            </div>
            """

        # Auto-refresh script tag
        auto_refresh_meta = f'<meta http-equiv="refresh" content="{refresh_val}">' if refresh_val > 0 else ""

        # Stat Badges HTML
        def _render_stat_card(icon: str, label: str, value: Any, color: str, subtext: str = "") -> str:
            return f"""
            <div style="flex: 1; min-width: 200px; background: #fff; border: 1px solid #dee2e6; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-right: 12px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-size: 13px; font-weight: 600; color: #6c757d; text-transform: uppercase;">{label}</span>
                    <span style="font-size: 20px;">{icon}</span>
                </div>
                <div style="font-size: 28px; font-weight: bold; color: {color}; line-height: 1.1;">{value}</div>
                {f'<div style="font-size: 12px; color: #6c757d; margin-top: 6px;">{subtext}</div>' if subtext else ''}
            </div>
            """

        stat_cards = f"""
        <div style="display: flex; flex-wrap: wrap; margin-bottom: 16px;">
            {_render_stat_card('🏃', 'Aktywne Zadania', total_active_tasks, '#0d6efd' if total_active_tasks > 0 else '#495057', f'{len(running_components)} w bazie · {len(active_celery_tasks)} w workerach')}
            {_render_stat_card('📬', 'Wiadomości w Kolejce', total_queued_messages, '#fd7e14' if total_queued_messages > 0 else '#198754', 'Oczekujące na podjęcie')}
            {_render_stat_card('🚀', 'Aktywne Pipeline Runs', total_running_pipelines, '#6f42c1' if total_running_pipelines > 0 else '#495057', 'In-flight badania SLR')}
            {_render_stat_card('🖥️', 'Workery Celery', online_workers_count, '#198754' if online_workers_count > 0 else '#dc3545', f'{online_workers_count} z {len(worker_nodes)} online')}
        </div>
        """

        # Table 1: In-Flight Active ComponentRuns (Database + Celery Worker)
        running_tasks_rows = ""
        if running_components:
            for c in running_components:
                badge_bg = "#dc3545" if c["is_stalled"] else ("#0d6efd" if c["elapsed_seconds"] < 300 else "#ffc107")
                badge_color = "#fff" if c["is_stalled"] or c["elapsed_seconds"] < 300 else "#000"
                warning_label = " ⚠️ Długi czas (>30m)" if c["is_stalled"] else ""
                admin_link = f"/admin/research_intelligence/componentrun/{c['id']}/change/"
                pr_admin_link = f"/admin/research_intelligence/pipelinerun/{c['pipeline_run_id']}/change/" if c['pipeline_run_id'] else "#"

                running_tasks_rows += f"""
                <tr style="border-bottom: 1px solid #eee;">
                    <td style="padding: 10px 12px; font-weight: 600;">
                        <a href="{admin_link}" style="color: #0d6efd; text-decoration: none;">⚙️ {escape(c['component_name'])}</a>
                        <div style="font-size: 11px; color: #6c757d; font-weight: normal;">Krok: <strong>{escape(c['step_type'])}</strong></div>
                    </td>
                    <td style="padding: 10px 12px; font-size: 13px;">
                        <a href="{pr_admin_link}" style="color: #495057; text-decoration: none; font-weight: 500;">{escape(c['pipeline_run_name'])}</a>
                        <div style="font-size: 11px; color: #6c757d;">WS: {escape(c['workspace'])}</div>
                    </td>
                    <td style="padding: 10px 12px; font-size: 12px; font-family: monospace; color: #495057;">
                        {escape(c['celery_task_id'][:18])}...
                    </td>
                    <td style="padding: 10px 12px; font-size: 13px; color: #6c757d;">
                        {escape(c['started_at_str'])}
                    </td>
                    <td style="padding: 10px 12px;">
                        <span style="display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; background-color: {badge_bg}; color: {badge_color};">
                            ⏳ {escape(c['elapsed_display'])}{warning_label}
                        </span>
                    </td>
                    <td style="padding: 10px 12px; text-align: right;">
                        <a href="{admin_link}" style="display: inline-block; padding: 4px 8px; border: 1px solid #0d6efd; color: #0d6efd; border-radius: 4px; font-size: 12px; text-decoration: none;">🔍 Zobacz w Adminie</a>
                    </td>
                </tr>
                """
        elif active_celery_tasks:
            # Fallback to Celery active tasks if database is empty
            for at in active_celery_tasks:
                running_tasks_rows += f"""
                <tr style="border-bottom: 1px solid #eee;">
                    <td style="padding: 10px 12px; font-weight: 600;">
                        ⚙️ {escape(at['name'])}
                        <div style="font-size: 11px; color: #6c757d;">Worker: {escape(at['worker'])}</div>
                    </td>
                    <td style="padding: 10px 12px; font-size: 12px; font-family: monospace;">{escape(at['id'][:20])}</td>
                    <td style="padding: 10px 12px; font-size: 12px; color: #6c757d;" colspan="2">{escape(at['start_time'])}</td>
                    <td style="padding: 10px 12px;">
                        <span style="display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; background-color: #0d6efd; color: #fff;">
                            ⏳ {escape(at['elapsed_display'])}
                        </span>
                    </td>
                    <td style="padding: 10px 12px; text-align: right;">-</td>
                </tr>
                """
        else:
            running_tasks_rows = """
            <tr>
                <td colspan="6" style="padding: 24px; text-align: center; color: #6c757d; font-size: 14px;">
                    ✨ Brak aktywnych zadań. Wszyscy workerzy oczekują na nowe zlecenia w kolejce.
                </td>
            </tr>
            """

        # Table 2: Queues and Messages in Redis
        queue_summary_html = ""
        for q in queue_summaries:
            is_active = q["count"] > 0
            badge_bg = "#fd7e14" if is_active else "#6c757d"
            queue_summary_html += f"""
            <div style="display: inline-block; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; padding: 8px 14px; margin-right: 10px; margin-bottom: 8px; font-size: 13px;">
                <strong>{escape(q['name'])}</strong>: 
                <span style="display: inline-block; background: {badge_bg}; color: #fff; padding: 2px 8px; border-radius: 10px; font-weight: bold; font-size: 12px; margin-left: 4px;">
                    {q['count']}
                </span>
            </div>
            """

        queued_messages_rows = ""
        if queued_messages:
            for qm in queued_messages:
                queued_messages_rows += f"""
                <tr style="border-bottom: 1px solid #eee;">
                    <td style="padding: 8px 12px; font-size: 12px; font-weight: bold; color: #fd7e14;">#{qm['position']}</td>
                    <td style="padding: 8px 12px; font-size: 12px;">
                        <span style="background: #e9ecef; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{escape(qm['queue'])}</span>
                    </td>
                    <td style="padding: 8px 12px; font-size: 13px; font-weight: 600; color: #212529;">
                        {escape(qm['task'])}
                        <div style="font-size: 11px; color: #6c757d; font-family: monospace;">ID: {escape(qm['id'])}</div>
                    </td>
                    <td style="padding: 8px 12px; font-size: 12px; color: #495057; font-family: monospace;">
                        {escape(qm['args'][:120])}
                    </td>
                    <td style="padding: 8px 12px; font-size: 12px; color: #6c757d;">
                        {escape(str(qm['eta'])) if qm['eta'] else 'Natychmiast'}
                    </td>
                </tr>
                """
        else:
            queued_messages_rows = """
            <tr>
                <td colspan="5" style="padding: 20px; text-align: center; color: #6c757d; font-size: 13px;">
                    🎉 Kolejki są puste. Żadne zadania nie oczekują na przetworzenie w brokerze.
                </td>
            </tr>
            """

        # Table 3: Active Pipeline Runs
        active_pipeline_rows = ""
        if running_pipelines:
            for pr in running_pipelines:
                badge_bg = "#dc3545" if pr["is_stalled"] else "#6f42c1"
                pr_link = f"/admin/research_intelligence/pipelinerun/{pr['id']}/change/"
                active_pipeline_rows += f"""
                <tr style="border-bottom: 1px solid #eee;">
                    <td style="padding: 10px 12px;">
                        <a href="{pr_link}" style="color: #6f42c1; font-weight: bold; text-decoration: none;">🚀 {escape(pr['name'])}</a>
                        <div style="font-size: 11px; color: #6c757d;">ID: {escape(pr['id'])}</div>
                    </td>
                    <td style="padding: 10px 12px; font-size: 13px;">{escape(pr['workspace'])}</td>
                    <td style="padding: 10px 12px; font-size: 13px;">
                        <span style="background: #e7f1ff; color: #0c63e4; padding: 3px 8px; border-radius: 4px; font-weight: 500;">
                            {escape(pr['current_stage'])}
                        </span>
                    </td>
                    <td style="padding: 10px 12px; font-size: 13px; color: #6c757d;">{escape(pr['started_at_str'])}</td>
                    <td style="padding: 10px 12px;">
                        <span style="display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; background-color: {badge_bg}; color: #fff;">
                            ⏳ {escape(pr['elapsed_display'])}
                        </span>
                    </td>
                    <td style="padding: 10px 12px; text-align: right;">
                        <a href="{pr_link}" style="display: inline-block; padding: 4px 8px; border: 1px solid #6f42c1; color: #6f42c1; border-radius: 4px; font-size: 12px; text-decoration: none;">Szczegóły Run-a</a>
                    </td>
                </tr>
                """
        else:
            active_pipeline_rows = """
            <tr>
                <td colspan="6" style="padding: 20px; text-align: center; color: #6c757d; font-size: 13px;">
                    Brak uruchomionych pipeline runs w stanie 'running'.
                </td>
            </tr>
            """

        # Table 4: Celery Worker Nodes
        worker_nodes_rows = ""
        if worker_nodes:
            for w in worker_nodes:
                is_online = w["status"] == "Online"
                status_color = "#198754" if is_online else "#dc3545"
                worker_nodes_rows += f"""
                <tr style="border-bottom: 1px solid #eee;">
                    <td style="padding: 8px 12px; font-weight: 600;">🖥️ {escape(w['name'])}</td>
                    <td style="padding: 8px 12px;">
                        <span style="color: {status_color}; font-weight: bold;">● {w['status']}</span>
                    </td>
                    <td style="padding: 8px 12px; font-size: 13px;">{w['concurrency']} worker process(es)</td>
                    <td style="padding: 8px 12px; font-size: 13px;">{w['active_count']} active</td>
                    <td style="padding: 8px 12px; font-size: 13px; color: #6c757d;">{w['processed_count']} tasks</td>
                </tr>
                """
        else:
            worker_nodes_rows = """
            <tr>
                <td colspan="5" style="padding: 16px; text-align: center; color: #6c757d; font-size: 13px;">
                    Nie wykryto zarejestrowanych węzłów Celery (worker processes mogą być uśpione lub brak łączności z brokerem).
                </td>
            </tr>
            """

        # Auto-refresh selector helper
        def _refresh_btn(seconds: int, label: str) -> str:
            is_selected = refresh_val == seconds
            bg = "#0d6efd" if is_selected else "#f8f9fa"
            color = "#fff" if is_selected else "#495057"
            border = "#0d6efd" if is_selected else "#ced4da"
            return f'<a href="{base_url}?refresh={seconds}" style="display: inline-block; padding: 4px 10px; margin-left: 4px; border: 1px solid {border}; background-color: {bg}; color: {color} !important; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: {"bold" if is_selected else "normal"};">{label}</a>'

        refresh_controls = f"""
        <div style="display: flex; align-items: center; font-size: 12px; color: #6c757d;">
            <span>⏱️ Auto-odświeżanie:</span>
            {_refresh_btn(0, 'Wył.')}
            {_refresh_btn(5, '5s')}
            {_refresh_btn(10, '10s')}
            {_refresh_btn(30, '30s')}
        </div>
        """

        current_time_str = timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC")

        # Full HTML Document
        html = f"""
        <!DOCTYPE html>
        <html lang="pl">
        <head>
            <meta charset="utf-8">
            <title>⚡ Kolejki & Aktywne Runy | SRI Admin</title>
            {auto_refresh_meta}
            <style>
                body {{
                    margin: 0;
                    padding: 20px;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    background-color: #f4f6f8;
                    color: #212529;
                }}
                .card {{
                    background: #fff;
                    border: 1px solid #dee2e6;
                    border-radius: 8px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
                    margin-bottom: 24px;
                    overflow: hidden;
                }}
                .card-header {{
                    padding: 12px 18px;
                    background-color: #f8f9fa;
                    border-bottom: 1px solid #dee2e6;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }}
                .card-header h2 {{
                    margin: 0;
                    font-size: 15px;
                    font-weight: 700;
                    color: #343a40;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    text-align: left;
                }}
                th {{
                    background-color: #f8f9fa;
                    color: #495057;
                    font-size: 12px;
                    text-transform: uppercase;
                    padding: 10px 12px;
                    border-bottom: 2px solid #dee2e6;
                }}
                .btn {{
                    display: inline-block;
                    padding: 6px 12px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: 600;
                    text-decoration: none;
                    cursor: pointer;
                    line-height: 1.2;
                    white-space: nowrap;
                }}
            </style>
        </head>
        <body>
            <!-- Top Navigation Bar -->
            <div style="background: #fff; border: 1px solid #dee2e6; border-radius: 8px; padding: 14px 20px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,0.05); flex-wrap: wrap; gap: 12px;">
                <div>
                    <h1 style="margin: 0; font-size: 18px; font-weight: bold; color: #212529; display: flex; align-items: center; gap: 8px;">
                        ⚡ <span>Kolejki & Aktywne Runy Workerów</span>
                        <span style="font-size: 12px; font-weight: normal; color: #6c757d; background: #e9ecef; padding: 2px 8px; border-radius: 12px;">Live Monitor</span>
                    </h1>
                    <div style="font-size: 12px; color: #6c757d; margin-top: 4px;">
                        Ostatnia aktualizacja: <strong>{current_time_str}</strong>
                    </div>
                </div>

                <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                    {refresh_controls}
                    <a href="{base_url}?refresh={refresh_val}" class="btn" style="background: #0d6efd; color: #fff;">🔄 Odśwież</a>
                    <a href="{base_url}?action=run_watchdog" class="btn" style="background: #6c757d; color: #fff;" onclick="return confirm('Czy na pewno chcesz uruchomić Zombie Watchdog i wyczyścić zadania przekraczające limit czasu?');">🧹 Zombie Watchdog</a>
                    <a href="/admin/storage-browser/" class="btn" style="background: #f8f9fa; color: #495057; border: 1px solid #ced4da;">📂 S3 Storage</a>
                    <a href="/admin/" class="btn" style="background: #f8f9fa; color: #495057; border: 1px solid #ced4da;">🏠 Django Admin</a>
                </div>
            </div>

            {msg_html}
            {system_warnings}
            {stat_cards}

            <!-- SECTION 1: Aktywne Zadania & Przetwarzający Workery -->
            <div class="card">
                <div class="card-header">
                    <h2>🏃 Aktywne Zadania Workerów (In-Progress Tasks)</h2>
                    <span style="font-size: 12px; color: #6c757d;">Liczba: {len(running_components)} w DB / {len(active_celery_tasks)} w Celery</span>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Zadanie / Komponent</th>
                            <th>Pipeline Run & Workspace</th>
                            <th>Celery Task ID</th>
                            <th>Start Time</th>
                            <th>Czas Trwania (Elapsed)</th>
                            <th style="text-align: right;">Akcje</th>
                        </tr>
                    </thead>
                    <tbody>
                        {running_tasks_rows}
                    </tbody>
                </table>
            </div>

            <!-- SECTION 2: Wiadomości w Kolejkach Celery (Redis) -->
            <div class="card">
                <div class="card-header">
                    <h2>📬 Wiadomości w Kolejkach Brokera (Redis Queues)</h2>
                    <div>{queue_summary_html}</div>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th style="width: 50px;">Poz.</th>
                            <th style="width: 140px;">Kolejka</th>
                            <th>Zadanie Celery</th>
                            <th>Argumenty & Parametry</th>
                            <th style="width: 120px;">ETA</th>
                        </tr>
                    </thead>
                    <tbody>
                        {queued_messages_rows}
                    </tbody>
                </table>
            </div>

            <!-- SECTION 3: Aktywne Badania SLR (Pipeline Runs) -->
            <div class="card">
                <div class="card-header">
                    <h2>🚀 Aktywne Badania SLR (Pipeline Runs in 'Running' State)</h2>
                    <span style="font-size: 12px; color: #6c757d;">Liczba: {len(running_pipelines)}</span>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Nazwa Pipeline Run</th>
                            <th>Workspace</th>
                            <th>Aktualny Krok</th>
                            <th>Data Rozpoczęcia</th>
                            <th>Czas Trwania</th>
                            <th style="text-align: right;">Akcje</th>
                        </tr>
                    </thead>
                    <tbody>
                        {active_pipeline_rows}
                    </tbody>
                </table>
            </div>

            <!-- SECTION 4: Status Węzłów Workerów (Celery Nodes) -->
            <div class="card">
                <div class="card-header">
                    <h2>🖥️ Węzły Celery Worker (Active Worker Nodes)</h2>
                    <span style="font-size: 12px; color: #6c757d;">Online: {online_workers_count}</span>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Nazwa Węzła (Node)</th>
                            <th>Status</th>
                            <th>Współbieżność (Concurrency)</th>
                            <th>Aktywne Taski</th>
                            <th>Wykonane Taski</th>
                        </tr>
                    </thead>
                    <tbody>
                        {worker_nodes_rows}
                    </tbody>
                </table>
            </div>
        </body>
        </html>
        """

        resp = HttpResponse(html)
        resp["X-Frame-Options"] = "SAMEORIGIN"
        return resp


queue_monitor_view = QueueMonitorView.as_view()
