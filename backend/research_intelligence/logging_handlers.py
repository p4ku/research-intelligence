import logging
import os
import socket
import ssl
import sys
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

REDIS_STREAM_KEY = "sri:system:logs:stream"
MAX_STREAM_ENTRIES = 10000


def get_current_component() -> str:
    """Detects whether this process is running as a worker, api, beat, or mcp component."""
    override = os.environ.get("SRI_COMPONENT")
    if override:
        return override.strip().lower()

    cmd = " ".join(sys.argv).lower()
    if "celery" in cmd:
        if "beat" in cmd:
            return "beat"
        return "worker"
    if "run_mcp" in cmd:
        return "mcp"
    return "api"


def get_current_instance_id() -> str:
    """
    Resolves the pod or instance identifier across Cloud Foundry, Kubernetes, Docker, and bare-metal.
    Examples: sri-worker-0, sri-api-2, or host-abc123.
    """
    comp = get_current_component()

    # Cloud Foundry instance index
    cf_index = os.environ.get("CF_INSTANCE_INDEX")
    if cf_index is not None:
        return f"{comp}-{cf_index}"

    # Kubernetes pod name
    pod_name = os.environ.get("POD_NAME")
    if pod_name:
        return pod_name

    # Hostname (Docker container ID or VM hostname)
    hostname = os.environ.get("HOSTNAME") or socket.gethostname() or "node-1"
    short_host = hostname.split(".")[0][:14]
    return f"{comp}-{short_host}"


class RedisLogHandler(logging.Handler):
    """
    State-of-the-art distributed log handler that emits structured log entries
    into a capped Redis Stream (sri:system:logs:stream).
    Aggregates logs from multiple API and Worker pods without requiring external network sidecars.
    Includes an automatic circuit breaker to fail gracefully and silently if Redis is unreachable.
    """

    def __init__(self, level=logging.INFO, maxlen: int = MAX_STREAM_ENTRIES):
        super().__init__(level)
        self.maxlen = maxlen
        self.component = get_current_component()
        self.instance_id = get_current_instance_id()
        self._redis_client = None
        self._circuit_broken_until = 0.0
        self._consecutive_failures = 0

    def _get_redis_client(self):
        if self._redis_client is not None:
            return self._redis_client

        try:
            import redis
            from django.conf import settings

            broker_url = (
                getattr(settings, "CELERY_BROKER_URL", None)
                or os.environ.get("REDIS_URL")
                or "redis://localhost:6379/0"
            )
            clean_url = str(broker_url).replace("ssl_cert_reqs=CERT_NONE", "ssl_cert_reqs=none")
            if "rediss://" in clean_url:
                self._redis_client = redis.from_url(
                    clean_url,
                    ssl_cert_reqs=ssl.CERT_NONE,
                    socket_connect_timeout=0.5,
                    socket_timeout=0.5,
                    decode_responses=True,
                )
            else:
                self._redis_client = redis.from_url(
                    clean_url,
                    socket_connect_timeout=0.5,
                    socket_timeout=0.5,
                    decode_responses=True,
                )
            return self._redis_client
        except Exception:
            return None

    def emit(self, record: logging.LogRecord):
        # Circuit breaker: skip if recently failed repeatedly
        now = time.time()
        if now < self._circuit_broken_until:
            return

        # Filter out noisy internal logging from redis/kombu/urllib to prevent recursive logging loops
        if record.name.startswith(("redis", "urllib3", "kombu", "django.db.backends")):
            return

        try:
            r = self._get_redis_client()
            if r is None:
                return

            task_id = getattr(record, "task_id", "")
            if not task_id:
                try:
                    from celery import current_task
                    if current_task and getattr(current_task, "request", None):
                        task_id = str(current_task.request.id or "")
                except Exception:
                    pass

            formatted_msg = self.format(record)

            payload = {
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "component": self.component,
                "instance": self.instance_id,
                "level": record.levelname,
                "logger": record.name,
                "message": formatted_msg,
                "task_id": task_id,
            }

            r.xadd(
                REDIS_STREAM_KEY,
                payload,
                maxlen=self.maxlen,
                approximate=True,
            )
            self._consecutive_failures = 0
        except Exception:
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                # Open circuit breaker for 5 seconds to prevent performance degradation
                self._circuit_broken_until = now + 5.0
                self._redis_client = None
