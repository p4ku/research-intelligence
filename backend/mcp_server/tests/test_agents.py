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

    def test_get_pipeline_logs_and_live_telemetry(self):
        from research_intelligence.models import PipelineRun, ComponentRun
        pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="screening",
            triggered_by=self.admin
        )
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            name="Live Screening Agent",
            status="running",
            current_step="screening",
            triggered_by=self.admin,
            step_history=[
                {"step": "search", "event": "completed", "message": "Fetched 30 papers.", "timestamp": "2026-08-30T10:00:00Z"},
                {"step": "screening", "event": "started", "timestamp": "2026-08-30T10:05:00Z"}
            ]
        )
        comp_run = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type="screening",
            component_name="full_text_screening",
            status="running",
            metrics={
                "total_screened": 15,
                "total_to_screen": 30,
                "passed": 4,
                "rejected": 11,
                "percent_complete": 50.0,
                "latest_processed": "[PASSED] Quantum Error Correction in Diamond",
            }
        )

        with self.patch_auth(user=self.admin, workspace=self.workspace, api_key=self.api_key):
            # Test get_pipeline_logs tool
            logs_res = self.parse_res(server.get_pipeline_logs(process_id=str(agent.id)))
            self.assertEqual(logs_res.get("status"), "success")
            self.assertIn("terminal_output", logs_res)
            self.assertIn("Quantum Error Correction", logs_res["terminal_output"])
            self.assertEqual(logs_res["active_worker"]["component_name"], "full_text_screening")
            self.assertEqual(logs_res["active_worker"]["processed_items"], 15)

            # Test check_run_status live TQDM progress
            status_res = self.parse_res(server.check_run_status(process_id=str(agent.id)))
            self.assertEqual(status_res.get("status"), "running")
            self.assertFalse(status_res.get("is_finished"))
            self.assertIn("Live Task Telemetry & Worker Progress (TQDM)", status_res["summary_markdown"])
            self.assertIn("15/30 items", status_res["summary_markdown"])
            self.assertIn("4 Passed, 11 Rejected", status_res["summary_markdown"])

