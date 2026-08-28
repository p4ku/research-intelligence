import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from research_intelligence.models import Workspace, WorkspaceMember, UserActivityLog
from mcp.tools.diagnostics import list_user_activity_logs_logic

User = get_user_model()


class ActivityLogsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="audit_user",
            email="audit@example.com",
            password="password123"
        )
        self.workspace = Workspace.objects.create(
            name="Audit Target Workspace",
            abstract_acceptance_criteria="AI agent research",
            abstract_rejection_criteria="Out of domain"
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role="admin"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_log_action_creates_entry(self):
        """Test that UserActivityLog.log_action() creates a proper entry with denormalized fields."""
        log = UserActivityLog.log_action(
            user=self.user,
            workspace=self.workspace,
            interface="mcp",
            action_name="create_workspace",
            status="success",
            input_params={"name": "Test Workspace"},
            execution_time_ms=42.5
        )

        self.assertIsNotNone(log.id)
        self.assertEqual(log.user_username, "audit_user")
        self.assertEqual(log.user_email, "audit@example.com")
        self.assertEqual(log.workspace_name, "Audit Target Workspace")
        self.assertEqual(log.interface, "mcp")
        self.assertEqual(log.action_name, "create_workspace")
        self.assertEqual(log.status, "success")
        self.assertEqual(log.execution_time_ms, 42.5)

    def test_rest_api_middleware_logs_activity(self):
        """Test that making a REST API POST request generates a UserActivityLog entry via middleware."""
        # Clear any pre-existing logs
        UserActivityLog.objects.filter(interface="rest_api").delete()

        response = self.client.post(
            "/api/workspaces/",
            data=json.dumps({
                "name": "API Created Workspace",
                "abstract_acceptance_criteria": "Scope AI"
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)

        # Verify log entry created by UserActionAuditMiddleware
        logs = UserActivityLog.objects.filter(interface="rest_api")
        self.assertGreaterEqual(logs.count(), 1,
            f"Middleware should have created UserActivityLog. Found logs: {list(logs.values_list('action_name', flat=True))}")

        post_log = logs.filter(action_name__contains="POST").first()
        if post_log:
            self.assertEqual(post_log.user_username, "audit_user")
            self.assertEqual(post_log.status, "success")
            if post_log.input_params:
                self.assertEqual(post_log.input_params.get("name"), "API Created Workspace")

    def test_activity_log_retrieval_mcp_tool(self):
        """Test list_user_activity_logs_logic MCP tool."""
        UserActivityLog.log_action(
            user=self.user,
            workspace=self.workspace,
            interface="mcp",
            action_name="test_tool",
            status="success"
        )

        res_str = list_user_activity_logs_logic(
            user=self.user,
            workspace_id=str(self.workspace.id)
        )
        res_data = json.loads(res_str)
        self.assertEqual(res_data["status"], "success")
        self.assertGreaterEqual(res_data["count"], 1)

    def test_activity_log_rest_api_endpoint(self):
        """Test GET /api/activity-logs/ endpoint."""
        UserActivityLog.log_action(
            user=self.user,
            workspace=self.workspace,
            interface="rest_api",
            action_name="POST /api/agents/",
            status="success"
        )

        response = self.client.get("/api/activity-logs/")
        self.assertEqual(response.status_code, 200)
        # Response includes both the manually created log AND the middleware log for this GET request
        self.assertGreaterEqual(len(response.data), 1)

    def test_deletion_resilience_preserves_log_history(self):
        """
        CRITICAL REQUIREMENT TEST:
        Verifies that when a User or Workspace is deleted from the database,
        the UserActivityLog entry is NOT deleted, its foreign keys become SET_NULL,
        and its historical user_username, user_email, and workspace_name strings remain 100% intact!
        """
        temp_user = User.objects.create_user(
            username="doomed_user",
            email="doomed@example.com",
            password="password123"
        )
        temp_ws = Workspace.objects.create(
            name="Doomed Workspace",
            abstract_acceptance_criteria="Temp criteria"
        )

        log = UserActivityLog.log_action(
            user=temp_user,
            workspace=temp_ws,
            interface="mcp",
            action_name="start_research_agent",
            status="success",
            input_params={"limit": 50}
        )

        log_id = log.id

        # Delete user and workspace from database
        temp_user.delete()
        temp_ws.delete()

        # Refresh log entry from database
        log_after = UserActivityLog.objects.get(id=log_id)

        # Foreign keys should be NULL (SET_NULL)
        self.assertIsNone(log_after.user)
        self.assertIsNone(log_after.workspace)

        # Denormalized historical fields MUST be preserved!
        self.assertEqual(log_after.user_username, "doomed_user")
        self.assertEqual(log_after.user_email, "doomed@example.com")
        self.assertEqual(log_after.workspace_name, "Doomed Workspace")
        self.assertEqual(log_after.action_name, "start_research_agent")

    def test_automatic_workspace_resolution(self):
        """
        Verifies that UserActivityLog.log_action automatically resolves workspace when
        passed via input_params (workspace_id, pipeline_run_id, process_id, paper_id, etc.)
        or output_summary.
        """
        from research_intelligence.models import PipelineRun, ResearchAgentProcess, Paper

        # 1. Resolve via input_params['workspace_id']
        log1 = UserActivityLog.log_action(
            user=self.user,
            workspace=None,
            interface="mcp",
            action_name="list_scrapers",
            input_params={"workspace_id": str(self.workspace.id)}
        )
        self.assertEqual(log1.workspace, self.workspace)
        self.assertEqual(log1.workspace_name, "Audit Target Workspace")

        # 2. Resolve via input_params['pipeline_run_id']
        run = PipelineRun.objects.create(workspace=self.workspace)
        log2 = UserActivityLog.log_action(
            user=self.user,
            workspace=None,
            interface="mcp",
            action_name="get_pipeline_run_status",
            input_params={"pipeline_run_id": str(run.id)}
        )
        self.assertEqual(log2.workspace, self.workspace)
        self.assertEqual(log2.workspace_name, "Audit Target Workspace")

        # 3. Resolve via input_params['process_id']
        proc = ResearchAgentProcess.objects.create(workspace=self.workspace, pipeline_run=run)
        log3 = UserActivityLog.log_action(
            user=self.user,
            workspace=None,
            interface="mcp",
            action_name="get_research_agent_status",
            input_params={"process_id": str(proc.id)}
        )
        self.assertEqual(log3.workspace, self.workspace)
        self.assertEqual(log3.workspace_name, "Audit Target Workspace")

        # 4. Resolve via input_params['paper_id']
        paper = Paper.objects.create(workspace=self.workspace, pipeline_run=run, hash_id="audit_hash", title="Audit Paper")
        log4 = UserActivityLog.log_action(
            user=self.user,
            workspace=None,
            interface="mcp",
            action_name="get_paper_extractions_matrix",
            input_params={"paper_id": str(paper.id)}
        )
        self.assertEqual(log4.workspace, self.workspace)
        self.assertEqual(log4.workspace_name, "Audit Target Workspace")

        # 5. Resolve via output_summary['workspace_id'] (e.g. create_workspace)
        log5 = UserActivityLog.log_action(
            user=self.user,
            workspace=None,
            interface="mcp",
            action_name="create_workspace",
            output_summary={"status": "success", "workspace_id": str(self.workspace.id)}
        )
        self.assertEqual(log5.workspace, self.workspace)
        self.assertEqual(log5.workspace_name, "Audit Target Workspace")

        # 6. Resolve via action_name URL containing workspace UUID
        log6 = UserActivityLog.log_action(
            user=self.user,
            workspace=None,
            interface="rest_api",
            action_name=f"GET /api/workspaces/{str(self.workspace.id)}/"
        )
        self.assertEqual(log6.workspace, self.workspace)
        self.assertEqual(log6.workspace_name, "Audit Target Workspace")
