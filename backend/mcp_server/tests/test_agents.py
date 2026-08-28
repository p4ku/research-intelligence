from research_intelligence.models import ResearchAgentProcess
from mcp_server.tools import get_workflow_dag_schema_logic
from mcp_server import server
from .base import BaseMCPTestCase


class MCPAgentsTestCase(BaseMCPTestCase):
    def test_get_workflow_dag_schema_mcp(self):
        res = self.parse_res(get_workflow_dag_schema_logic(self.admin))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["dag_name"], "slr_systematic_review_dag")
        self.assertIn("nodes", res)

    def test_check_run_status_server_tool_invocation(self):
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Test Agent Check Status",
            status="completed",
            current_step="completed",
            triggered_by=self.admin
        )

        with self.patch_auth(user=self.admin, workspace=agent.workspace, api_key=self.api_key):
            res = self.parse_res(server.check_run_status(process_id=str(agent.id)))
            self.assertEqual(res.get("status"), "completed")
            self.assertTrue(res.get("is_finished"))
            self.assertEqual(res.get("agent_status"), "completed")
            self.assertIn("summary_markdown", res)
