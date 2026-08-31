import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    ComponentRun,
    Paper,
)
from research_intelligence.tasks.step_4_screening.node import AbstractScreeningNode, FullTextScreeningNode
from research_intelligence.tasks.step_4_screening.abstract import execute_screening_job
from research_intelligence.tasks.step_4_screening.full_text import execute_full_text_screening_job
from mcp_server.tools.pipeline_runs.triggers import trigger_screening_job_logic

User = get_user_model()


class ComponentRunPromptCaptureTestCase(TestCase):
    """
    Tests verifying that ComponentRun.input_params captures exact prompt snapshots
    including criteria, system prompts, user templates, exit metrics, and output JSON schemas.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="prompt_tester", email="prompt@example.com", password="password123")
        self.workspace = Workspace.objects.create(
            name="AI Prompt Capture Lab",
            abstract_acceptance_criteria="Include papers discussing transformer attention optimizations.",
            abstract_rejection_criteria="Exclude survey papers without experimental evaluation.",
            abstract_screening_system_prompt="You are a senior ML reviewer evaluating abstract relevance.",
            abstract_screening_user_prompt_template="Title: {title}\nAbstract: {abstract}\nCriteria: {acceptance_criteria}\nRejection: {rejection_criteria}",
            abstract_screening_exit_metric="decision_category",
            abstract_screening_response_schema={
                "type": "object",
                "properties": {
                    "passed": {"type": "boolean"},
                    "decision_category": {"type": "string"},
                    "reasoning": {"type": "string"}
                },
                "required": ["passed", "decision_category", "reasoning"]
            },
            full_text_acceptance_criteria="Include papers with empirical benchmark latency on NVIDIA GPUs.",
            full_text_rejection_criteria="Exclude theoretical papers lacking hardware latency metrics.",
            full_text_screening_system_prompt="You are a systems researcher evaluating full-text hardware efficiency.",
            full_text_screening_user_prompt_template="Title: {title}\nFull Text: {full_text}\nCriteria: {acceptance_criteria}",
            full_text_screening_exit_metric="hardware_fit_score",
            full_text_screening_response_schema={
                "type": "object",
                "properties": {
                    "passed": {"type": "boolean"},
                    "hardware_fit_score": {"type": "number"},
                    "reasoning": {"type": "string"}
                },
                "required": ["passed", "hardware_fit_score", "reasoning"]
            },
            screening_llm_model="google/gemini-3.7-flash",
            llm_provider="google",
            reasoning_effort="high"
        )
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            triggered_by=self.user,
            status="running"
        )

        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="prompt_test_p1",
            title="Fast Attention Kernel Optimization",
            abstract="We present FlashKernel for reducing GPU latency in transformer inference.",
            screening_status="pending"
        )

    def test_abstract_screening_node_get_input_params(self):
        """Verify AbstractScreeningNode.get_input_params builds complete criteria and prompt snapshot."""
        node = AbstractScreeningNode()
        params = node.get_input_params(self.pipeline_run, self.workspace, {"limit": 10}, limit=10)

        self.assertEqual(params["stage"], "abstract")
        self.assertEqual(params["llm_model"], "google/gemini-3.7-flash")
        self.assertEqual(params["llm_provider"], "google")
        self.assertEqual(params["reasoning_effort"], "high")
        self.assertEqual(params["abstract_acceptance_criteria"], "Include papers discussing transformer attention optimizations.")
        self.assertEqual(params["abstract_rejection_criteria"], "Exclude survey papers without experimental evaluation.")
        self.assertEqual(params["abstract_screening_system_prompt"], "You are a senior ML reviewer evaluating abstract relevance.")
        self.assertIn("{title}", params["abstract_screening_user_prompt_template"])
        self.assertEqual(params["abstract_screening_exit_metric"], "decision_category")
        self.assertIn("properties", params["abstract_screening_response_schema"])
        self.assertEqual(params["limit"], 10)

    def test_full_text_screening_node_get_input_params(self):
        """Verify FullTextScreeningNode.get_input_params builds complete criteria and prompt snapshot."""
        node = FullTextScreeningNode()
        params = node.get_input_params(self.pipeline_run, self.workspace, {"limit": 5}, limit=5)

        self.assertEqual(params["stage"], "full_text")
        self.assertEqual(params["llm_model"], "google/gemini-3.7-flash")
        self.assertEqual(params["llm_provider"], "google")
        self.assertEqual(params["reasoning_effort"], "high")
        self.assertEqual(params["full_text_acceptance_criteria"], "Include papers with empirical benchmark latency on NVIDIA GPUs.")
        self.assertEqual(params["full_text_rejection_criteria"], "Exclude theoretical papers lacking hardware latency metrics.")
        self.assertEqual(params["full_text_screening_system_prompt"], "You are a systems researcher evaluating full-text hardware efficiency.")
        self.assertIn("{full_text}", params["full_text_screening_user_prompt_template"])
        self.assertEqual(params["full_text_screening_exit_metric"], "hardware_fit_score")
        self.assertIn("hardware_fit_score", params["full_text_screening_response_schema"]["properties"])
        self.assertEqual(params["limit"], 5)

    @patch("research_intelligence.tasks.step_4_screening.abstract.screen_abstract")
    def test_execute_screening_job_enriches_input_params_snapshot(self, mock_screen):
        """Verify execute_screening_job saves prompt & criteria snapshot to ComponentRun.input_params."""
        mock_screen.return_value = {
            "success": True,
            "passed": True,
            "screening_status": "abstract_passed",
            "reasoning": "Discusses FlashKernel attention optimization.",
            "decision_category": "ACCEPTED",
            "usage": {"tokens_in": 100, "tokens_out": 20}
        }

        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="abstract_screening",
            status="pending",
            input_params={"limit": 5}
        )

        res = execute_screening_job(str(comp_run.id))
        self.assertTrue(res)

        comp_run.refresh_from_db()
        params = comp_run.input_params
        self.assertEqual(params["stage"], "abstract")
        self.assertEqual(params["abstract_acceptance_criteria"], "Include papers discussing transformer attention optimizations.")
        self.assertEqual(params["abstract_screening_system_prompt"], "You are a senior ML reviewer evaluating abstract relevance.")
        self.assertEqual(params["abstract_screening_exit_metric"], "decision_category")
        self.assertIsInstance(params["abstract_screening_response_schema"], dict)

    @patch("research_intelligence.tasks.step_4_screening.full_text.screen_full_text")
    def test_execute_full_text_screening_job_enriches_input_params_snapshot(self, mock_screen):
        """Verify execute_full_text_screening_job saves prompt & criteria snapshot to ComponentRun.input_params."""
        mock_screen.return_value = {
            "success": True,
            "passed": True,
            "screening_status": "full_text_passed",
            "reasoning": "Demonstrates GPU latency benchmarks on NVIDIA H100.",
            "decision_category": "ACCEPTED",
            "hardware_fit_score": 9.5,
            "usage": {"tokens_in": 500, "tokens_out": 80}
        }

        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="full_text_screening",
            status="pending",
            input_params={"limit": 5}
        )

        res = execute_full_text_screening_job(str(comp_run.id))
        self.assertTrue(res)

        comp_run.refresh_from_db()
        params = comp_run.input_params
        self.assertEqual(params["stage"], "full_text")
        self.assertEqual(params["full_text_acceptance_criteria"], "Include papers with empirical benchmark latency on NVIDIA GPUs.")
        self.assertEqual(params["full_text_screening_system_prompt"], "You are a systems researcher evaluating full-text hardware efficiency.")
        self.assertEqual(params["full_text_screening_exit_metric"], "hardware_fit_score")
        self.assertIn("hardware_fit_score", params["full_text_screening_response_schema"]["properties"])

    @patch("mcp_server.tools.pipeline_runs.triggers.execute_screening_job")
    def test_trigger_screening_job_logic_creates_full_input_params(self, mock_exec):
        """Verify trigger_screening_job_logic populates complete input_params snapshot."""
        mock_exec.delay.return_value = MagicMock(id="celery_task_123")

        # Test abstract screening trigger
        raw_res = trigger_screening_job_logic(
            user=self.user,
            pipeline_run_id=str(self.pipeline_run.id),
            stage="abstract",
            limit=15
        )
        data = json.loads(raw_res)
        self.assertTrue(data.get("success"))
        comp_id = data.get("component_run_id")

        comp_run = ComponentRun.objects.get(id=comp_id)
        self.assertEqual(comp_run.input_params["stage"], "abstract")
        self.assertEqual(comp_run.input_params["abstract_acceptance_criteria"], "Include papers discussing transformer attention optimizations.")
        self.assertEqual(comp_run.input_params["abstract_screening_exit_metric"], "decision_category")
        self.assertEqual(comp_run.input_params["limit"], 15)

        # Test full-text screening trigger
        raw_res_ft = trigger_screening_job_logic(
            user=self.user,
            pipeline_run_id=str(self.pipeline_run.id),
            stage="full_text",
            limit=10
        )
        data_ft = json.loads(raw_res_ft)
        self.assertTrue(data_ft.get("success"))
        comp_id_ft = data_ft.get("component_run_id")

        comp_run_ft = ComponentRun.objects.get(id=comp_id_ft)
        self.assertEqual(comp_run_ft.input_params["stage"], "full_text")
        self.assertEqual(comp_run_ft.input_params["full_text_acceptance_criteria"], "Include papers with empirical benchmark latency on NVIDIA GPUs.")
        self.assertEqual(comp_run_ft.input_params["full_text_screening_exit_metric"], "hardware_fit_score")
        self.assertEqual(comp_run_ft.input_params["limit"], 10)
