from unittest.mock import patch, MagicMock
from research_intelligence.models import DocumentRegistry
from mcp_server.tools import (
    get_document_registry_stats_logic,
    test_google_llm_logic,
    list_user_activity_logs_logic,
)
from .base import BaseMCPTestCase


class MCPDiagnosticsTestCase(BaseMCPTestCase):
    def test_get_document_registry_stats_logic(self):
        DocumentRegistry.objects.create(
            sha256_hash="stat_hash_01",
            title="Cached Paper 1",
            pdf_file_size_bytes=1000000,
            access_count=5
        )
        res = self.parse_res(get_document_registry_stats_logic(self.admin))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["total_cached_documents"], 1)

    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_google_llm_tool(self, mock_generate):
        mock_generate.return_value = "Google LLM connectivity test successful with model gemini-3.8-flash."
        res = self.parse_res(test_google_llm_logic(self.admin, prompt="Test prompt", model="gemini-3.8-flash"))
        self.assertTrue(res.get("success", False))
        self.assertIn("connectivity test", res["message"].lower())

    def test_list_user_activity_logs_tenant_isolation(self):
        from research_intelligence.models import UserActivityLog, Workspace, WorkspaceMember
        from django.contrib.auth import get_user_model
        User = get_user_model()

        other_user = User.objects.create_user(username="other_researcher", password="password123")
        other_ws = Workspace.objects.create(name="Other Secret WS")
        WorkspaceMember.objects.create(workspace=other_ws, user=other_user, role="admin")

        log_own = UserActivityLog.log_action(user=self.researcher, workspace=self.workspace, action_name="own_action")
        log_other = UserActivityLog.log_action(user=other_user, workspace=other_ws, action_name="secret_action")

        # 1. Researcher requesting without workspace_id should only see their own / their workspace logs
        res_researcher = self.parse_res(list_user_activity_logs_logic(self.researcher))
        self.assertEqual(res_researcher["status"], "success")
        log_ids = [l["id"] for l in res_researcher["logs"]]
        self.assertIn(str(log_own.id), log_ids)
        self.assertNotIn(str(log_other.id), log_ids)

        # 2. Superuser sees all logs
        res_admin = self.parse_res(list_user_activity_logs_logic(self.admin))
        admin_log_ids = [l["id"] for l in res_admin["logs"]]
        self.assertIn(str(log_own.id), admin_log_ids)
        self.assertIn(str(log_other.id), admin_log_ids)

