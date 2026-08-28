import json
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from research_intelligence.models import Workspace, WorkspaceMember, ResearchAgentProcess, APIKey
from mcp.tools import (
    start_research_agent_logic,
    list_research_agents_logic,
    get_research_agent_status_logic,
    check_run_status_logic,
    pause_research_agent_logic,
    resume_research_agent_logic,
    abort_research_agent_logic,
    delete_research_agent_logic,
    get_workflow_dag_schema_logic,
)
from mcp import server

User = get_user_model()


class MCPAgentsTestCase(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(username="agent_admin", email="admin@schwarz.de", password="password")
        self.workspace = Workspace.objects.create(name="Autonomous Agent WS")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.admin_user, role="admin")
        self.api_key = APIKey.objects.create(user=self.admin_user, name="Admin Key", scopes=["*"])

    def test_get_workflow_dag_schema_mcp(self):
        res = json.loads(get_workflow_dag_schema_logic(self.admin_user))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["dag_name"], "slr_systematic_review_dag")
        self.assertIn("nodes", res)

    def test_check_run_status_server_tool_invocation(self):
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            name="Test Agent Check Status",
            status="completed",
            current_step="completed",
            triggered_by=self.admin_user
        )

        with patch("mcp.server.app.get_auth_context", return_value=(self.admin_user, agent.workspace, self.api_key)):
            res_str = server.check_run_status(process_id=str(agent.id))
            res = json.loads(res_str)
            self.assertEqual(res.get("status"), "completed")
            self.assertTrue(res.get("is_finished"))
            self.assertEqual(res.get("agent_status"), "completed")
            self.assertIn("summary_markdown", res)
