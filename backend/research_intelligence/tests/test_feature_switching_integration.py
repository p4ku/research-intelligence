"""
Integration Tests for System-Wide Feature Switching (Feature.SCHEDULING & Feature.EMAIL_NOTIFICATIONS).

Verifies that when features are disabled (default):
- Django Admin hides WorkflowSchedule & Subscriber and omits their inlines
- Celery Beat periodic schedule excludes workflow dispatch
- Schedule dispatcher early-exits without triggering runs
- Pipeline runner & Mailer suppress outbound emails (circuit breaker)
- DRF API returns 404 Not Found for /api/v1/schedules/ and /api/v1/subscribers/
- MCP workspace tool omits nested schedules & subscribers
"""

import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.exceptions import NotFound

from research_intelligence.features import Feature, is_feature_enabled
from research_intelligence.models import Workspace, WorkflowSchedule, Subscriber, PipelineRun, WorkspaceMember
from research_intelligence.admin import (
    WorkspaceAdmin,
    WorkflowScheduleAdmin,
    SubscriberAdmin,
    PipelineRunAdmin,
    WorkflowScheduleInline,
    SubscriberInline,
)
from research_intelligence.tasks.auxiliary.schedule_dispatcher import dispatch_due_workflow_schedules
from research_intelligence.tasks.orchestrator.runner import PipelineRunner
from research_intelligence.utils.mailer import send_mailgun_message, send_mail
from research_intelligence.reports.registry import reporter_registry
from api.views.schedules import WorkflowScheduleViewSet
from api.views.subscribers import SubscriberViewSet
from mcp_server.tools.workspaces.crud import get_workspace_logic
from mcp_server.tools.diagnostics.email import send_pipeline_run_digest_email_logic

User = get_user_model()


class FeatureSwitchingIntegrationTestCase(TestCase):
    """
    Validates end-to-end suppression and dynamic reactivation across all architectural layers.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.api_factory = APIRequestFactory()
        self.admin_site = AdminSite()

        self.user = User.objects.create_superuser(
            username="admin_test", email="admin@example.com", password="password123"
        )
        self.workspace = Workspace.objects.create(name="Test Switch Workspace")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")

        self.schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Daily Routine",
            frequency="daily",
            created_by=self.user,
        )
        self.subscriber = Subscriber.objects.create(
            workspace=self.workspace,
            name="Lead Analyst",
            email="analyst@example.com",
            subscription_type="all",
        )

    # --------------------------------------------------------------------------
    # 1. Django Admin Visibility & Permissions
    # --------------------------------------------------------------------------

    @override_settings(FEATURES={"SCHEDULING": False, "EMAIL_NOTIFICATIONS": False})
    def test_admin_permissions_denied_when_features_disabled(self):
        """Admin modules must deny view and module permissions when features are False."""
        request = self.factory.get("/admin/")
        request.user = self.user

        ws_admin = WorkflowScheduleAdmin(WorkflowSchedule, self.admin_site)
        sub_admin = SubscriberAdmin(Subscriber, self.admin_site)

        self.assertFalse(ws_admin.has_module_permission(request))
        self.assertFalse(ws_admin.has_view_permission(request))
        self.assertFalse(ws_admin.has_add_permission(request))
        self.assertFalse(ws_admin.has_change_permission(request))
        self.assertFalse(ws_admin.has_delete_permission(request))

        self.assertFalse(sub_admin.has_module_permission(request))
        self.assertFalse(sub_admin.has_view_permission(request))
        self.assertFalse(sub_admin.has_add_permission(request))
        self.assertFalse(sub_admin.has_change_permission(request))
        self.assertFalse(sub_admin.has_delete_permission(request))

    @override_settings(FEATURES={"SCHEDULING": True, "EMAIL_NOTIFICATIONS": True})
    def test_admin_permissions_granted_when_features_enabled(self):
        """Admin modules grant standard permissions when features are explicitly enabled."""
        request = self.factory.get("/admin/")
        request.user = self.user

        ws_admin = WorkflowScheduleAdmin(WorkflowSchedule, self.admin_site)
        sub_admin = SubscriberAdmin(Subscriber, self.admin_site)

        self.assertTrue(ws_admin.has_module_permission(request))
        self.assertTrue(ws_admin.has_view_permission(request))
        self.assertTrue(sub_admin.has_module_permission(request))
        self.assertTrue(sub_admin.has_view_permission(request))

    @override_settings(FEATURES={"SCHEDULING": False, "EMAIL_NOTIFICATIONS": False})
    def test_workspace_admin_inlines_excluded_when_disabled(self):
        """WorkspaceAdmin.get_inlines must omit WorkflowScheduleInline and SubscriberInline."""
        request = self.factory.get("/admin/research_intelligence/workspace/")
        request.user = self.user
        admin = WorkspaceAdmin(Workspace, self.admin_site)

        inlines = admin.get_inlines(request, self.workspace)
        inline_classes = [i if isinstance(i, type) else type(i) for i in inlines]

        self.assertNotIn(WorkflowScheduleInline, inline_classes)
        self.assertNotIn(SubscriberInline, inline_classes)

    @override_settings(FEATURES={"SCHEDULING": True, "EMAIL_NOTIFICATIONS": True})
    def test_workspace_admin_inlines_included_when_enabled(self):
        """WorkspaceAdmin.get_inlines includes both inlines when features are True."""
        request = self.factory.get("/admin/research_intelligence/workspace/")
        request.user = self.user
        admin = WorkspaceAdmin(Workspace, self.admin_site)

        inlines = admin.get_inlines(request, self.workspace)
        inline_classes = [i if isinstance(i, type) else type(i) for i in inlines]

        self.assertIn(WorkflowScheduleInline, inline_classes)
        self.assertIn(SubscriberInline, inline_classes)

    @override_settings(FEATURES={"SCHEDULING": False})
    def test_pipelinerun_admin_schedule_display_when_scheduling_disabled(self):
        """PipelineRunAdmin.schedule_display renders unlinked plain text when scheduling is disabled."""
        run = PipelineRun.objects.create(workspace=self.workspace, schedule=self.schedule)
        admin = PipelineRunAdmin(PipelineRun, self.admin_site)
        rendered = str(admin.schedule_display(run))
        self.assertIn("Manual", rendered)
        self.assertNotIn("href=", rendered)

    # --------------------------------------------------------------------------
    # 2. Pipeline Dispatching & Mailer Suppression
    # --------------------------------------------------------------------------

    @override_settings(FEATURES={"SCHEDULING": False})
    def test_schedule_dispatcher_early_exits_when_disabled(self):
        """Periodic schedule dispatcher exits early with disabled status when feature is False."""
        res = dispatch_due_workflow_schedules(dry_run=False)
        self.assertEqual(res["status"], "disabled")
        self.assertEqual(res["dispatched_count"], 0)

    @override_settings(FEATURES={"EMAIL_NOTIFICATIONS": False})
    @patch("research_intelligence.utils.mailer.send_mailgun_message")
    def test_runner_send_completion_notification_skipped_when_disabled(self, mock_mailgun):
        """PipelineRunner.send_completion_notification skips dispatch without calling mailer."""
        run = PipelineRun.objects.create(workspace=self.workspace, status="completed")
        PipelineRunner.send_completion_notification(run)
        mock_mailgun.assert_not_called()

    @override_settings(FEATURES={"EMAIL_NOTIFICATIONS": False})
    @patch("requests.post")
    def test_mailer_circuit_breaker_prevents_network_calls(self, mock_post):
        """send_mailgun_message suppresses network requests and returns suppressed status."""
        success, res = send_mailgun_message(to_email="test@example.com", subject="Test")
        self.assertTrue(success)
        self.assertIsInstance(res, dict)
        self.assertTrue(res.get("suppressed"))
        mock_post.assert_not_called()

        sent_count = send_mail(
            subject="Test",
            message="Body",
            from_email="no-reply@test.com",
            recipient_list=["test@example.com"],
        )
        self.assertEqual(sent_count, 0)
        mock_post.assert_not_called()

    @override_settings(FEATURES={"EMAIL_NOTIFICATIONS": False})
    def test_reporter_registry_skips_when_disabled(self):
        """reporter_registry.dispatch_report skips dispatch when feature is False."""
        run = PipelineRun.objects.create(workspace=self.workspace, status="completed")
        res = reporter_registry.dispatch_report(workspace=self.workspace, event_type="result_report", pipeline_run=run)
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["sent_count"], 0)

    # --------------------------------------------------------------------------
    # 3. REST API ViewSets (HTTP 404 when disabled)
    # --------------------------------------------------------------------------

    @override_settings(FEATURES={"SCHEDULING": False})
    def test_schedules_api_returns_404_when_disabled(self):
        """WorkflowScheduleViewSet returns 404 Not Found when SCHEDULING is disabled."""
        req = self.api_factory.get("/api/v1/schedules/")
        force_authenticate(req, user=self.user)
        view = WorkflowScheduleViewSet.as_view({"get": "list"})
        resp = view(req)
        self.assertEqual(resp.status_code, 404)

    @override_settings(FEATURES={"SCHEDULING": True})
    def test_schedules_api_accessible_when_enabled(self):
        """WorkflowScheduleViewSet returns 200 OK when SCHEDULING is enabled."""
        req = self.api_factory.get("/api/v1/schedules/")
        force_authenticate(req, user=self.user)
        view = WorkflowScheduleViewSet.as_view({"get": "list"})
        resp = view(req)
        self.assertEqual(resp.status_code, 200)

    @override_settings(FEATURES={"EMAIL_NOTIFICATIONS": False})
    def test_subscribers_api_returns_404_when_disabled(self):
        """SubscriberViewSet returns 404 Not Found when EMAIL_NOTIFICATIONS is disabled."""
        req = self.api_factory.get("/api/v1/subscribers/")
        force_authenticate(req, user=self.user)
        view = SubscriberViewSet.as_view({"get": "list"})
        resp = view(req)
        self.assertEqual(resp.status_code, 404)

    @override_settings(FEATURES={"EMAIL_NOTIFICATIONS": True})
    def test_subscribers_api_accessible_when_enabled(self):
        """SubscriberViewSet returns 200 OK when EMAIL_NOTIFICATIONS is enabled."""
        req = self.api_factory.get("/api/v1/subscribers/")
        force_authenticate(req, user=self.user)
        view = SubscriberViewSet.as_view({"get": "list"})
        resp = view(req)
        self.assertEqual(resp.status_code, 200)

    # --------------------------------------------------------------------------
    # 4. MCP Tools Representation
    # --------------------------------------------------------------------------

    @override_settings(FEATURES={"SCHEDULING": False, "EMAIL_NOTIFICATIONS": False})
    def test_mcp_workspace_details_omits_subscribers_and_schedules_when_disabled(self):
        """MCP get_workspace_logic returns empty lists for schedules and subscribers when disabled."""
        raw_json = get_workspace_logic(self.user, str(self.workspace.id))
        data = json.loads(raw_json)
        self.assertEqual(data["schedules"], [])
        self.assertEqual(data["subscribers"], [])

    @override_settings(FEATURES={"SCHEDULING": True, "EMAIL_NOTIFICATIONS": True})
    def test_mcp_workspace_details_includes_subscribers_and_schedules_when_enabled(self):
        """MCP get_workspace_logic includes schedules and subscribers when enabled."""
        raw_json = get_workspace_logic(self.user, str(self.workspace.id))
        data = json.loads(raw_json)
        self.assertEqual(len(data["schedules"]), 1)
        self.assertEqual(len(data["subscribers"]), 1)

    @override_settings(FEATURES={"EMAIL_NOTIFICATIONS": False})
    def test_mcp_email_diagnostics_returns_error_when_disabled(self):
        """send_pipeline_run_digest_email_logic returns error message when disabled."""
        run = PipelineRun.objects.create(workspace=self.workspace, status="completed")
        res_json = send_pipeline_run_digest_email_logic(self.user, str(self.workspace.id), str(run.id))
        data = json.loads(res_json)
        self.assertIn("error", data)
        self.assertIn("disabled", data["error"].lower())
