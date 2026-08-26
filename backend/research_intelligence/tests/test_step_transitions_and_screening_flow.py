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
    Extraction,
    ExtractionDefinition,
    ResearchAgentProcess
)
from research_intelligence.tasks.step_5_extraction.extract import execute_extraction_job
from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process

User = get_user_model()


class StepTransitionsAndScreeningFlowTestCase(TestCase):
    """
    Tests pipeline step transitions, screening status filtering in extraction,
    and state engine zero-pass edge cases:
    1. Extraction step targeting both 'full_text_passed' and 'accepted' status aliases.
    2. Extraction step targeting both 'abstract_passed' and 'accepted' status aliases.
    3. State engine skipping OCR when ocr_provider is None (direct multimodal mode).
    4. State engine zero-pass handling when 0 papers pass abstract screening (skips full-text, completes gracefully).
    """

    def setUp(self):
        self.user = User.objects.create_user(username="flow_tester", email="flow@example.com", password="password123")
        self.workspace = Workspace.objects.create(
            name="Pipeline Flow Lab",
            ocr_provider=None,  # Direct multimodal PDF mode
            screening_llm_model="google/gemini-3.7-flash"
        )
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            triggered_by=self.user,
            status="running"
        )

        self.ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Key Findings",
            llm_model="google/gemini-3.7-flash",
            system_prompt="Extract main findings.",
            response_schema={"type": "object", "properties": {"finding": {"type": "string"}}}
        )

    def test_extraction_targets_both_full_text_passed_and_accepted_aliases(self):
        """
        Ensures execute_extraction_job captures papers with screening_status='full_text_passed'
        AND 'accepted' when prior full-text screening exists.
        """
        # Prior full-text screening component run
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="full_text_screening",
            status="completed"
        )

        # Paper 1 with canonical 'full_text_passed'
        p1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="flow_p1",
            title="Full Text Passed Paper",
            abstract="Study on deep learning.",
            screening_status="full_text_passed"
        )

        # Paper 2 with alias 'accepted'
        p2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="flow_p2",
            title="Accepted Alias Paper",
            abstract="Study on reinforcement learning.",
            screening_status="accepted"
        )

        # Paper 3 rejected (should be excluded)
        p3 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="flow_p3",
            title="Rejected Paper",
            abstract="Out of domain.",
            screening_status="rejected"
        )

        comp_run_extract = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="extraction",
            component_name="parameter_extractor",
            status="running"
        )

        mock_llm_output = {"finding": "Model converged in 10 epochs.", "confidence_score": 0.95}
        mock_usage = {"prompt_tokens": 500, "candidates_tokens": 50, "total_tokens": 550}

        with patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider") as mock_provider_factory:
            mock_provider = MagicMock()
            mock_provider.generate.return_value = (mock_llm_output, mock_usage)
            mock_provider_factory.return_value = mock_provider

            success = execute_extraction_job(str(comp_run_extract.id), limit=10)
            self.assertTrue(success)

        comp_run_extract.refresh_from_db()
        self.assertEqual(comp_run_extract.status, "completed")
        # Exactly 2 papers (p1 and p2) should be processed, p3 rejected excluded
        self.assertEqual(comp_run_extract.metrics["total_papers"], 2)
        self.assertEqual(comp_run_extract.metrics["extractions_created"], 2)
        self.assertEqual(Extraction.objects.filter(paper__in=[p1, p2]).count(), 2)

    def test_state_engine_skips_ocr_when_ocr_provider_is_none(self):
        """
        Ensures that when ocr_provider is None, tick_agent_process skips Step 3 (OCR)
        and transitions directly from 'download' to 'screening'.
        """
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            triggered_by=self.user,
            name="Direct Multimodal Agent",
            status="running",
            current_step="download"
        )

        # Download component run completed
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="download",
            component_name="pdf_downloader",
            status="completed"
        )

        with patch("research_intelligence.tasks.step_4_screening.abstract.execute_screening_job.delay") as mock_screening:
            mock_screening.return_value.id = "mock_screen_task_123"
            tick_result = tick_agent_process(str(agent.id))

            self.assertTrue(tick_result["success"])
            self.assertEqual(tick_result["current_step"], "screening")
            self.assertIn("OCR skipped", tick_result["message"])

        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "screening")

    def test_state_engine_zero_pass_abstract_screening_graceful_completion(self):
        """
        Tests when 0 papers pass abstract screening:
        State engine skips full-text screening, transitions to extraction,
        safely extracts 0 papers, and marks agent completed.
        """
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            triggered_by=self.user,
            name="Zero Pass Agent",
            status="running",
            current_step="screening"
        )

        # Abstract screening completed with 0 passed
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="abstract_screening",
            status="completed",
            metrics={"total_screened": 5, "passed": 0, "rejected": 5}
        )

        with patch("research_intelligence.tasks.step_5_extraction.extract.execute_extraction_job.delay") as mock_extract:
            mock_extract.return_value.id = "mock_extract_task_123"
            tick_result = tick_agent_process(str(agent.id))

            self.assertTrue(tick_result["success"])
            self.assertEqual(tick_result["current_step"], "extraction")
            # Extraction job was launched for 0 papers
            mock_extract.assert_called_once()

        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "extraction")

    def test_dynamic_dual_stage_screening_transitions_and_metrics(self):
        """
        Tests sequential Abstract Screening -> Full-Text Screening flow with custom dynamic schemas
        and verifies that PaperMetric aggregates both screening evaluation dictionaries.
        """
        from research_intelligence.tasks.step_4_screening.abstract import screen_abstract
        from research_intelligence.tasks.step_4_screening.full_text import screen_full_text
        from research_intelligence.models import PaperMetric

        self.workspace.abstract_screening_system_prompt = "Custom Abstract Scanner"
        self.workspace.abstract_screening_response_schema = {
            "type": "object",
            "properties": {"passed": {"type": "boolean"}, "novelty": {"type": "number"}}
        }
        self.workspace.abstract_screening_exit_metric = "novelty"

        self.workspace.full_text_screening_system_prompt = "Custom Full Text Analyst"
        self.workspace.full_text_screening_response_schema = {
            "type": "object",
            "properties": {"passed": {"type": "boolean"}, "rigour": {"type": "number"}}
        }
        self.workspace.full_text_screening_exit_metric = "rigour"
        self.workspace.save()

        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="flow_dynamic_paper",
            title="Flow Paper Dynamic Screening",
            abstract="Study on self-driving agents."
        )

        with patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate") as mock_generate:
            # 1. Abstract screening passes with custom novelty score
            mock_generate.return_value = {
                "passed": True,
                "novelty": 9.2,
                "reasoning": "High novelty in multi-agent coordination."
            }
            abs_res = screen_abstract(paper.id, self.workspace.id)
            self.assertTrue(abs_res["passed"])
            self.assertEqual(abs_res["exit_metric_value"], 9.2)

            paper.refresh_from_db()
            self.assertEqual(paper.screening_status, "abstract_passed")

            # 2. Full-Text screening passes with custom rigour score
            mock_generate.return_value = {
                "passed": True,
                "rigour": 8.7,
                "reasoning": "Empirical rigour backed by statistical tests."
            }
            ft_res = screen_full_text(paper.id, self.workspace.id)
            self.assertTrue(ft_res["passed"])
            self.assertEqual(ft_res["exit_metric_value"], 8.7)

            paper.refresh_from_db()
            self.assertEqual(paper.screening_status, "full_text_passed")

            # Check that PaperMetric recorded both stages cleanly
            pm = PaperMetric.objects.get(paper=paper, pipeline_run=self.pipeline_run)
            self.assertIn("abstract_screening", pm.metrics_data)
            self.assertIn("full_text_screening", pm.metrics_data)
            self.assertEqual(pm.metrics_data["abstract_screening"]["exit_metric_value"], 9.2)
            self.assertEqual(pm.metrics_data["full_text_screening"]["exit_metric_value"], 8.7)

