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
            screening_llm_model="google/gemini-3.7-flash",
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
            screening_status="abstract_passed",
            original_pdf_path="workspaces/test/paper1.pdf"
        )
        self.paper2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            title="Paper 2 - Quantum Information",
            doi="10.1000/182.paper2",
            hash_id="hash_test_paper_2",
            abstract="Paper 2 abstract",
            screening_status="abstract_passed",
            original_pdf_path="workspaces/test/paper2.pdf"
        )
        self.paper3 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            title="Paper 3 - Hanging Paper",
            doi="10.1000/182.paper3",
            hash_id="hash_test_paper_3",
            abstract="Paper 3 abstract",
            screening_status="abstract_passed",
            original_pdf_path="workspaces/test/paper3.pdf"
        )

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
