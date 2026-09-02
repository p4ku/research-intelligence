from django.test import TestCase
from unittest.mock import patch, MagicMock
from ...models import Workspace, PipelineRun, Paper, PaperMetric, ComponentRun, Extraction, ExtractionDefinition
from ...tasks.step_6_signal_score.scorer import (
    compute_paper_signal_score,
    execute_signal_score_job,
    _sanitize_identifier,
)


class SignalScoreTaskTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Signal Score Test Project",
            llm_provider="google",
            signal_score_code="score = 0.5 * fit_score + 0.3 * novelty_score + 0.2 * trl_level\nreturn round(score, 2)"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="test_hash_signal_score_1",
            title="Advanced Quantum Routing",
            authors="Alice Q",
            abstract="Novel routing algorithm in NISQ devices with high fidelity."
        )
        PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="full_text_passed"
        )
        self.def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Schwarz Fit",
            exit_metric="fit_score",
            system_prompt="Extract fit",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object", "properties": {"fit_score": {"type": "number"}}}
        )
        self.def_novelty = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Score",
            exit_metric="novelty_score",
            system_prompt="Extract novelty",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object", "properties": {"novelty_score": {"type": "number"}}}
        )
        self.def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
            exit_metric="trl_level",
            system_prompt="Extract TRL",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object", "properties": {"trl_level": {"type": "number"}}}
        )

        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.def_fit,
            fields_data={"fit_score": 8.0}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.def_novelty,
            fields_data={"novelty_score": 9.0}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.def_trl,
            fields_data={"trl_level": 4.0}
        )

    def test_sanitize_identifier(self):
        self.assertEqual(_sanitize_identifier("TRL Level"), "trl_level")
        self.assertEqual(_sanitize_identifier("Fit-Score (0-100)"), "fit_score_0_100")
        self.assertEqual(_sanitize_identifier("123abc"), "v_123abc")
        self.assertEqual(_sanitize_identifier(""), "param")

    def test_compute_paper_signal_score(self):
        # 0.5 * 8.0 + 0.3 * 9.0 + 0.2 * 4.0 = 4.0 + 2.7 + 0.8 = 7.5
        score, details = compute_paper_signal_score(self.paper, pipeline_run=self.pipeline_run)
        self.assertEqual(score, 7.5)
        self.assertIsNone(details.get("error"))

        # Verify saved on PaperMetric model
        metric = PaperMetric.objects.get(paper=self.paper, pipeline_run=self.pipeline_run)
        self.assertEqual(metric.signal_score, 7.5)
        self.assertEqual(metric.metrics_data.get("fit_score"), 8.0)

    def test_execute_signal_score_job(self):
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="signal_score",
            component_name="signal_scorer",
            status="running"
        )

        res = execute_signal_score_job(str(comp_run.id))
        self.assertTrue(res["success"])
        self.assertEqual(res["metrics"]["scored_count"], 1)

        comp_run.refresh_from_db()
        self.assertEqual(comp_run.status, "completed")
        self.assertEqual(comp_run.metrics.get("scored_count"), 1)


class ScorerSingleSourceOfTruthTests(TestCase):
    """
    Dedicated tests verifying that:
    1. Paper table has NO signal_score column in database.
    2. compute_paper_signal_score and execute_signal_score_job write exclusively to PaperMetric.
    3. Multiple pipeline runs (including reprocess runs) score the same paper independently.
    4. Runtime AST evaluation errors in scorer store failure details on PaperMetric without corrupting Paper.
    """
    def setUp(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        User = get_user_model()
        self.user = User.objects.create_user(username="scorer_test_user", password="password")
        self.workspace = Workspace.objects.create(
            name="Scorer SSOT Workspace",
            signal_score_code="score = fit * 10\nreturn score"
        )
        self.run_1 = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run_1,
            hash_id="ssot_paper_hash_001",
            title="SSOT Quantum Routing"
        )
        PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.run_1,
            workspace=self.workspace,
            screening_status="full_text_passed"
        )
        self.def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Fit",
            exit_metric="fit",
            system_prompt="Extract fit",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"}
        )
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.def_fit,
            fields_data={"fit": 7.0}
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_paper_table_has_no_signal_score_column(self):
        """Verify that Paper database table has no physical 'signal_score' or 'signal_score_details' columns."""
        paper_values = Paper.objects.filter(id=self.paper.id).values().first()
        self.assertNotIn("signal_score", paper_values, "signal_score must NOT exist as a column in Paper DB table")
        self.assertNotIn("signal_score_details", paper_values, "signal_score_details must NOT exist as a column in Paper DB table")

    def test_scorer_writes_strictly_to_papermetric(self):
        """compute_paper_signal_score must persist to PaperMetric and keep Paper row clean."""
        score, details = compute_paper_signal_score(self.paper, pipeline_run=self.run_1)
        self.assertEqual(score, 70.0)

        # PaperMetric exists
        metric = PaperMetric.objects.get(paper=self.paper, pipeline_run=self.run_1)
        self.assertEqual(metric.signal_score, 70.0)
        self.assertEqual(metric.signal_score_details.get("score"), 70.0)

        # Paper DB row has no signal_score column
        paper_raw = Paper.objects.filter(id=self.paper.id).values().first()
        self.assertNotIn("signal_score", paper_raw)

    def test_reprocessed_run_scorer_isolation(self):
        """
        Run 1 scores paper at 70.0.
        Run 2 modifies formula, reprocesses paper, and scores at 95.0.
        Verify Run 1 retains 70.0 and Run 2 stores 95.0 independently.
        """
        # 1. Execute Run 1 scoring job
        comp_run_1 = ComponentRun.objects.create(
            pipeline_run=self.run_1,
            step_type="signal_score",
            component_name="signal_scorer",
            status="running"
        )
        res_1 = execute_signal_score_job(str(comp_run_1.id))
        self.assertTrue(res_1["success"])
        metric_1 = PaperMetric.objects.get(paper=self.paper, pipeline_run=self.run_1)
        self.assertEqual(metric_1.signal_score, 70.0)

        # 2. Create Run 2 (reprocess existing) with updated workspace formula
        self.workspace.signal_score_code = "score = fit * 10 + 25\nreturn score"
        self.workspace.save()

        run_2 = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            reprocess_existing=True
        )
        self.paper.reprocessed_runs.add(run_2)
        PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=run_2,
            workspace=self.workspace,
            screening_status="full_text_passed"
        )

        comp_run_2 = ComponentRun.objects.create(
            pipeline_run=run_2,
            step_type="signal_score",
            component_name="signal_scorer",
            status="running"
        )
        res_2 = execute_signal_score_job(str(comp_run_2.id))
        self.assertTrue(res_2["success"])

        # Verify Run 2 metric is 95.0
        metric_2 = PaperMetric.objects.get(paper=self.paper, pipeline_run=run_2)
        self.assertEqual(metric_2.signal_score, 95.0)

        # Verify Run 1 metric was NOT mutated and remains 70.0
        metric_1.refresh_from_db()
        self.assertEqual(metric_1.signal_score, 70.0, "Run 1 PaperMetric must not be overwritten by Run 2")

    def test_scorer_ast_error_handling_stores_details_in_papermetric(self):
        """When AST code violates sandbox or raises an error, error details are saved in PaperMetric."""
        self.workspace.signal_score_code = "import os\nreturn 10"
        self.workspace.save()

        score, details = compute_paper_signal_score(self.paper, pipeline_run=self.run_1)
        self.assertEqual(score, 0.0)
        self.assertIsNotNone(details.get("error"))
        self.assertIn("Import", details.get("error", ""))

        metric = PaperMetric.objects.get(paper=self.paper, pipeline_run=self.run_1)
        self.assertEqual(metric.signal_score, 0.0)
        self.assertIn("Import", metric.signal_score_details.get("error", ""))
