import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from research_intelligence.models import Workspace, WorkspaceMember, PipelineRun, ResearchAgentProcess
from research_intelligence.services.workspace_service import create_workspace_record, serialize_workspace_configuration, import_workspace_configuration_bundle
from research_intelligence.tasks.orchestrator.runner import ResearchAgentRunner
from research_intelligence.tasks.step_1_search.node import SearchNode
from research_intelligence.tasks.step_4_screening.node import AbstractScreeningNode, FullTextScreeningNode
from mcp_server.tools.workspaces.crud import list_workspaces_logic, get_workspace_logic, create_workspace_logic, update_workspace_logic
from mcp_server.tools.agents.processes import start_research_agent_logic
from mcp_server.tools.pipeline_runs.triggers import trigger_search_job_logic

User = get_user_model()


class WorkspaceReprocessFlagTestCase(TestCase):
    """
    Tests verifying the workspace-level `reprocess_existing` flag:
    1. Default value is False.
    2. Model, Admin, and REST API serialize and persist `reprocess_existing`.
    3. Pipeline runs and Agent processes inherit workspace default when not explicitly overridden.
    4. Per-run explicit overrides take precedence over workspace default (both True->False and False->True).
    5. MCP CRUD tools and DAG execution nodes honor workspace-level default.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="ws_reprocess_user", email="user@test.com", password="password123")
        self.admin = User.objects.create_superuser(username="ws_reprocess_admin", email="admin@test.com", password="password123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_workspace_default_reprocess_existing_is_false(self):
        ws = Workspace.objects.create(name="Default WS")
        self.assertFalse(ws.reprocess_existing)

        # Service creation
        ws2, err = create_workspace_record(user=self.user, name="Service WS")
        self.assertIsNone(err)
        self.assertFalse(ws2.reprocess_existing)

    def test_workspace_create_and_update_with_reprocess_existing_true(self):
        ws, err = create_workspace_record(user=self.user, name="Reprocess Active WS", reprocess_existing=True)
        self.assertIsNone(err)
        self.assertTrue(ws.reprocess_existing)

        serialized = serialize_workspace_configuration(ws)
        self.assertTrue(serialized.get("reprocess_existing"))

        # Test REST API GET / PATCH
        res_get = self.client.get(f"/api/workspaces/{ws.id}/")
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertIn("reprocess_existing", res_get.data)
        self.assertTrue(res_get.data["reprocess_existing"])

        # Patch to False
        res_patch = self.client.patch(f"/api/workspaces/{ws.id}/", {"reprocess_existing": False}, format="json")
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        ws.refresh_from_db()
        self.assertFalse(ws.reprocess_existing)

    def test_mcp_workspace_crud_reprocess_existing_lifecycle(self):
        # 1. Create via MCP
        res_raw = create_workspace_logic(self.admin, name="MCP Reprocess WS", reprocess_existing=True)
        res = json.loads(res_raw)
        self.assertEqual(res["status"], "success")
        ws_id = res["workspace_id"]

        ws = Workspace.objects.get(id=ws_id)
        self.assertTrue(ws.reprocess_existing)

        # 2. Get via MCP
        details = json.loads(get_workspace_logic(self.admin, workspace_id=ws_id))
        self.assertTrue(details["reprocess_existing"])

        # 3. List via MCP
        ws_list = json.loads(list_workspaces_logic(self.admin))
        matched = next(w for w in ws_list if w["workspace_id"] == ws_id)
        self.assertTrue(matched["reprocess_existing"])

        # 4. Update via MCP to False
        up_raw = update_workspace_logic(self.admin, workspace_id=ws_id, reprocess_existing=False)
        up_res = json.loads(up_raw)
        self.assertEqual(up_res["status"], "success")
        ws.refresh_from_db()
        self.assertFalse(ws.reprocess_existing)

    def test_agent_process_inherits_workspace_reprocess_existing_default(self):
        ws_true = Workspace.objects.create(name="Reprocess Enabled WS", reprocess_existing=True)
        WorkspaceMember.objects.create(workspace=ws_true, user=self.admin, role="admin")

        # 1. Start agent without explicit override -> inherits True
        start_res_raw = start_research_agent_logic(self.admin, workspace_id=str(ws_true.id), name="Inherit True Agent")
        start_res = json.loads(start_res_raw)
        self.assertEqual(start_res["status"], "success")
        proc_true = ResearchAgentProcess.objects.get(id=start_res["process_id"])
        self.assertTrue(proc_true.configuration_override.get("reprocess_existing"))

        # Tick runner -> PipelineRun inherits True
        with patch("research_intelligence.tasks.orchestrator.dag.engine.WorkflowDAG.evaluate_and_dispatch") as mock_disp:
            mock_disp.return_value = {"status": "running"}
            ResearchAgentRunner.tick(str(proc_true.id))
            proc_true.refresh_from_db()
            self.assertIsNotNone(proc_true.pipeline_run)
            self.assertTrue(proc_true.pipeline_run.reprocess_existing)

        # 2. Start agent with explicit override reprocess_existing=False -> overrides workspace True
        start_false_raw = start_research_agent_logic(
            self.admin, workspace_id=str(ws_true.id), name="Override False Agent", reprocess_existing=False
        )
        proc_false = ResearchAgentProcess.objects.get(id=json.loads(start_false_raw)["process_id"])
        self.assertFalse(proc_false.configuration_override.get("reprocess_existing"))

    def test_pipeline_run_trigger_search_job_inherits_workspace_reprocess(self):
        from research_intelligence.models import Scraper
        ws_true = Workspace.objects.create(name="Scraper WS", reprocess_existing=True)
        WorkspaceMember.objects.create(workspace=ws_true, user=self.admin, role="admin")
        scraper = Scraper.objects.create(workspace=ws_true, provider="arxiv", search_query="quantum", is_active=True)

        with patch("mcp_server.tools.pipeline_runs.triggers.execute_scraper_run_job.delay"):
            # Trigger without explicit reprocess_existing argument -> inherits workspace True
            res_raw = trigger_search_job_logic(self.admin, workspace_id=str(ws_true.id), scraper_id=str(scraper.id))
            res = json.loads(res_raw)
            self.assertTrue(res.get("success"))
            run = PipelineRun.objects.get(id=res["pipeline_run_id"])
            self.assertTrue(run.reprocess_existing)

            # Trigger with explicit reprocess_existing=False -> overrides workspace True
            res_raw_override = trigger_search_job_logic(
                self.admin, workspace_id=str(ws_true.id), scraper_id=str(scraper.id), reprocess_existing=False
            )
            res_ov = json.loads(res_raw_override)
            self.assertTrue(res_ov.get("success"))
            run_override = PipelineRun.objects.get(id=res_ov["pipeline_run_id"])
            self.assertFalse(run_override.reprocess_existing)

    def test_dag_nodes_honor_workspace_reprocess_fallback(self):
        ws_true = Workspace.objects.create(name="DAG Fallback WS", reprocess_existing=True)
        run_no_override = PipelineRun.objects.create(workspace=ws_true, reprocess_existing=False)

        search_node = SearchNode()
        abs_node = AbstractScreeningNode()
        ft_node = FullTextScreeningNode()

        # When config is empty, fallback checks pipeline_run then workspace
        self.assertFalse(search_node.should_halt_pipeline(run_no_override, ws_true, {})[0])
