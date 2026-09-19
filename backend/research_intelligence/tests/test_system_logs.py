import json
import logging
from unittest.mock import MagicMock, patch
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from research_intelligence.logging_handlers import (
    RedisLogHandler,
    get_current_component,
    get_current_instance_id,
    REDIS_STREAM_KEY,
)
from research_intelligence.admin_views.system_logs import SystemLogsView, system_logs_view


class ComponentAndInstanceDetectionTests(TestCase):
    def test_get_current_component_override(self):
        with patch.dict("os.environ", {"SRI_COMPONENT": "worker"}):
            self.assertEqual(get_current_component(), "worker")

        with patch.dict("os.environ", {"SRI_COMPONENT": "api"}):
            self.assertEqual(get_current_component(), "api")

    def test_get_current_component_sys_argv(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.argv", ["celery", "-A", "django_project", "worker"]):
                self.assertEqual(get_current_component(), "worker")
            with patch("sys.argv", ["celery", "-A", "django_project", "beat"]):
                self.assertEqual(get_current_component(), "beat")
            with patch("sys.argv", ["python", "manage.py", "run_mcp"]):
                self.assertEqual(get_current_component(), "mcp")
            with patch("sys.argv", ["gunicorn", "django_project.wsgi:application"]):
                self.assertEqual(get_current_component(), "api")

    def test_get_current_instance_id_cf_index(self):
        with patch.dict("os.environ", {"SRI_COMPONENT": "worker", "CF_INSTANCE_INDEX": "2"}):
            self.assertEqual(get_current_instance_id(), "worker-2")

    def test_get_current_instance_id_pod_name(self):
        with patch.dict("os.environ", {"SRI_COMPONENT": "api", "POD_NAME": "sri-api-deploy-7b9d-4x8k"}):
            self.assertEqual(get_current_instance_id(), "sri-api-deploy-7b9d-4x8k")


class RedisLogHandlerTests(TestCase):
    def setUp(self):
        self.handler = RedisLogHandler(level=logging.INFO)
        self.mock_redis = MagicMock()
        self.handler._redis_client = self.mock_redis

    def test_emit_writes_to_redis_stream(self):
        record = logging.LogRecord(
            name="research_intelligence.tasks.step_1_search",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Processing query 'quantum computing' on %s candidate papers",
            args=(42,),
            exc_info=None,
        )
        self.handler.emit(record)

        self.assertTrue(self.mock_redis.xadd.called)
        args, kwargs = self.mock_redis.xadd.call_args
        self.assertEqual(args[0], REDIS_STREAM_KEY)
        payload = args[1]
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["logger"], "research_intelligence.tasks.step_1_search")
        self.assertIn("Processing query 'quantum computing' on 42 candidate papers", payload["message"])
        self.assertIn("timestamp", payload)
        self.assertIn("component", payload)
        self.assertIn("instance", payload)
        self.assertEqual(kwargs.get("maxlen"), 10000)

    def test_emit_circuit_breaker_on_failure(self):
        self.mock_redis.xadd.side_effect = Exception("Redis connection refused")

        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Failure test",
            args=(),
            exc_info=None,
        )

        # Emit 3 times to trigger circuit breaker
        for _ in range(3):
            self.handler.emit(record)

        self.assertGreater(self.handler._circuit_broken_until, 0)
        call_count = self.mock_redis.xadd.call_count

        # 4th emit should skip calling Redis entirely due to open circuit breaker
        self.handler.emit(record)
        self.assertEqual(self.mock_redis.xadd.call_count, call_count)


class SystemLogsViewPermissionsTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.superuser = User.objects.create_superuser(
            username="admin_user",
            email="admin@example.com",
            password="admin_password",
        )
        self.staff_user = User.objects.create_user(
            username="staff_user",
            email="staff@example.com",
            password="staff_password",
            is_staff=True,
            is_superuser=False,
        )
        self.normal_user = User.objects.create_user(
            username="normal_user",
            email="normal@example.com",
            password="normal_password",
            is_staff=False,
            is_superuser=False,
        )

    def test_anonymous_user_redirected_to_login(self):
        from django.contrib.auth.models import AnonymousUser

        req = self.factory.get("/admin/system-logs/")
        req.user = AnonymousUser()
        resp = system_logs_view(req)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login", resp["Location"])

    def test_staff_non_superuser_rejected_with_403_on_api(self):
        req = self.factory.get("/admin/system-logs/?format=json")
        req.user = self.staff_user
        resp = system_logs_view(req)
        self.assertEqual(resp.status_code, 403)
        data = json.loads(resp.content.decode("utf-8"))
        self.assertFalse(data.get("success"))
        self.assertIn("Superuser access required", data.get("error"))

    def test_staff_non_superuser_redirected_on_html(self):
        from django.contrib.messages.storage.fallback import FallbackStorage

        req = self.factory.get("/admin/system-logs/")
        req.user = self.staff_user
        setattr(req, "session", {})
        setattr(req, "_messages", FallbackStorage(req))
        resp = system_logs_view(req)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login", resp["Location"])

    @patch("research_intelligence.admin_views.system_logs.SystemLogsView.get_redis_client")
    def test_superuser_access_allowed_html(self, mock_redis_fn):
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.xlen.return_value = 100
        mock_redis_fn.return_value = mock_redis

        req = self.factory.get("/admin/system-logs/")
        req.user = self.superuser
        setattr(req, "session", {})
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(req, "_messages", FallbackStorage(req))

        resp = system_logs_view(req)
        self.assertEqual(resp.status_code, 200)

    @patch("research_intelligence.admin_views.system_logs.SystemLogsView.get_redis_client")
    def test_superuser_access_allowed_json_stream(self, mock_redis_fn):
        mock_redis = MagicMock()
        mock_redis.xlen.return_value = 2
        mock_redis.xrevrange.return_value = [
            (
                "1726738910000-0",
                {
                    "timestamp": "2026-09-19 10:00:00.000",
                    "component": "worker",
                    "instance": "sri-worker-0",
                    "level": "INFO",
                    "logger": "tasks.ocr",
                    "message": "OCR conversion started",
                    "task_id": "abc-123",
                },
            ),
            (
                "1726738920000-0",
                {
                    "timestamp": "2026-09-19 10:00:10.000",
                    "component": "api",
                    "instance": "sri-api-1",
                    "level": "ERROR",
                    "logger": "api.views",
                    "message": "Rate limit reached",
                    "task_id": "",
                },
            ),
        ]
        mock_redis_fn.return_value = mock_redis

        req = self.factory.get("/admin/system-logs/?format=json")
        req.user = self.superuser
        resp = system_logs_view(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode("utf-8"))
        self.assertTrue(data.get("success"))
        self.assertEqual(len(data.get("logs")), 2)
        self.assertIn("sri-worker-0", data.get("instances"))
        self.assertIn("sri-api-1", data.get("instances"))

    @patch("research_intelligence.admin_views.system_logs.SystemLogsView.get_redis_client")
    def test_superuser_stream_filtering_component_and_level(self, mock_redis_fn):
        mock_redis = MagicMock()
        mock_redis.xlen.return_value = 3
        mock_redis.xrevrange.return_value = [
            (
                "1-0",
                {
                    "timestamp": "2026-09-19 10:00:00",
                    "component": "worker",
                    "instance": "sri-worker-0",
                    "level": "INFO",
                    "message": "Worker log 1",
                },
            ),
            (
                "2-0",
                {
                    "timestamp": "2026-09-19 10:00:05",
                    "component": "worker",
                    "instance": "sri-worker-0",
                    "level": "ERROR",
                    "message": "Worker failure",
                },
            ),
            (
                "3-0",
                {
                    "timestamp": "2026-09-19 10:00:10",
                    "component": "api",
                    "instance": "sri-api-0",
                    "level": "ERROR",
                    "message": "API error",
                },
            ),
        ]
        mock_redis_fn.return_value = mock_redis

        # Filter: component=worker, level=ERROR
        req = self.factory.get("/admin/system-logs/?format=json&component=worker&level=ERROR")
        req.user = self.superuser
        resp = system_logs_view(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode("utf-8"))
        logs = data.get("logs")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["message"], "Worker failure")
        self.assertEqual(logs[0]["component"], "worker")
        self.assertEqual(logs[0]["level"], "ERROR")

    @patch("research_intelligence.admin_views.system_logs.SystemLogsView.get_redis_client")
    def test_superuser_clear_buffer(self, mock_redis_fn):
        mock_redis = MagicMock()
        mock_redis_fn.return_value = mock_redis

        req = self.factory.post("/admin/system-logs/", {"action": "clear"})
        req.user = self.superuser
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(req, "session", {})
        setattr(req, "_messages", FallbackStorage(req))

        resp = system_logs_view(req)
        self.assertEqual(resp.status_code, 302)
        mock_redis.delete.assert_called_once_with(REDIS_STREAM_KEY)

    @patch("research_intelligence.admin_views.system_logs.SystemLogsView.get_redis_client")
    def test_superuser_export_logs_txt(self, mock_redis_fn):
        mock_redis = MagicMock()
        mock_redis.xlen.return_value = 1
        mock_redis.xrevrange.return_value = [
            (
                "1-0",
                {
                    "timestamp": "2026-09-19 10:00:00",
                    "component": "worker",
                    "instance": "sri-worker-0",
                    "level": "INFO",
                    "logger": "tasks.screening",
                    "message": "Screening completed successfully",
                },
            ),
        ]
        mock_redis_fn.return_value = mock_redis

        req = self.factory.get("/admin/system-logs/?action=export")
        req.user = self.superuser
        resp = system_logs_view(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("attachment; filename=", resp["Content-Disposition"])
        body = resp.content.decode("utf-8")
        self.assertIn("[worker:sri-worker-0]", body)
        self.assertIn("Screening completed successfully", body)
