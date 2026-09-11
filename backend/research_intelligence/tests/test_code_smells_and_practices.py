"""
Unit tests for Code Smells & Implementation Practices:
1. Audit logging query count optimization (no cascading N+1 lookups).
2. Audit logging resolution via pipeline_run, URL regex, and output_summary.
3. Middleware safe handling of multipart form requests and sensitive data redaction.
4. Middleware ignoring non-API endpoints and tracking unauthorized/failed requests.
5. Database connection cleanup in worker threads on error and on success.
6. Non-blocking Celery dispatch failure handling in production mode vs eager fallback.
"""

import json
from unittest.mock import MagicMock, patch
from django.test import TestCase, RequestFactory, override_settings
from django.http import HttpResponse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from research_intelligence.models import (
    Workspace,
    Paper,
    PipelineRun,
    ComponentRun,
    UserActivityLog
)
from api.middleware import UserActionAuditMiddleware
from research_intelligence.tasks.orchestrator.dag.base_node import BaseWorkflowNode
from research_intelligence.tasks.step_5_extraction.extract import _run_single_extraction_worker

User = get_user_model()


class DummyWorkflowNode(BaseWorkflowNode):
    @property
    def name(self) -> str:
        return "dummy_node"

    def execute(self, pipeline_run, comp_run, limit=None):
        return {}


class CodeSmellsAndPracticesTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="smell_tester", email="smell@example.com")
        self.workspace = Workspace.objects.create(name="Smell Test WS")
        self.pipeline_run = PipelineRun.objects.create(workspace=self.workspace)
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="dummy_paper_hash_smell",
            title="Test Paper Smell"
        )
        self.factory = RequestFactory()

    # -------------------------------------------------------------------------
    # 1. AUDIT LOGGING QUERY & RESOLUTION TESTS
    # -------------------------------------------------------------------------

    def test_audit_log_workspace_resolution_does_not_cascade(self):
        """
        Verify that passing workspace_id or paper_id directly in input_params
        resolves the workspace in at most 1 query without cascading across 7 other tables.
        """
        # 1. Direct workspace resolution
        with self.assertNumQueries(2):  # 1 for Workspace.objects.filter(id=...), 1 for UserActivityLog.objects.create(...)
            UserActivityLog.log_action(
                action_name="test_action_direct_ws",
                user=self.user,
                input_params={"workspace_id": str(self.workspace.id)}
            )

        # 2. Paper-based resolution (1 query with select_related('workspace') + 1 for log create)
        with self.assertNumQueries(2):
            UserActivityLog.log_action(
                action_name="test_action_paper_res",
                user=self.user,
                input_params={"paper_id": str(self.paper.id)}
            )

        # 3. No workspace keys in input_params -> 0 entity queries (only 1 query to insert log)
        with self.assertNumQueries(1):
            UserActivityLog.log_action(
                action_name="test_action_no_ws",
                user=self.user,
                input_params={"unrelated_key": "some_value"}
            )

    def test_audit_log_resolution_via_pipeline_run_and_url_regex(self):
        """
        Verify that workspace is correctly resolved when passed via pipeline_run_id,
        REST URL regex, or output_summary.
        """
        # 1. Resolve via pipeline_run_id
        log1 = UserActivityLog.log_action(
            action_name="test_pr_resolve",
            user=self.user,
            input_params={"pipeline_run_id": str(self.pipeline_run.id)}
        )
        self.assertEqual(log1.workspace, self.workspace)

        # 2. Resolve via REST URL regex
        log2 = UserActivityLog.log_action(
            action_name=f"GET /api/workspaces/{self.workspace.id}/papers/",
            user=self.user
        )
        self.assertEqual(log2.workspace, self.workspace)

        # 3. Resolve via output_summary for create_workspace
        log3 = UserActivityLog.log_action(
            action_name="create_workspace",
            user=self.user,
            output_summary={"id": str(self.workspace.id), "name": "Smell Test WS"}
        )
        self.assertEqual(log3.workspace, self.workspace)

    # -------------------------------------------------------------------------
    # 2. MIDDLEWARE SAFETY & REDACTION TESTS
    # -------------------------------------------------------------------------

    def test_middleware_multipart_does_not_crash_or_read_raw_body(self):
        """
        Verify that UserActionAuditMiddleware handles multipart/form-data requests
        without reading raw request.body or raising RawPostDataException.
        """
        middleware = UserActionAuditMiddleware(lambda req: HttpResponse(b'{"status": "ok"}', content_type="application/json"))
        pdf_file = SimpleUploadedFile("sample.pdf", b"%PDF-1.4 test binary", content_type="application/pdf")

        request = self.factory.post(
            "/api/workspaces/upload-paper/",
            data={"title": "Uploaded via form", "file": pdf_file}
        )
        request.user = self.user

        # process_request must not touch request.body
        middleware.process_request(request)
        self.assertFalse(hasattr(request, '_cached_body'))

        # process_response must handle multipart form keys safely
        response = HttpResponse(b'{"status": "uploaded"}', content_type="application/json", status=201)
        res = middleware.process_response(request, response)
        self.assertEqual(res.status_code, 201)

        # Verify activity log was recorded with form data without crashing
        log = UserActivityLog.objects.filter(action_name="POST /api/workspaces/upload-paper/").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, "success")
        self.assertIn("title", log.input_params)

    def test_middleware_sensitive_payload_redaction(self):
        """
        Verify that passwords, tokens, and api_keys in request bodies
        are redacted in the audit log.
        """
        middleware = UserActionAuditMiddleware(lambda req: HttpResponse(b'{"ok": true}', content_type="application/json"))
        body_dict = {
            "username": "tester",
            "password": "SuperSecretPassword123!",
            "api_key": "sensitive_key_val",
            "token": "bearer_token_xyz"
        }
        request = self.factory.post(
            "/api/auth/login/",
            data=json.dumps(body_dict),
            content_type="application/json"
        )
        request.user = self.user

        middleware.process_request(request)
        response = HttpResponse(b'{"token": "new_secret_token"}', content_type="application/json", status=200)
        middleware.process_response(request, response)

        log = UserActivityLog.objects.filter(action_name="POST /api/auth/login/").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.input_params.get("password"), "[REDACTED]")
        self.assertEqual(log.input_params.get("api_key"), "[REDACTED]")
        self.assertEqual(log.input_params.get("token"), "[REDACTED]")
        self.assertEqual(log.input_params.get("username"), "tester")
        # Response bodies are not stored at all, redacted or otherwise
        self.assertNotIn("token", log.output_summary)
        self.assertNotIn("new_secret_token", json.dumps(log.output_summary))

    def test_middleware_ignores_non_api_endpoints(self):
        """
        Verify that requests to non-API paths (e.g. /schema/, /health/) are ignored by middleware.
        """
        middleware = UserActionAuditMiddleware(lambda req: HttpResponse(b"OK"))
        request = self.factory.get("/api/schema/")
        request.user = self.user

        middleware.process_request(request)
        response = HttpResponse(b"Schema YAML", content_type="text/yaml")
        middleware.process_response(request, response)

        self.assertFalse(UserActivityLog.objects.filter(action_name="GET /api/schema/").exists())

    def test_middleware_tracks_unauthorized_and_failed_responses(self):
        """
        Verify that 401/403 responses are marked 'unauthorized' and 500 responses are marked 'failed'.
        """
        middleware = UserActionAuditMiddleware(lambda req: HttpResponse(b"Error"))

        # 1. 401 Unauthorized
        req401 = self.factory.get("/api/workspaces/restricted/")
        res401 = HttpResponse(b'{"error": "Invalid credentials"}', content_type="application/json", status=401)
        middleware.process_request(req401)
        middleware.process_response(req401, res401)

        log401 = UserActivityLog.objects.filter(action_name="GET /api/workspaces/restricted/").first()
        self.assertIsNotNone(log401)
        self.assertEqual(log401.status, "unauthorized")

        # 2. 500 Server Error
        req500 = self.factory.post("/api/papers/search/", data=json.dumps({"q": "ai"}), content_type="application/json")
        req500.user = self.user
        res500 = HttpResponse(b'{"error": "Database error"}', content_type="application/json", status=500)
        middleware.process_request(req500)
        middleware.process_response(req500, res500)

        log500 = UserActivityLog.objects.filter(action_name="POST /api/papers/search/").first()
        self.assertIsNotNone(log500)
        self.assertEqual(log500.status, "failed")

    # -------------------------------------------------------------------------
    # 3. CELERY DISPATCH FAILURE & FALLBACK TESTS
    # -------------------------------------------------------------------------

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_celery_dispatch_in_production_fails_cleanly_without_synchronous_hang(self):
        """
        Verify that in production (CELERY_TASK_ALWAYS_EAGER=False), if Celery broker
        is unreachable, dispatch_celery_task marks comp_run as failed rather than
        blocking the thread synchronously.
        """
        node = DummyWorkflowNode()
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type='search',
            component_name='test_comp',
            status='running'
        )

        mock_task = MagicMock()
        mock_task.delay.side_effect = Exception("Connection to Redis broker refused")

        node.dispatch_celery_task(mock_task, comp_run)

        # In production mode with broker failure:
        # 1. mock_task must NOT be called synchronously
        mock_task.assert_not_called()
        # 2. comp_run must be marked failed
        comp_run.refresh_from_db()
        self.assertEqual(comp_run.status, "failed")
        self.assertIn("Celery broker dispatch failed", comp_run.error_message)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_celery_dispatch_multiple_tasks_in_production_fails_cleanly(self):
        """
        Verify that dispatch_multiple_celery_tasks cleanly marks all tasks as failed
        without synchronous execution if the broker fails.
        """
        node = DummyWorkflowNode()
        comp_run1 = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type='search',
            component_name='test_scraper_1',
            status='running'
        )
        comp_run2 = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type='search',
            component_name='test_scraper_2',
            status='running'
        )

        mock_task = MagicMock()
        mock_task.delay.side_effect = Exception("Redis broker down")

        node.dispatch_multiple_celery_tasks(mock_task, [comp_run1, comp_run2])

        mock_task.assert_not_called()
        comp_run1.refresh_from_db()
        comp_run2.refresh_from_db()
        self.assertEqual(comp_run1.status, "failed")
        self.assertEqual(comp_run2.status, "failed")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_celery_dispatch_in_eager_mode_falls_back_to_synchronous(self):
        """
        Verify that under test environments (CELERY_TASK_ALWAYS_EAGER=True),
        if delay fails, task_func is called synchronously as intended.
        """
        node = DummyWorkflowNode()
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type='search',
            component_name='test_eager_comp',
            status='running'
        )

        mock_task = MagicMock()
        mock_task.delay.side_effect = Exception("Delay mock error")

        node.dispatch_celery_task(mock_task, comp_run, limit=5)

        # In eager mode, synchronous fallback is executed
        mock_task.assert_called_once_with(str(comp_run.id), limit=5)

    # -------------------------------------------------------------------------
    # 4. WORKER THREAD DATABASE CONNECTION CLEANUP TESTS
    # -------------------------------------------------------------------------

    @patch('research_intelligence.tasks.step_5_extraction.extract.close_old_connections')
    @patch('research_intelligence.tasks.step_5_extraction.extract._run_single_extraction_impl')
    def test_extraction_worker_thread_cleans_db_connections_in_finally_on_error(self, mock_impl, mock_close):
        """
        Verify that _run_single_extraction_worker calls close_old_connections in a finally block
        even if an exception is raised during extraction.
        """
        mock_impl.side_effect = RuntimeError("Worker simulated crash")
        mock_def = MagicMock()

        with self.assertRaises(RuntimeError):
            _run_single_extraction_worker(self.paper, mock_def, self.workspace)

        # close_old_connections must be called at least twice (at start and in finally)
        self.assertTrue(mock_close.call_count >= 2)

    @patch('research_intelligence.tasks.step_5_extraction.extract.close_old_connections')
    @patch('research_intelligence.tasks.step_5_extraction.extract._run_single_extraction_impl')
    def test_extraction_worker_thread_cleans_db_connections_in_finally_on_success(self, mock_impl, mock_close):
        """
        Verify that _run_single_extraction_worker calls close_old_connections in a finally block
        when extraction completes normally.
        """
        mock_impl.return_value = {"success": True}
        mock_def = MagicMock()

        res = _run_single_extraction_worker(self.paper, mock_def, self.workspace)
        self.assertTrue(res["success"])
        self.assertTrue(mock_close.call_count >= 2)
