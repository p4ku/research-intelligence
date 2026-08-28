import json
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from research_intelligence.models import Workspace, WorkspaceMember, DocumentRegistry
from mcp.tools import (
    get_document_registry_stats_logic,
    test_google_llm_logic,
    list_user_activity_logs_logic,
)

User = get_user_model()


class MCPDiagnosticsTestCase(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(username="diag_admin", email="admin@schwarz.de", password="password")
        self.workspace = Workspace.objects.create(name="Diagnostic Test WS")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.admin_user, role="admin")

    def test_get_document_registry_stats_logic(self):
        DocumentRegistry.objects.create(
            sha256_hash="stat_hash_01",
            title="Cached Paper 1",
            pdf_file_size_bytes=1000000,
            access_count=5
        )
        res = json.loads(get_document_registry_stats_logic(self.admin_user))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["total_cached_documents"], 1)

    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_google_llm_tool(self, mock_generate):
        mock_generate.return_value = "Google LLM connectivity test successful with model gemini-3.7-flash."
        res = json.loads(test_google_llm_logic(self.admin_user, prompt="Test prompt", model="gemini-3.7-flash"))
        self.assertTrue(res.get("success", False))
        self.assertIn("connectivity test", res["message"].lower())
