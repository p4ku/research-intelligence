import uuid
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    ComponentRun,
    Paper,
    PaperMetric,
    Extraction,
    NarrativeReport,
)
from research_intelligence.admin import render_component_metrics_summary
from research_intelligence.tasks.orchestrator.dag import build_default_slr_dag


class TestCumulativeMetricsAndRerun(TestCase):
    """
    Validates cumulative step metrics rendering in Django admin,
    resumed batch accumulation, and clean state resets on step reruns.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="metric_admin", password="password123")
        self.workspace = Workspace.objects.create(
            name="Metrics Workspace",
            screening_llm_model="gemini-2.5-flash",
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status='running',
            total_papers_passed_screening=457
        )

    def test_render_component_metrics_summary_clean_batch(self):
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type='screening',
            component_name='abstract_screening',
            metrics={
                "total_screened": 1559,
                "passed": 558,
                "rejected": 999,
                "withdrawn": 2
            }
        )
        html = render_component_metrics_summary(comp_run)
        self.assertIn("1559 screened:", html)
        self.assertIn("558 passed", html)
        self.assertIn("999 rejected", html)
        self.assertIn("(2 withdrawn)", html)

    def test_render_component_metrics_summary_resumed_batch(self):
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type='screening',
            component_name='full_text_screening',
            metrics={
                "total_screened": 558,
                "passed": 457,
                "rejected": 101,
                "withdrawn": 0,
                "newly_screened": 298,
                "resumed_from_cache": 260
            }
        )
        html = render_component_metrics_summary(comp_run)
        self.assertIn("558 screened:", html)
        self.assertIn("457 passed", html)
        self.assertIn("101 rejected", html)
        self.assertIn("(298 in batch, 260 cached)", html)

    def test_render_component_metrics_summary_legacy_partial_batch_fallback(self):
        # In legacy runs, total_screened was 298 (the last batch) and passed was 245,
        # but pipeline_run.total_papers_passed_screening was 457.
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type='screening',
            component_name='full_text_screening',
            metrics={
                "total_screened": 298,
                "passed": 245,
                "rejected": 53,
                "withdrawn": 0
            }
        )
        html = render_component_metrics_summary(comp_run)
        self.assertIn("298 screened:", html)
        self.assertIn("245 passed", html)
        self.assertIn("(245 in last batch, 457 total passed)", html)

    def test_dag_rerun_from_full_text_cleans_metrics_and_downstream_data(self):
        dag = build_default_slr_dag(self.workspace)

        # Setup 3 papers:
        # Paper 1: passed abstract and full-text
        # Paper 2: passed abstract, rejected full-text
        # Paper 3: rejected at abstract
        p1 = Paper.objects.create(workspace=self.workspace, title="P1 Paper Title", doi="10.1001/p1", hash_id="hash_p1")
        p2 = Paper.objects.create(workspace=self.workspace, title="P2 Paper Title", doi="10.1001/p2", hash_id="hash_p2")
        p3 = Paper.objects.create(workspace=self.workspace, title="P3 Paper Title", doi="10.1001/p3", hash_id="hash_p3")

        pm1 = PaperMetric.objects.create(
            workspace=self.workspace,
            paper=p1,
            pipeline_run=self.pipeline_run,
            screening_status='full_text_passed',
            abstract_screening_reasoning="Abstract passed",
            full_text_screening_reasoning="Full text accepted",
            metrics_data={"abstract_screening": {"passed": True}, "full_text_screening": {"passed": True}},
            signal_score=92.5
        )
        pm2 = PaperMetric.objects.create(
            workspace=self.workspace,
            paper=p2,
            pipeline_run=self.pipeline_run,
            screening_status='rejected',
            abstract_screening_reasoning="Abstract passed",
            full_text_screening_reasoning="Full text rejected - out of scope",
            metrics_data={"abstract_screening": {"passed": True}, "full_text_screening": {"passed": False}},
            signal_score=None
        )
        pm3 = PaperMetric.objects.create(
            workspace=self.workspace,
            paper=p3,
            pipeline_run=self.pipeline_run,
            screening_status='rejected',
            abstract_screening_reasoning="Abstract rejected",
            metrics_data={"abstract_screening": {"passed": False}},
            signal_score=None
        )

        Extraction.objects.create(
            workspace=self.workspace,
            paper=p1,
            category="parameter",
            fields_data={"param": "value"}
        )
        NarrativeReport.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            title="Brief",
            content_markdown="# Brief"
        )

        # Trigger clean rerun from full_text_screening
        dag.rerun_from_node(self.pipeline_run, "full_text_screening")

        pm1.refresh_from_db()
        pm2.refresh_from_db()
        pm3.refresh_from_db()

        # p1 and p2 should have been reset to abstract_passed (ready for full text screening from zero)
        self.assertEqual(pm1.screening_status, 'abstract_passed')
        self.assertEqual(pm1.full_text_screening_reasoning, '')
        self.assertNotIn('full_text_screening', pm1.metrics_data)
        self.assertIsNone(pm1.signal_score)

        self.assertEqual(pm2.screening_status, 'abstract_passed')
        self.assertEqual(pm2.full_text_screening_reasoning, '')
        self.assertNotIn('full_text_screening', pm2.metrics_data)

        # p3 was rejected at abstract stage, so it must remain rejected!
        self.assertEqual(pm3.screening_status, 'rejected')

        # Downstream Extractions and Reports must be wiped
        self.assertEqual(Extraction.objects.filter(workspace=self.workspace).count(), 0)
        self.assertEqual(NarrativeReport.objects.filter(pipeline_run=self.pipeline_run).count(), 0)

        # Pipeline total_papers_passed_screening should reflect only abstract passed (2)
        self.pipeline_run.refresh_from_db()
        self.assertEqual(self.pipeline_run.total_papers_passed_screening, 2)

    from unittest.mock import patch

    @patch("research_intelligence.tasks.step_4_screening.full_text.screen_full_text")
    def test_execute_full_text_screening_job_cumulative_metrics(self, mock_screen):
        from research_intelligence.tasks.step_4_screening.full_text import execute_full_text_screening_job

        # Paper 1: Already processed in batch 1
        p1 = Paper.objects.create(workspace=self.workspace, title="Batch 1 Paper", hash_id="h_b1")
        PaperMetric.objects.create(
            workspace=self.workspace,
            paper=p1,
            pipeline_run=self.pipeline_run,
            screening_status='full_text_passed',
            abstract_screening_reasoning="Abstract passed",
            full_text_screening_reasoning="Batch 1 pass",
            metrics_data={"abstract_screening": {"passed": True}, "full_text_screening": {"passed": True}}
        )

        # Paper 2: Pending full-text screening (abstract_passed)
        p2 = Paper.objects.create(workspace=self.workspace, title="Batch 2 Paper", hash_id="h_b2")
        PaperMetric.objects.create(
            workspace=self.workspace,
            paper=p2,
            pipeline_run=self.pipeline_run,
            screening_status='abstract_passed',
            abstract_screening_reasoning="Abstract passed",
            metrics_data={"abstract_screening": {"passed": True}}
        )

        # Create prior abstract screening component run so full_text targets abstract_passed
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type='screening',
            component_name='abstract_screening',
            status='completed'
        )

        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="full_text_screening",
            status="pending"
        )

        def mock_impl(*args, **kwargs):
            paper = args[0] if args else kwargs.get('paper')
            PaperMetric.objects.filter(paper=paper, pipeline_run=self.pipeline_run).update(
                screening_status="full_text_passed"
            )
            return {
                "success": True,
                "passed": True,
                "screening_status": "full_text_passed",
                "reasoning": "Batch 2 evaluated",
                "decision_category": "ACCEPTED",
                "usage": {"tokens_in": 100, "tokens_out": 50}
            }
        mock_screen.side_effect = mock_impl

        success = execute_full_text_screening_job(str(comp_run.id), max_workers=1)
        self.assertTrue(success)

        comp_run.refresh_from_db()
        # Cumulative metrics: total_screened should be 2 (1 cached + 1 new), passed 2, resumed 1, new 1
        self.assertEqual(comp_run.metrics["total_screened"], 2)
        self.assertEqual(comp_run.metrics["passed"], 2)
        self.assertEqual(comp_run.metrics["resumed_from_cache"], 1)
        self.assertEqual(comp_run.metrics["newly_screened"], 1)

        self.pipeline_run.refresh_from_db()
        self.assertEqual(self.pipeline_run.total_papers_passed_screening, 2)
