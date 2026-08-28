from unittest.mock import patch, MagicMock
from research_intelligence.models import Paper, PipelineRun, Workspace, WorkspaceMember
from chat.models import PaperChatSession, PaperChatMessage
from mcp_server.tools import ask_paper_logic
from .base import BaseMCPTestCase


class MCPChatTestCase(BaseMCPTestCase):
    def setUp(self):
        super().setUp()
        self.run = PipelineRun.objects.create(workspace=self.workspace)
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="sha256_photonic_mcp_01",
            title="Photonic Processing Unit Architecture",
            abstract="High performance photonic tensor processing unit.",
            screening_status="accepted",
            signal_score=9.4
        )

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_ask_paper_mcp_tool_success(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            "The Photonic Processing Unit achieves extreme matrix throughput.",
            {"prompt_tokens": 1200, "candidates_tokens": 60, "total_tokens": 1260}
        )
        mock_get_llm_provider.return_value = mock_provider

        res = self.parse_res(ask_paper_logic(
            self.admin,
            workspace_id=str(self.workspace.id),
            paper_id=str(self.paper.id),
            question="What is the architecture overview?",
            deep_thinking=True
        ))

        self.assertEqual(res["status"], "completed")
        self.assertIn("Photonic Processing Unit", res["answer"])
        self.assertEqual(res["paper_id"], str(self.paper.id))
        self.assertEqual(res["paper_title"], "Photonic Processing Unit Architecture")
        self.assertTrue(res["deep_thinking"])
        self.assertIsNotNone(res["session_id"])

        # Second turn reusing session_id
        session_id = res["session_id"]
        res_turn2 = self.parse_res(ask_paper_logic(
            self.admin,
            workspace_id=str(self.workspace.id),
            paper_id=str(self.paper.id),
            session_id=session_id,
            question="What is the energy efficiency?"
        ))
        self.assertEqual(res_turn2["status"], "completed")
        self.assertEqual(res_turn2["session_id"], session_id)

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_ask_paper_workspace_level_synthesis(self, mock_get_llm_provider):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            "The workspace contains 1 top accepted paper on photonic processing.",
            {"prompt_tokens": 800, "candidates_tokens": 40, "total_tokens": 840}
        )
        mock_get_llm_provider.return_value = mock_provider

        # Ask question without paper_id -> queries workspace overview
        res = self.parse_res(ask_paper_logic(
            self.admin,
            workspace_id=str(self.workspace.id),
            question="Summarize the top accepted findings in this workspace."
        ))

        self.assertEqual(res["status"], "completed")
        self.assertIsNone(res["paper_id"])
        self.assertIn("photonic processing", res["answer"].lower())

    def test_ask_paper_error_responses_are_valid_json(self):
        # 1. Missing required parameters
        res_missing = self.parse_res(ask_paper_logic(self.admin, workspace_id="", question=""))
        self.assertEqual(res_missing["status"], "error")
        self.assertIn("must provide", res_missing["error"].lower())

        # 2. Non-existent workspace
        import uuid
        random_ws_id = str(uuid.uuid4())
        res_ws = self.parse_res(ask_paper_logic(self.admin, workspace_id=random_ws_id, question="test"))
        self.assertEqual(res_ws["status"], "error")

        # 3. Non-existent paper
        random_paper_id = str(uuid.uuid4())
        res_paper = self.parse_res(ask_paper_logic(
            self.admin,
            workspace_id=str(self.workspace.id),
            paper_id=random_paper_id,
            question="test"
        ))
        self.assertEqual(res_paper["status"], "error")
        self.assertIn("not found in workspace", res_paper["error"])

        # 4. Non-existent chat session
        random_session_id = str(uuid.uuid4())
        res_session = self.parse_res(ask_paper_logic(
            self.admin,
            workspace_id=str(self.workspace.id),
            session_id=random_session_id,
            question="test"
        ))
        self.assertEqual(res_session["status"], "error")
        self.assertIn("not found in workspace", res_session["error"])

    def test_ask_paper_tenant_isolation(self):
        # Other user has a secret workspace
        other_user = self.create_user(username="secret_scientist")
        other_ws = Workspace.objects.create(name="Top Secret Quantum Lab")
        WorkspaceMember.objects.create(workspace=other_ws, user=other_user, role="admin")

        # Researcher cannot access secret workspace
        res = self.parse_res(ask_paper_logic(
            self.researcher,
            workspace_id=str(other_ws.id),
            question="Tell me about secret project."
        ))
        self.assertEqual(res["status"], "error")
        self.assertIn("access denied", res["error"].lower())
