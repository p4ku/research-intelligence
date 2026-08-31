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

    def test_extraction_node_get_input_params(self):
        """Verify ExtractionNode.get_input_params builds a complete list of extraction definitions."""
        from research_intelligence.models import ExtractionDefinition
        from research_intelligence.tasks.step_5_extraction.node import ExtractionNode

        ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Evaluation",
            system_prompt="Extract research novelty score and key contributions.",
            user_prompt_template="Paper Content: {paper_text}",
            exit_metric="novelty_score",
            llm_model="google/gemini-3.7-flash",
            response_schema={"type": "object", "properties": {"novelty_score": {"type": "number"}}}
        )
        ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
            system_prompt="Assess Technology Readiness Level (1-9).",
            user_prompt_template="Full Text: {full_text}",
            exit_metric="trl_level",
            llm_model="google/gemini-3.7-flash",
            response_schema={"type": "object", "properties": {"trl_level": {"type": "integer"}}}
        )

        node = ExtractionNode()
        params = node.get_input_params(self.pipeline_run, self.workspace, {"limit": 10}, limit=10)

        self.assertEqual(params["stage"], "extraction")
        self.assertEqual(params["total_definitions"], 2)
        defs = params["extraction_definitions"]
        self.assertEqual(len(defs), 2)

        def_names = [d["name"] for d in defs]
        self.assertIn("Novelty Evaluation", def_names)
        self.assertIn("TRL Level", def_names)

        novelty_def = next(d for d in defs if d["name"] == "Novelty Evaluation")
        self.assertEqual(novelty_def["exit_metric"], "novelty_score")
        self.assertEqual(novelty_def["system_prompt"], "Extract research novelty score and key contributions.")
        self.assertEqual(novelty_def["user_prompt_template"], "Paper Content: {paper_text}")
        self.assertIn("novelty_score", novelty_def["response_schema"]["properties"])

    @patch("mcp_server.tools.pipeline_runs.triggers.execute_extraction_job")
    def test_trigger_extraction_job_logic_creates_full_input_params(self, mock_exec):
        """Verify trigger_extraction_job_logic snapshots all extraction definitions into input_params."""
        from research_intelligence.models import ExtractionDefinition
        from mcp_server.tools.pipeline_runs.triggers import trigger_extraction_job_logic

        mock_exec.delay.return_value = MagicMock(id="celery_task_ext_123")

        ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Schwarz Strategic Fit",
            system_prompt="Assess corporate fit with retail logistics.",
            user_prompt_template="Evaluate: {paper_text}",
            exit_metric="fit_score",
            llm_model="google/gemini-3.7-flash",
            response_schema={"type": "object", "properties": {"fit_score": {"type": "number"}}}
        )

        raw_res = trigger_extraction_job_logic(
            user=self.user,
            pipeline_run_id=str(self.pipeline_run.id),
            limit=5
        )
        data = json.loads(raw_res)
        self.assertTrue(data.get("success"))
        comp_id = data.get("component_run_id")

        comp_run = ComponentRun.objects.get(id=comp_id)
        self.assertEqual(comp_run.input_params["stage"], "extraction")
        self.assertEqual(comp_run.input_params["total_definitions"], 1)
        self.assertEqual(comp_run.input_params["extraction_definitions"][0]["name"], "Schwarz Strategic Fit")
        self.assertEqual(comp_run.input_params["extraction_definitions"][0]["exit_metric"], "fit_score")
        self.assertEqual(comp_run.input_params["limit"], 5)

    def test_signal_score_node_get_input_params(self):
        """Verify SignalScoreNode.get_input_params captures exact formula code and available variables."""
        from research_intelligence.models import ExtractionDefinition
        from research_intelligence.tasks.step_6_signal_score.node import SignalScoreNode

        self.workspace.signal_score_code = "score = (fit_score * 0.6) + (novelty_score * 0.4)"
        self.workspace.save()

        ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Strategic Fit",
            system_prompt="Fit",
            user_prompt_template="Fit",
            exit_metric="fit_score",
            response_schema={"type": "object"}
        )
        ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty",
            system_prompt="Nov",
            user_prompt_template="Nov",
            exit_metric="novelty_score",
            response_schema={"type": "object"}
        )

        node = SignalScoreNode()
        params = node.get_input_params(self.pipeline_run, self.workspace, {"limit": 10}, limit=10)

        self.assertEqual(params["stage"], "signal_score")
        self.assertEqual(params["evaluation_engine"], "AST Sandboxed Python 3")
        self.assertEqual(params["signal_score_code"], "score = (fit_score * 0.6) + (novelty_score * 0.4)")
        self.assertTrue(params["has_custom_formula"])
        self.assertEqual(params["total_scoring_variables"], 2)

        var_names = [v["variable_name"] for v in params["scoring_variables"]]
        self.assertIn("fit_score", var_names)
        self.assertIn("novelty_score", var_names)

        fit_var = next(v for v in params["scoring_variables"] if v["definition_name"] == "Strategic Fit")
        self.assertEqual(fit_var["exit_metric"], "fit_score")
        self.assertEqual(fit_var["variable_name"], "fit_score")

    @patch("mcp_server.tools.pipeline_runs.triggers.execute_signal_score_job")
    def test_trigger_signal_score_job_logic_creates_full_input_params(self, mock_exec):
        """Verify trigger_signal_score_job_logic snapshots signal score formula into input_params."""
        from research_intelligence.tasks.step_6_signal_score.scorer import compute_paper_signal_score
        from mcp_server.tools.pipeline_runs.triggers import trigger_signal_score_job_logic

        mock_exec.delay.return_value = MagicMock(id="celery_task_sig_123")

        self.workspace.signal_score_code = "score = fit_score * 100.0"
        self.workspace.save()

        self.paper.screening_status = "accepted"
        self.paper.save()

        raw_res = trigger_signal_score_job_logic(
            user=self.user,
            pipeline_run_id=str(self.pipeline_run.id),
            limit=5
        )
        data = json.loads(raw_res)
        self.assertTrue(data.get("success"))
        comp_id = data.get("component_run_id")

        comp_run = ComponentRun.objects.get(id=comp_id)
        self.assertEqual(comp_run.input_params["stage"], "signal_score")
        self.assertEqual(comp_run.input_params["signal_score_code"], "score = fit_score * 100.0")
        self.assertTrue(comp_run.input_params["has_custom_formula"])
        self.assertEqual(comp_run.input_params["limit"], 5)
        self.assertIn("scoring_variables", comp_run.input_params)


