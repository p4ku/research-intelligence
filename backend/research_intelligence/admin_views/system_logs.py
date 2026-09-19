import json
import logging
import os
import re
import ssl
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.middleware.csrf import get_token
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_sameorigin

from research_intelligence.logging_handlers import REDIS_STREAM_KEY

logger = logging.getLogger(__name__)


@method_decorator(xframe_options_sameorigin, name="dispatch")
class SystemLogsView(View):
    """
    Superuser-restricted Django Admin View for real-time log aggregation across
    all API and Worker pods/instances via Redis Streams.
    """

    def dispatch(self, request, *args, **kwargs):
        # Strictly require superuser access
        if not request.user.is_authenticated or not request.user.is_superuser:
            is_ajax = (
                request.GET.get("format") == "json"
                or request.headers.get("x-requested-with") == "XMLHttpRequest"
                or request.method == "POST"
            )
            if is_ajax:
                return JsonResponse({"success": False, "error": "Forbidden: Superuser access required."}, status=403)
            try:
                messages.error(request, "Access restricted to superusers only.", fail_silently=True)
            except Exception:
                pass
            return HttpResponseRedirect(reverse("admin:login"))
        return super().dispatch(request, *args, **kwargs)

    @classmethod
    def get_redis_client(cls):
        try:
            import redis

            broker_url = (
                getattr(settings, "CELERY_BROKER_URL", None)
                or os.environ.get("REDIS_URL")
                or "redis://localhost:6379/0"
            )
            clean_url = str(broker_url).replace("ssl_cert_reqs=CERT_NONE", "ssl_cert_reqs=none")
            if "rediss://" in clean_url:
                r = redis.from_url(
                    clean_url,
                    ssl_cert_reqs=ssl.CERT_NONE,
                    socket_connect_timeout=1.5,
                    socket_timeout=1.5,
                    decode_responses=True,
                )
            else:
                r = redis.from_url(
                    clean_url,
                    socket_connect_timeout=1.5,
                    socket_timeout=1.5,
                    decode_responses=True,
                )
            r.ping()
            return r
        except Exception as e:
            logger.debug(f"Redis connection failed in SystemLogsView: {e}")
            return None

    def _fetch_logs(
        self,
        redis_client,
        last_id: Optional[str] = None,
        limit: int = 250,
        component_filter: Optional[str] = None,
        level_filter: Optional[str] = None,
        instance_filter: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], str, List[str], int]:
        """
        Queries Redis Stream for log records, applying filters.
        Returns (logs, latest_id, active_instances, total_count).
        """
        if redis_client is None:
            return [], "", [], 0

        logs: List[Dict[str, Any]] = []
        instances_set = set()
        total_in_stream = 0

        try:
            total_in_stream = redis_client.xlen(REDIS_STREAM_KEY)
        except Exception:
            pass

        try:
            if last_id:
                # Forward streaming: fetch records strictly greater than last_id
                # In Redis, '(' prefix excludes the boundary ID
                raw_entries = redis_client.xrange(REDIS_STREAM_KEY, min=f"({last_id}", max="+", count=limit)
            else:
                # Initial view: fetch latest N records in reverse, then reverse back to chronological
                raw_entries = redis_client.xrevrange(REDIS_STREAM_KEY, max="+", min="-", count=limit)
                raw_entries = list(reversed(raw_entries))

            comp_filter_clean = component_filter.strip().lower() if component_filter and component_filter != "all" else None
            level_filter_clean = level_filter.strip().upper() if level_filter and level_filter != "ALL" else None
            inst_filter_clean = instance_filter.strip() if instance_filter and instance_filter != "all" else None
            search_clean = search_query.strip().lower() if search_query else None

            search_regex = None
            if search_clean:
                try:
                    search_regex = re.compile(re.escape(search_clean), re.IGNORECASE)
                except Exception:
                    pass

            latest_id = last_id or ""
            for msg_id, fields in raw_entries:
                latest_id = msg_id
                inst = fields.get("instance", "unknown")
                instances_set.add(inst)

                comp = fields.get("component", "api").lower()
                lvl = fields.get("level", "INFO").upper()

                if comp_filter_clean and comp != comp_filter_clean:
                    continue
                if level_filter_clean and lvl != level_filter_clean:
                    continue
                if inst_filter_clean and inst != inst_filter_clean:
                    continue

                msg_text = fields.get("message", "")
                logger_name = fields.get("logger", "")
                task_id = fields.get("task_id", "")

                if search_regex:
                    corpus = f"{msg_text} {logger_name} {task_id} {inst}"
                    if not search_regex.search(corpus):
                        continue

                logs.append({
                    "id": msg_id,
                    "timestamp": fields.get("timestamp", ""),
                    "component": comp,
                    "instance": inst,
                    "level": lvl,
                    "logger": logger_name,
                    "message": msg_text,
                    "task_id": task_id,
                })

            return logs, latest_id, sorted(list(instances_set)), total_in_stream

        except Exception as e:
            logger.warning(f"Error reading Redis log stream: {e}")
            return [], last_id or "", [], total_in_stream

    def get(self, request):
        redis_client = self.get_redis_client()
        action = request.GET.get("action")

        # Handle Clear action via GET or POST
        if action == "clear":
            if redis_client:
                try:
                    redis_client.delete(REDIS_STREAM_KEY)
                    messages.success(request, "Live log buffer cleared successfully.")
                except Exception as e:
                    messages.error(request, f"Failed to clear log buffer: {e}")
            return HttpResponseRedirect(reverse("admin:system-logs"))

        # Handle Export action (.txt file download)
        if action == "export":
            component = request.GET.get("component", "all")
            level = request.GET.get("level", "ALL")
            search = request.GET.get("search", "")
            logs, _, _, _ = self._fetch_logs(
                redis_client,
                last_id=None,
                limit=2000,
                component_filter=component,
                level_filter=level,
                search_query=search,
            )
            text_lines = []
            for item in logs:
                task_part = f" [task:{item['task_id']}]" if item.get("task_id") else ""
                text_lines.append(
                    f"{item['timestamp']} [{item['level']}] [{item['component']}:{item['instance']}]{task_part} {item['logger']}: {item['message']}"
                )
            content = "\n".join(text_lines)
            resp = HttpResponse(content, content_type="text/plain; charset=utf-8")
            timestamp_slug = datetime.now().strftime("%Y%m%d_%H%M%S")
            resp["Content-Disposition"] = f'attachment; filename="sri_system_logs_{timestamp_slug}.txt"'
            return resp

        # Handle AJAX JSON stream endpoint
        is_ajax = (
            request.GET.get("format") == "json"
            or request.headers.get("x-requested-with") == "XMLHttpRequest"
            or "application/json" in request.headers.get("Accept", "")
        )
        if is_ajax:
            last_id = request.GET.get("last_id") or None
            component = request.GET.get("component", "all")
            level = request.GET.get("level", "ALL")
            instance = request.GET.get("instance", "all")
            search = request.GET.get("search", "")
            limit_param = request.GET.get("limit", "250")
            limit = int(limit_param) if limit_param.isdigit() else 250

            logs, latest_id, instances, total_count = self._fetch_logs(
                redis_client,
                last_id=last_id,
                limit=min(limit, 1000),
                component_filter=component,
                level_filter=level,
                instance_filter=instance,
                search_query=search,
            )
            return JsonResponse({
                "success": True,
                "logs": logs,
                "last_id": latest_id,
                "instances": instances,
                "total_buffered": total_count,
                "redis_online": bool(redis_client),
            })

        # HTML Shell View
        context = {
            **admin.site.each_context(request),
            "title": "System Live Logs (API & Worker)",
            "csrf_token": get_token(request),
            "redis_online": bool(redis_client),
            "now_str": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return TemplateResponse(request, "admin/research_intelligence/system_logs.html", context)

    def post(self, request):
        # Clearing logs via POST
        action = request.POST.get("action")
        if action == "clear":
            redis_client = self.get_redis_client()
            if redis_client:
                try:
                    redis_client.delete(REDIS_STREAM_KEY)
                    if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.GET.get("format") == "json":
                        return JsonResponse({"success": True, "message": "Logs cleared."})
                    messages.success(request, "Log buffer cleared successfully.")
                except Exception as e:
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return JsonResponse({"success": False, "error": str(e)}, status=500)
                    messages.error(request, f"Error clearing logs: {e}")
            return HttpResponseRedirect(reverse("admin:system-logs"))

        return JsonResponse({"error": "Unknown POST action."}, status=400)


def system_logs_view(request, *args, **kwargs):
    return SystemLogsView.as_view()(request, *args, **kwargs)
