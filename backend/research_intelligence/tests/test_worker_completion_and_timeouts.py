import time
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    ComponentRun,
    Paper,
    PaperMetric,
    ResearchAgentProcess,
    ExtractionDefinition,
)
from research_intelligence.tasks.step_4_screening.full_text import execute_full_text_screening_job
from research_intelligence.tasks.step_4_screening.abstract import execute_screening_job
from research_intelligence.tasks.step_5_extraction.extract import execute_extraction_job
from research_intelligence.tasks.auxiliary.zombie_watchdog import reap_zombie_tasks


class WorkerCompletionAndTimeoutsTestCase(TestCase):
    """
    Tests ensuring that Celery workers gracefully handle timeouts,
    update component run and pipeline run statuses upon completion,
    and trigger the DAG state transitions without getting stuck.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Timeout Test Workspace",
            screening_llm_model="google/gemini-3.8-flash",
            ocr_provider="local"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="screening"
        )
        self.agent_process = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            status="running",
            current_step="full_text_screening"
        )

        # Create 3 test papers with unique identifiers and hash_ids
        self.paper1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            title="Paper 1 - High Energy Physics",
            doi="10.1000/182.paper1",
            hash_id="hash_test_paper_1",
            abstract="Paper 1 abstract",
            original_pdf_path="workspaces/test/paper1.pdf"
        )
        PaperMetric.objects.create(paper=self.paper1, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="abstract_passed")
        self.paper2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            title="Paper 2 - Quantum Information",
            doi="10.1000/182.paper2",
            hash_id="hash_test_paper_2",
            abstract="Paper 2 abstract",
            original_pdf_path="workspaces/test/paper2.pdf"
        )
        PaperMetric.objects.create(paper=self.paper2, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="abstract_passed")
        self.paper3 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            title="Paper 3 - Hanging Paper",
            doi="10.1000/182.paper3",
            hash_id="hash_test_paper_3",
            abstract="Paper 3 abstract",
            original_pdf_path="workspaces/test/paper3.pdf"
        )
        PaperMetric.objects.create(paper=self.paper3, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="abstract_passed")

    @patch("research_intelligence.tasks.step_4_screening.full_text.screen_full_text")
    def test_full_text_screening_completes_and_transitions_status(self, mock_screen):
        """
        Verifies that when all papers finish screening, the component run and
        pipeline run statuses are updated to completed and the orchestrator is ticked.
        """
        mock_screen.side_effect = [
            {"success": True, "passed": True, "screening_status": "full_text_passed", "reasoning": "Pass 1", "usage": {"tokens_in": 100, "tokens_out": 50}},
            {"success": True, "passed": False, "screening_status": "rejected", "reasoning": "Fail 2", "usage": {"tokens_in": 100, "tokens_out": 50}},
            {"success": True, "passed": True, "screening_status": "full_text_passed", "reasoning": "Pass 3", "usage": {"tokens_in": 100, "tokens_out": 50}},
        ]

        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="full_text_screening",
            status="pending"
        )

        res = execute_full_text_screening_job(str(comp_run.id), max_workers=2)
        self.assertTrue(res)

        comp_run.refresh_from_db()
        self.assertEqual(comp_run.status, "completed")
        self.assertIsNotNone(comp_run.completed_at)
        self.assertEqual(comp_run.metrics["passed"], 2)
        self.assertEqual(comp_run.metrics["rejected"], 1)

    @patch("research_intelligence.tasks.step_4_screening.full_text.screen_full_text")
    def test_full_text_screening_batch_timeout_recovery(self, mock_screen):
        """
        Verifies that if a paper hangs in the thread pool, timeout recovery catches it,
        marks that individual paper as failed/timed out, and still successfully completes
        the ComponentRun and advances the state machine.
        """
        def fake_screen(paper_id, workspace_id, **kwargs):
            if str(paper_id) == str(self.paper3.id):
                # Simulate timeout or thread hang
                raise TimeoutError("Simulated LLM call hang / timeout")
            return {
                "success": True,
                "passed": True,
                "screening_status": "full_text_passed",
                "reasoning": "Accepted criteria",
                "usage": {"tokens_in": 100, "tokens_out": 50}
            }

        mock_screen.side_effect = fake_screen

        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="full_text_screening",
            status="pending"
        )

        res = execute_full_text_screening_job(str(comp_run.id), max_workers=2)
        self.assertTrue(res)

        comp_run.refresh_from_db()
        self.assertEqual(comp_run.status, "completed")
        self.assertIsNotNone(comp_run.completed_at)
        self.assertEqual(comp_run.metrics["passed"], 2)
        self.assertEqual(comp_run.metrics["failed"], 1)

    @patch("research_intelligence.tasks.step_5_extraction.extract._run_single_extraction_worker")
    def test_extraction_batch_timeout_recovery(self, mock_extract):
        """
        Verifies that if an extraction task hangs, the batch timeout recovery
        properly logs it, records the failure, and completes the ComponentRun.
        """
        ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Assessment",
            system_prompt="Assess TRL",
            response_schema={
                "type": "object",
                "properties": {
                    "trl": {"type": "integer"}
                },
                "required": ["trl"]
            },
            is_active=True
        )

        def fake_extract(paper, definition, workspace):
            if str(paper.id) == str(self.paper3.id):
                raise TimeoutError("Simulated extraction hang")
            return {
                "success": True,
                "paper_id": str(paper.id),
                "definition_id": str(definition.id),
                "definition_name": definition.name,
                "extracted_data": {"trl": 4},
                "usage": {"tokens_in": 200, "tokens_out": 80}
            }

        mock_extract.side_effect = fake_extract

        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="extraction",
            component_name="extraction",
            status="pending"
        )

        res = execute_extraction_job(str(comp_run.id), max_workers=2)
        self.assertTrue(res)

        comp_run.refresh_from_db()
        self.assertEqual(comp_run.status, "completed")
        self.assertIsNotNone(comp_run.completed_at)
        self.assertEqual(comp_run.metrics["extractions_created"], 2)
        self.assertEqual(comp_run.metrics["failed"], 1)

    def test_zombie_watchdog_recovers_completed_metrics_and_ticks_orchestrator(self):
        """
        Verifies that when a component run has all items processed but its status
        remained 'running' due to a dropped callback, the watchdog recovers it
        to 'completed' and triggers the orchestrator.
        """
        stale_time = timezone.now() - timedelta(minutes=45)
        stuck_comp = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="full_text_screening",
            status="running",
            metrics={
                "total_to_screen": 246,
                "total_screened": 246,
                "passed": 210,
                "rejected": 35,
                "failed": 1,
                "percent_complete": 100.0
            }
        )
        ComponentRun.objects.filter(id=stuck_comp.id).update(started_at=stale_time)

        stats = reap_zombie_tasks(max_component_age_minutes=30)
        
        stuck_comp.refresh_from_db()
        self.assertEqual(stuck_comp.status, "completed")
        self.assertIsNotNone(stuck_comp.completed_at)
        self.assertIn("recovered completed", stats["details"][0])

    @patch("research_intelligence.tasks.step_5_extraction.extract._run_single_extraction_worker")
    @patch("research_intelligence.tasks.orchestrator.agent_engine.notify_pipeline_orchestrator_tick")
    def test_extraction_total_failure_fails_pipeline_and_component(self, mock_notify, mock_extract):
        """
        Verifies that if all extractions fail (0 succeeded), the ComponentRun
        and PipelineRun are marked 'failed' and execution halts.
        """
        ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Methodology",
            system_prompt="Assess Method",
            response_schema={"type": "object"},
            is_active=True
        )

        mock_extract.return_value = {
            "success": False,
            "error": "Simulated complete outage",
            "paper_id": "test",
            "definition_id": str(ext_def.id)
        }

        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="extraction",
            component_name="extraction",
            status="pending"
        )

        res = execute_extraction_job(str(comp_run.id), max_workers=2)
        self.assertFalse(res)

        comp_run.refresh_from_db()
        self.pipeline_run.refresh_from_db()

        self.assertEqual(comp_run.status, "failed")
        self.assertIn("All 3 extractions failed", comp_run.error_message)
        self.assertEqual(self.pipeline_run.status, "failed")
        self.assertIn("Extraction step failed completely", self.pipeline_run.status_message)
        mock_notify.assert_called_with(self.pipeline_run)

    @patch("research_intelligence.tasks.step_5_extraction.extract._run_single_extraction_worker")
    def test_extraction_resume_skips_already_completed_extractions(self, mock_extract):
        """
        Verifies that if extractions were already created in a previous attempt,
        the task gracefully resumes from where it left off, avoiding duplicate calls.
        """
        from research_intelligence.models import Extraction
        ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Architecture",
            system_prompt="Assess Architecture",
            response_schema={"type": "object"},
            is_active=True
        )

        # Pre-seed one successful extraction in DB for paper1
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper1,
            extraction_definition=ext_def,
            category="Architecture",
            fields_data={"layer": "hybrid"},
            validation_status="pass",
            confidence_score=0.95
        )

        mock_extract.return_value = {
            "success": True,
            "paper_id": "other",
            "definition_id": str(ext_def.id),
            "definition_name": ext_def.name,
            "extracted_data": {},
            "usage": {"tokens_in": 100, "tokens_out": 50}
        }

        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="extraction",
            component_name="extraction",
            status="pending"
        )

        res = execute_extraction_job(str(comp_run.id), max_workers=2)
        self.assertTrue(res)

        # Mock extract should only have been called for paper2 and paper3 (2 times), NOT paper1!
        self.assertEqual(mock_extract.call_count, 2)

        comp_run.refresh_from_db()
        self.assertEqual(comp_run.status, "completed")
        self.assertEqual(comp_run.metrics["extractions_created"], 3)
        self.assertEqual(comp_run.metrics["failed"], 0)

    @patch("research_intelligence.tasks.orchestrator.agent_engine.notify_pipeline_orchestrator_tick")
    def test_zombie_watchdog_reaping_failed_component_fails_pipeline(self, mock_notify):
        """
        Verifies that when the zombie watchdog reaps an in-flight dead component
        as failed, it immediately marks the associated PipelineRun as failed.
        """
        stale_time = timezone.now() - timedelta(minutes=45)
        stuck_comp = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="extraction",
            component_name="extraction",
            status="running",
            metrics={"total_work_items": 130, "completed_extractions": 55, "failed_extractions": 0}
        )
        ComponentRun.objects.filter(id=stuck_comp.id).update(started_at=stale_time)

        stats = reap_zombie_tasks(max_component_age_minutes=30)

        stuck_comp.refresh_from_db()
        self.pipeline_run.refresh_from_db()

        self.assertEqual(stuck_comp.status, "failed")
        self.assertEqual(self.pipeline_run.status, "failed")
        self.assertIn("Pipeline terminated: Component 'extraction' reaped by watchdog as zombie", self.pipeline_run.status_message)
        self.assertEqual(stats["reaped_components"], 1)
        self.assertEqual(stats["reaped_pipelines"], 1)
        mock_notify.assert_called()
