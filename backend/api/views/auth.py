from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken
from ..serializers.auth import LoginSerializer
from research_intelligence.models import APIKey


class LoginView(APIView):
    """
    Authenticates via MCP API key and returns JWT tokens with the real user_id.
    The api_key must be in format 'key_id:secret' and must match an active APIKey.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            api_key_raw = serializer.validated_data['api_key']
            workspace_id = serializer.validated_data['workspace_id']

            # Validate API key against APIKey model
            # Expected format: "key_id:secret" or just "secret" for legacy compat
            parts = api_key_raw.split(':', 1)
            if len(parts) == 2:
                key_id, secret = parts
                try:
                    api_key_obj = APIKey.objects.select_related('user').get(
                        key_id=key_id, is_active=True
                    )
                except APIKey.DoesNotExist:
                    return Response(
                        {"error": "Invalid API key."},
                        status=status.HTTP_401_UNAUTHORIZED
                    )
                if not api_key_obj.check_secret(secret):
                    return Response(
                        {"error": "Invalid API key secret."},
                        status=status.HTTP_401_UNAUTHORIZED
                    )
            else:
                # Legacy: try to find by matching hashed secret across all active keys
                import hashlib
                hashed = hashlib.sha256(api_key_raw.encode()).hexdigest()
                try:
                    api_key_obj = APIKey.objects.select_related('user').get(
                        hashed_secret=hashed, is_active=True
                    )
                except APIKey.DoesNotExist:
                    return Response(
                        {"error": "Invalid API key."},
                        status=status.HTTP_401_UNAUTHORIZED
                    )

            user = api_key_obj.user
            api_key_obj.update_last_used()

            # Generate token with real user_id
            refresh = RefreshToken.for_user(user)
            refresh['workspace_id'] = str(workspace_id)

            return Response(
                {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "workspace_id": workspace_id,
                    "user_id": user.id,
                    "username": user.username
                },
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class WorkspaceTokenRefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=True)
    access = serializers.CharField(read_only=True)

    def validate(self, attrs):
        try:
            refresh = RefreshToken(attrs['refresh'])
            data = {'access': str(refresh.access_token)}
            return data
        except Exception as e:
            raise InvalidToken(str(e))

class TokenRefreshView(APIView):
    """
    Regenerates a fresh access token given a valid SimpleJWT refresh token,
    without executing database user queries.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = WorkspaceTokenRefreshSerializer(data=request.data)
        if serializer.is_valid():
            return Response(serializer.validated_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)


import time
import uuid
import logging
from django.conf import settings
from django.db import connection
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from research_intelligence.models import Paper, Workspace
from research_intelligence.tasks.auxiliary.health import health_ping_task

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """
    Public end-to-end infrastructure diagnostics and health check endpoint.
    Performs active read/write/ping probes across:
    1. PostgreSQL Database (Query execution, latency, paper/workspace counts)
    2. Redis Cache & Broker (PING probe, latency)
    3. Celery Asynchronous Workers (Dispatches and awaits result of health_ping_task)
    4. Object Storage (S3 / MinIO / Local write-read-delete lifecycle probe)
    5. Mailgun Transactional Email Gateway configuration
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        services = {}
        overall_status = "online"

        # 1. Database Probe
        db_start = time.perf_counter()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
            papers_count = Paper.objects.count()
            workspaces_count = Workspace.objects.count()
            db_latency = round((time.perf_counter() - db_start) * 1000, 2)
            services["database"] = {
                "status": "online",
                "vendor": connection.vendor,
                "latency_ms": db_latency,
                "counts": {
                    "papers": papers_count,
                    "workspaces": workspaces_count,
                },
            }
        except Exception as e:
            overall_status = "degraded"
            services["database"] = {
                "status": "offline",
                "vendor": getattr(connection, "vendor", "unknown"),
                "latency_ms": round((time.perf_counter() - db_start) * 1000, 2),
                "error": str(e),
            }

        # 2. Redis Probe
        redis_start = time.perf_counter()
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
            redis_latency = round((time.perf_counter() - redis_start) * 1000, 2)
            services["redis"] = {
                "status": "online",
                "latency_ms": redis_latency,
                "scheme": "rediss (TLS)" if "rediss://" in broker_url else "redis",
            }
        except Exception as e:
            overall_status = "degraded"
            services["redis"] = {
                "status": "offline",
                "latency_ms": round((time.perf_counter() - redis_start) * 1000, 2),
                "error": str(e),
            }


        # 3. Celery Worker Probe
        celery_start = time.perf_counter()
        try:
            if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
                res = health_ping_task.delay("health_ping_payload")
                celery_latency = round((time.perf_counter() - celery_start) * 1000, 2)
                services["celery"] = {
                    "status": "online",
                    "mode": "eager_synchronous",
                    "latency_ms": celery_latency,
                    "task_id": res.id,
                    "result": res.result,
                }
            else:
                async_res = health_ping_task.apply_async(args=["health_ping_payload"], queue="celery")
                task_res = async_res.get(timeout=3)
                celery_latency = round((time.perf_counter() - celery_start) * 1000, 2)
                services["celery"] = {
                    "status": "online",
                    "mode": "distributed_worker",
                    "latency_ms": celery_latency,
                    "task_id": async_res.id,
                    "result": task_res,
                }
        except Exception as e:
            overall_status = "degraded"
            services["celery"] = {
                "status": "offline",
                "latency_ms": round((time.perf_counter() - celery_start) * 1000, 2),
                "error": str(e),
            }

        # 4. Storage Probe (S3 / Local Read-Write-Delete)
        storage_start = time.perf_counter()
        try:
            test_file_path = f"health_checks/test_{uuid.uuid4().hex[:8]}.txt"
            test_payload = b"schwarz_research_intelligence_health_probe_ok"
            default_storage.save(test_file_path, ContentFile(test_payload))
            with default_storage.open(test_file_path, "rb") as f:
                read_back = f.read()
            default_storage.delete(test_file_path)
            storage_latency = round((time.perf_counter() - storage_start) * 1000, 2)
            services["storage"] = {
                "status": "online",
                "backend": getattr(settings, "STORAGE_BACKEND", "local"),
                "bucket": getattr(settings, "AWS_STORAGE_BUCKET_NAME", "local_storage"),
                "latency_ms": storage_latency,
                "verified": read_back == test_payload,
            }
        except Exception as e:
            overall_status = "degraded"
            services["storage"] = {
                "status": "offline",
                "backend": getattr(settings, "STORAGE_BACKEND", "local"),
                "bucket": getattr(settings, "AWS_STORAGE_BUCKET_NAME", "local_storage"),
                "latency_ms": round((time.perf_counter() - storage_start) * 1000, 2),
                "error": str(e),
            }

        # 5. Mailgun Email Gateway Status
        services["mailgun"] = {
            "status": "configured" if bool(getattr(settings, "MAILGUN_API_KEY", "")) else "unconfigured",
            "sender_domain": getattr(settings, "MAILGUN_SENDER_DOMAIN", "soinventive.co.uk"),
            "api_url": getattr(settings, "MAILGUN_API_URL", "https://api.eu.mailgun.net/v3"),
        }

        # 6. LLM Providers Diagnostics
        llm_providers = {}
        google_start = time.perf_counter()
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        sa_email = None
        sa_project = None
        if sa_json:
            try:
                import json
                parsed_sa = json.loads(sa_json)
                sa_email = parsed_sa.get("client_email")
                sa_project = parsed_sa.get("project_id")
            except Exception:
                pass

        try:
            from research_intelligence.llm_providers.google import GoogleAgentAPIProvider
            provider = GoogleAgentAPIProvider(location="eu")
            # Quick validation prompt
            test_resp = provider.generate("Reply with 'OK' only.", model="gemini-3.7-flash")
            google_latency = round((time.perf_counter() - google_start) * 1000, 2)
            llm_providers["google"] = {
                "status": "online",
                "provider_name": "Google Vertex AI / GenAI",
                "model": "gemini-3.7-flash",
                "location": getattr(provider, "location", "eu"),
                "project_id": getattr(provider, "project_id", sa_project),
                "service_account_email": sa_email,
                "latency_ms": google_latency,
                "sample_response": str(test_resp).strip()[:100],
            }
        except Exception as e:
            google_latency = round((time.perf_counter() - google_start) * 1000, 2)
            llm_providers["google"] = {
                "status": "offline",
                "provider_name": "Google Vertex AI / GenAI",
                "model": "gemini-3.7-flash",
                "location": "eu",
                "project_id": sa_project,
                "service_account_email": sa_email,
                "latency_ms": google_latency,
                "error": str(e),
            }

        # OpenRouter (Multi-model Gateway - planned)
        openrouter_key = os.environ.get("OPENROUTER_API_KEY") or getattr(settings, "OPENROUTER_API_KEY", None)
        llm_providers["openrouter"] = {
            "status": "configured" if bool(openrouter_key and openrouter_key != "mock-openrouter-key") else "not_configured",
            "provider_name": "OpenRouter Gateway",
            "supported_models": ["anthropic/claude-3.5-sonnet", "deepseek/deepseek-r1", "openai/o3-mini"],
            "note": "Multi-provider LLM gateway fallback",
        }

        services["llm_providers"] = llm_providers

        http_status = status.HTTP_200_OK if overall_status == "online" else status.HTTP_207_MULTI_STATUS

        return Response(
            {
                "status": overall_status,
                "timestamp": time.time(),
                "services": services,
            },
            status=http_status
        )


