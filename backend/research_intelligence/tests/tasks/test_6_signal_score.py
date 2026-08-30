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
            abstract="Novel routing algorithm in NISQ devices with high fidelity.",
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

        # Verify saved on Paper model
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.signal_score, 7.5)

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
