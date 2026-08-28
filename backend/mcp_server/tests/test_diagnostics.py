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
        mock_generate.return_value = "Google LLM connectivity test successful with model gemini-3.7-flash."
        res = self.parse_res(test_google_llm_logic(self.admin, prompt="Test prompt", model="gemini-3.7-flash"))
        self.assertTrue(res.get("success", False))
        self.assertIn("connectivity test", res["message"].lower())
