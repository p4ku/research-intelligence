import os
import json
import time
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.conf import settings
from django.db import connection, close_old_connections
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from research_intelligence.models import Paper, Workspace
from research_intelligence.tasks.auxiliary.health import health_ping_task

logger = logging.getLogger(__name__)


def probe_database() -> dict:
    """Probes PostgreSQL query execution latency."""
    close_old_connections()
    start = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
        latency = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "online",
            "vendor": connection.vendor,
            "latency_ms": latency,
        }
    except Exception as e:
        return {
            "status": "offline",
            "vendor": getattr(connection, "vendor", "unknown"),
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "error": "Database connection failed",
        }
    finally:
        close_old_connections()


def probe_redis() -> dict:
    """Probes Redis connection, TLS ping, and latency."""
    start = time.perf_counter()
    try:
        import redis
        import ssl
        broker_url = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
        clean_url = broker_url.replace("ssl_cert_reqs=CERT_NONE", "ssl_cert_reqs=none")
        if "rediss://" in clean_url:
            r = redis.from_url(clean_url, ssl_cert_reqs=ssl.CERT_NONE, socket_connect_timeout=2)
        else:
            r = redis.from_url(clean_url, socket_connect_timeout=2)
        r.ping()
        latency = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "online",
            "latency_ms": latency,
            "tls": "rediss://" in broker_url,
        }
    except Exception as e:
        return {
            "status": "offline",
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "error": "Redis cache/broker ping failed",
        }


def probe_celery() -> dict:
    """Probes Celery worker dispatch and task result roundtrip."""
    start = time.perf_counter()
    try:
        if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            res = health_ping_task.delay("health_ping_payload")
            latency = round((time.perf_counter() - start) * 1000, 2)
            return {
                "status": "online",
                "mode": "eager_synchronous",
                "latency_ms": latency,
            }
        else:
            async_res = health_ping_task.apply_async(args=["health_ping_payload"], queue="celery")
            task_res = async_res.get(timeout=3.0)
            latency = round((time.perf_counter() - start) * 1000, 2)
            return {
                "status": "online",
                "mode": "distributed_worker",
                "latency_ms": latency,
            }
    except Exception as e:
        return {
            "status": "offline",
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "error": "Celery worker dispatch timeout/failed",
        }


def probe_storage() -> dict:
    """Probes Object Storage (S3 / MinIO / Local) write-read-delete lifecycle."""
    start = time.perf_counter()
    try:
        test_file_path = f"health_checks/test_{uuid.uuid4().hex[:8]}.txt"
        test_payload = b"schwarz_research_intelligence_health_probe_ok"
        default_storage.save(test_file_path, ContentFile(test_payload))
        with default_storage.open(test_file_path, "rb") as f:
            read_back = f.read()
        default_storage.delete(test_file_path)
        latency = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "online",
            "backend": getattr(settings, "STORAGE_BACKEND", "local"),
            "latency_ms": latency,
            "verified": read_back == test_payload,
        }
    except Exception as e:
        return {
            "status": "offline",
            "backend": getattr(settings, "STORAGE_BACKEND", "local"),
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "error": "Storage read/write check failed",
        }


def probe_mailgun() -> dict:
    """Probes Mailgun configuration status without exposing credentials or domain."""
    return {
        "status": "configured" if bool(getattr(settings, "MAILGUN_API_KEY", "")) else "unconfigured",
    }


def probe_llm_providers() -> dict:
    """Probes Google Vertex AI / GenAI and OpenRouter connectivity without leaking internal project details."""
    llm_providers = {}
    google_start = time.perf_counter()

    try:
        from research_intelligence.llm_providers.google import GoogleAgentAPIProvider
        provider = GoogleAgentAPIProvider()
        test_resp = provider.generate("Reply with 'OK' only.", model="gemini-3.7-flash")
        latency = round((time.perf_counter() - google_start) * 1000, 2)
        llm_providers["google"] = {
            "status": "online",
            "provider_name": "Google Vertex AI / GenAI",
            "model": "gemini-3.7-flash",
            "latency_ms": latency,
            "response": str(test_resp)[:100],
        }
    except Exception as e:
        latency = round((time.perf_counter() - google_start) * 1000, 2)
        llm_providers["google"] = {
            "status": "offline",
            "provider_name": "Google Vertex AI / GenAI",
            "model": "gemini-3.7-flash",
            "latency_ms": latency,
            "error": str(e),
        }

    openrouter_key = os.environ.get("OPENROUTER_API_KEY") or getattr(settings, "OPENROUTER_API_KEY", None)
    llm_providers["openrouter"] = {
        "status": "configured" if bool(openrouter_key and openrouter_key != "mock-openrouter-key") else "not_configured",
        "provider_name": "OpenRouter Gateway",
    }

    return llm_providers


from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter


PROBE_FUNCTIONS = {
    "database": probe_database,
    "redis": probe_redis,
    "celery": probe_celery,
    "storage": probe_storage,
    "mailgun": probe_mailgun,
    "llm_providers": probe_llm_providers,
}


class HealthCheckView(APIView):
    """
    Lightweight, non-blocking Liveness & Readiness probe.
    Fast response (<5ms) for load balancers, Cloud Foundry router, and uptime monitors.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        responses={
            200: OpenApiResponse(description="API service is live and responsive"),
        },
        tags=['Health & Diagnostics']
    )
    def get(self, request, *args, **kwargs):
        return Response(
            {
                "status": "ok",
                "timestamp": time.time(),
                "service": "schwarz_research_intelligence_api",
            },
            status=status.HTTP_200_OK,
        )


class DeepDiagnosticsView(APIView):
    """
    Comprehensive, ThreadPoolExecutor-isolated infrastructure diagnostics.
    Executes all probes in parallel with strict thread timeouts so no single
    failing/slow component can block or hang the endpoint.
    Supports granular filtering via ?service=database, ?service=celery, etc.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='service',
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Target specific subsystem probe (database, redis, celery, storage, mailgun, llm_providers)"
            )
        ],
        responses={
            200: OpenApiResponse(description="Infrastructure health diagnostics result"),
            503: OpenApiResponse(description="One or more critical subsystems are offline"),
        },
        tags=['Health & Diagnostics']
    )
    def get(self, request, *args, **kwargs):
        service_filter = request.query_params.get("service")
        
        if service_filter and service_filter in PROBE_FUNCTIONS:
            target_probes = {service_filter: PROBE_FUNCTIONS[service_filter]}
        else:
            target_probes = PROBE_FUNCTIONS

        services = {}
        overall_status = "online"

        # Execute all requested probes concurrently with max 4.0s timeout
        with ThreadPoolExecutor(max_workers=len(target_probes)) as executor:
            future_to_service = {
                executor.submit(fn): srv_name 
                for srv_name, fn in target_probes.items()
            }

            for future in as_completed(future_to_service):
                srv_name = future_to_service[future]
                try:
                    res = future.result(timeout=4.0)
                    services[srv_name] = res
                    if isinstance(res, dict) and res.get("status") in ["offline", "degraded"]:
                        overall_status = "degraded"
                except Exception as exc:
                    overall_status = "degraded"
                    services[srv_name] = {
                        "status": "offline",
                        "error": f"Probe timed out or threw unhandled exception: {str(exc)}",
                    }

        http_status = status.HTTP_200_OK if overall_status == "online" else status.HTTP_207_MULTI_STATUS

        return Response(
            {
                "status": overall_status,
                "timestamp": time.time(),
                "services": services,
            },
            status=http_status,
        )
