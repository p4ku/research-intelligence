import json
import uuid
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    Scraper,
    PipelineRun,
    ComponentRun,
    Paper,
    ExtractionDefinition,
    Extraction,
    PaperMetric,
    ResearchAgentProcess
)
from mcp_server.tools.pipeline_runs.triggers import (
    trigger_search_job_logic,
    trigger_pdf_download_job_logic,
    trigger_ocr_job_logic,
    trigger_screening_job_logic,
    trigger_extraction_job_logic,
    trigger_signal_score_job_logic
)
from research_intelligence.tasks.step_1_search.search import execute_scraper_run_job
from research_intelligence.tasks.orchestrator.agent_engine import tick_agent_process

User = get_user_model()


class PipelineStepReexecutionAndResumeTestCase(TestCase):
    """
    End-to-end tests for:
    1. Re-running individual pipeline steps multiple times (idempotency, updates, deduplication).
    2. Restarting / resuming a pipeline or ResearchAgentProcess from intermediate steps (e.g., from step 3 OCR or step 4 Screening) after configuration changes.
    3. Chaining downstream steps after intermediate modifications.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="step_tester", email="step@corp.com", password="pass")
        self.workspace = Workspace.objects.create(
            name="E2E Pipeline Re-Execution Workspace",
            abstract_acceptance_criteria=["Must involve solid-state battery."],
            abstract_rejection_criteria=["Reject software simulations."],
            signal_score_code="return 0.5 * energy_density + 0.5 * cycle_life"
        )
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")

        self.scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="solid-state battery",
            is_active=True
        )

        self.ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Battery Performance",
            system_prompt="Extract energy density and cycle life",
            user_prompt_template="Extract from paper",
            response_schema={
                "type": "object",
                "properties": {
                    "energy_density": {"type": "number"},
                    "cycle_life": {"type": "number"}
                }
            },
            exit_metric="energy_density",
            is_active=True
        )

    @patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider")
    def test_rerun_step_1_search_multiple_times_deduplicates_papers(self, mock_get_scraper):
        mock_provider = MagicMock()
        mock_provider.search.return_value = [
            {"title": "Solid State Electrolyte V1", "hash_id": "2401.0001", "pdf_url": "https://arxiv.org/pdf/2401.0001.pdf", "abstract": "Paper 1", "source_database": "arxiv"},
            {"title": "Solid State Electrolyte V2", "hash_id": "2401.0002", "pdf_url": "https://arxiv.org/pdf/2401.0002.pdf", "abstract": "Paper 2", "source_database": "arxiv"},
        ]
        mock_get_scraper.return_value = mock_provider

        # Run 1: Ingests 2 papers synchronously
        res1 = trigger_search_job_logic(self.user, str(self.workspace.id), limit=10)
        data1 = json.loads(res1)
        self.assertTrue(data1["success"])
        for cr in data1["component_runs"]:
            execute_scraper_run_job.apply(args=[cr["component_run_id"]], kwargs={"limit": 10})

        self.assertEqual(Paper.objects.filter(workspace=self.workspace).count(), 2)

        # Run 2: Same query with overlapping results + 1 new paper
        mock_provider.search.return_value = [
            {"title": "Solid State Electrolyte V1", "hash_id": "2401.0001", "pdf_url": "https://arxiv.org/pdf/2401.0001.pdf", "abstract": "Paper 1", "source_database": "arxiv"},
            {"title": "Solid State Electrolyte V3", "hash_id": "2401.0003", "pdf_url": "https://arxiv.org/pdf/2401.0003.pdf", "abstract": "Paper 3", "source_database": "arxiv"},
        ]
        res2 = trigger_search_job_logic(self.user, str(self.workspace.id), limit=10)
        data2 = json.loads(res2)
        self.assertTrue(data2["success"])
        for cr in data2["component_runs"]:
            execute_scraper_run_job.apply(args=[cr["component_run_id"]], kwargs={"limit": 10})

        # Deduplication check: total unique papers in workspace should now be 3, not 4
        self.assertEqual(Paper.objects.filter(workspace=self.workspace).count(), 3)

    @patch("research_intelligence.tasks.step_2_download.fetch.get_scraper_provider")
    def test_rerun_step_2_download_skips_already_downloaded_pdfs(self, mock_get_scraper):
        mock_scraper = MagicMock()
        mock_scraper.download_file.return_value = b"%PDF-1.4 Mock PDF Content"
        mock_get_scraper.return_value = mock_scraper

        pipeline_run = PipelineRun.objects.create(workspace=self.workspace, status="running")
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            hash_id="paper_dl_001",
            title="Battery Paper",
            original_pdf_path="https://arxiv.org/pdf/2401.0001.pdf"
        )

        # Download 1: First download
        res1 = trigger_pdf_download_job_logic(self.user, pipeline_run_id=str(pipeline_run.id))
        data1 = json.loads(res1)
        self.assertTrue(data1["success"])
        paper.refresh_from_db()
        self.assertIsNotNone(paper.original_pdf_path)

        # Download 2: Re-running step 2 should handle paper with existing PDF gracefully without error
        res2 = trigger_pdf_download_job_logic(self.user, pipeline_run_id=str(pipeline_run.id))
        data2 = json.loads(res2)
        self.assertTrue(data2["success"])

    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_rerun_step_4_screening_with_updated_criteria_updates_decisions(self, mock_llm):
        pipeline_run = PipelineRun.objects.create(workspace=self.workspace, status="running")
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            hash_id="screen_paper_001",
            title="Solid-State Polymer Electrolytes",
            abstract="We investigate solid-state polymer electrolyte batteries.",
            screening_status="pending"
        )

        # Screening 1: Passes initial criteria
        mock_llm.return_value = (
            {"passed": True, "reasoning": "Directly evaluates solid-state battery technology."},
            {"prompt_tokens": 100, "candidates_tokens": 50}
        )
        trigger_screening_job_logic(self.user, pipeline_run_id=str(pipeline_run.id))
        paper.refresh_from_db()
        self.assertEqual(paper.screening_status, "abstract_passed")

        # Now user updates workspace rejection criteria to strictly reject polymer electrolytes
        self.workspace.abstract_rejection_criteria = ["Reject any polymer electrolytes."]
        self.workspace.save()

        # Screening 2: Re-run screening with updated criteria -> Rejects paper
        mock_llm.return_value = (
            {"passed": False, "reasoning": "Rejected due to polymer electrolyte exclusion criteria."},
            {"prompt_tokens": 100, "candidates_tokens": 50}
        )
        trigger_screening_job_logic(self.user, pipeline_run_id=str(pipeline_run.id))
        paper.refresh_from_db()
        self.assertEqual(paper.screening_status, "rejected")
        self.assertIn("polymer electrolyte exclusion", paper.screening_reasoning)

    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_rerun_step_5_extraction_and_step_6_signal_scoring(self, mock_llm):
        pipeline_run = PipelineRun.objects.create(workspace=self.workspace, status="running")
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            hash_id="ext_score_paper_001",
            title="High Energy Density Solid State Battery",
            abstract="500 Wh/kg solid state battery with 1000 cycles.",
            screening_status="accepted"
        )

        # Mock Step 5 Extraction Response
        mock_llm.return_value = (
            {
                "energy_density": 500.0,
                "cycle_life": 1000.0
            },
            {"prompt_tokens": 120, "candidates_tokens": 60}
        )

        # 1. Trigger Step 5 (Extraction)
        res_ext = trigger_extraction_job_logic(self.user, pipeline_run_id=str(pipeline_run.id))
        self.assertTrue(json.loads(res_ext)["success"])
        self.assertEqual(Extraction.objects.filter(paper=paper).count(), 1)

        # 2. Trigger Step 6 (Signal Scoring)
        # formula: 0.5 * energy_density + 0.5 * cycle_life = 0.5*500 + 0.5*1000 = 750.0
        res_score1 = trigger_signal_score_job_logic(self.user, pipeline_run_id=str(pipeline_run.id))
        self.assertTrue(json.loads(res_score1)["success"])
        paper.refresh_from_db()
        self.assertEqual(paper.signal_score, 750.0)

        # 3. Change signal score formula in workspace and re-run Step 6
        # new formula: 0.8 * energy_density + 0.2 * cycle_life = 0.8*500 + 0.2*1000 = 400 + 200 = 600.0
        self.workspace.signal_score_code = "return 0.8 * energy_density + 0.2 * cycle_life"
        self.workspace.save()

        res_score2 = trigger_signal_score_job_logic(self.user, pipeline_run_id=str(pipeline_run.id))
        self.assertTrue(json.loads(res_score2)["success"])
        paper.refresh_from_db()
        self.assertEqual(paper.signal_score, 600.0)

    @patch("research_intelligence.tasks.step_4_screening.abstract.execute_screening_job")
    @patch("research_intelligence.tasks.step_2_download.fetch.execute_pdf_download_job")
    @patch("research_intelligence.tasks.step_3_ocr.convert.execute_ocr_job")
    @patch("research_intelligence.tasks.step_4_screening.full_text.execute_full_text_screening_job")
    @patch("research_intelligence.tasks.step_5_extraction.extract.execute_extraction_job")
    @patch("research_intelligence.tasks.step_6_signal_score.scorer.execute_signal_score_job")
    def test_restart_autonomous_agent_from_step_4_screening_onwards(
        self,
        mock_step6,
        mock_step5,
        mock_step4_ft,
        mock_step3_ocr,
        mock_step2_dl,
        mock_step4
    ):
        """
        Simulate an autonomous agent that is reset / restarted from abstract screening
        and verify that the state engine chains through download -> extraction -> signal_score -> completed.
        """
        pipeline_run = PipelineRun.objects.create(workspace=self.workspace, status="running", current_stage="abstract_screening")
        ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type="search",
            component_name="workspace_search",
            status="completed"
        )
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            hash_id="resume_paper_001",
            title="Chalcogenide Solid Battery",
            abstract="Chalcogenide battery.",
            screening_status="pending"
        )

        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=pipeline_run,
            name="Restartable Agent",
            status="running",
            current_step="abstract_screening",
            configuration_override={"skip_full_text_screening": True}
        )

        def _finish_comp_run(cid, **kw):
            ComponentRun.objects.filter(id=cid).update(status="completed")
            Paper.objects.filter(pipeline_run=pipeline_run).update(screening_status="abstract_passed")
            res = MagicMock()
            res.id = "task-mock-id"
            return res

        mock_step4.side_effect = _finish_comp_run
        mock_step4.delay.side_effect = _finish_comp_run
        mock_step2_dl.side_effect = _finish_comp_run
        mock_step2_dl.delay.side_effect = _finish_comp_run
        mock_step3_ocr.side_effect = _finish_comp_run
        mock_step3_ocr.delay.side_effect = _finish_comp_run
        mock_step4_ft.side_effect = _finish_comp_run
        mock_step4_ft.delay.side_effect = _finish_comp_run
        mock_step5.side_effect = _finish_comp_run
        mock_step5.delay.side_effect = _finish_comp_run
        mock_step6.side_effect = _finish_comp_run
        mock_step6.delay.side_effect = _finish_comp_run

        # Tick 1: Run Abstract Screening
        tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "abstract_screening")

        # Tick 2: Abstract Screening -> Download
        tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "download")

        # Tick 3: Download -> Extraction (since ocr skipped and skip_full_text_screening=True)
        tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "extraction")

        # Tick 4: Extraction -> Signal Score
        tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.current_step, "signal_score")

        # Tick 5: Signal Score -> Completed
        tick_agent_process(str(agent.id))
        agent.refresh_from_db()
        self.assertEqual(agent.status, "completed")
        self.assertEqual(agent.current_step, "completed")
