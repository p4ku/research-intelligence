import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    ExtractionDefinition,
    Paper,
    Extraction,
    PaperMetric,
    PipelineRun,
)
from research_intelligence.services.scorecard_service import (
    resolve_dimension_scale,
    format_definitions_metadata,
    build_paper_scorecard_data,
)
from research_intelligence.tasks.step_6_signal_score.scorer import (
    compute_paper_signal_score,
    extract_paper_parameters,
)

User = get_user_model()


class Issue138AndFrontendMetricsTestCase(TestCase):
    """
    Tests for Issue #138 and #131:
    - Verifies Extraction.exit_metric NEVER prioritizes primary_frontend_metric (#138).
    - Verifies setting primary_frontend_metric does NOT alter calculate_signal_score (#138).
    - Verifies shared resolve_dimension_scale aligns WorkspaceSummary and dimensions max (#131).
    - Verifies is_risk_and_affiliation metadata in format_definitions_metadata.
    """

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="analyst_user",
            email="analyst@schwarz.de",
            password="test_password123!"
        )
        self.workspace = Workspace.objects.create(
            name="AI Robotics Workspace",
            signal_score_code="score = fit_score * 0.8 + trl * 2.0\nreturn score",
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role="analyst"
        )

        # Definition with exit_metrics = 'fit_score'
        self.def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Schwarz Fit",
            order=1,
            exit_metrics="fit_score",
            response_schema={"type": "object", "properties": {"fit_score": {"type": "number"}, "fit_insight": {"type": "string"}}},
            is_active=True,
        )

        # Definition with TRL
        self.def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Technology Readiness Level (TRL)",
            order=2,
            exit_metrics="trl",
            response_schema={"type": "object", "properties": {"trl": {"type": "integer"}}},
            is_active=True,
        )

        # Paper
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            title="Advanced Robotics Control in Warehouses",
            authors="Dr. Schmidt",
            screening_status="accepted",
        )

        # Extractions
        self.ext_fit = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=self.def_fit,
            fields_data={
                "fields": {
                    "fit_score": 75.0,
                    "fit_insight": "2019.0 was the year of baseline robotics deployment.",
                }
            },
            validation_status="pass",
        )
        self.ext_trl = Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=self.def_trl,
            fields_data={
                "fields": {
                    "trl": 6,
                    "trl_label": "System prototype demonstration in operational environment",
                }
            },
            validation_status="pass",
        )

    def test_issue_138_setting_primary_frontend_metric_does_not_mutate_exit_metric(self):
        """
        Fix for Issue #138:
        Setting primary_frontend_metric to a display key (or descriptive text field)
        must NEVER alter Extraction.exit_metric.
        """
        # Baseline: exit_metric reads fit_score -> "75.0"
        self.assertEqual(self.ext_fit.exit_metric, "75.0")

        # Now configure primary_frontend_metric to point to fit_insight
        self.def_fit.primary_frontend_metric = "fit_insight"
        self.def_fit.save(update_fields=["primary_frontend_metric"])

        # Refresh from DB
        self.ext_fit.refresh_from_db()

        # In buggy #138 code, ext_fit.exit_metric would return "2019.0" (parsed from fit_insight)
        # With the fix, ext_fit.exit_metric must remain "75.0"
        self.assertEqual(
            self.ext_fit.exit_metric,
            "75.0",
            "Extraction.exit_metric must not be hijacked by primary_frontend_metric display setting!"
        )

    def test_issue_138_signal_score_calculation_is_isolated_from_frontend_metrics(self):
        """
        Verify that changing primary_frontend_metric on definitions has zero effect
        on compute_paper_signal_score and extract_paper_parameters.
        """
        # Baseline score calculation: 75.0 * 0.8 + 6 * 2.0 = 60.0 + 12.0 = 72.0
        score_before, details_before = compute_paper_signal_score(
            self.paper,
            preloaded_extractions=[self.ext_fit, self.ext_trl],
        )
        params_before = extract_paper_parameters(
            self.paper,
            preloaded_extractions=[self.ext_fit, self.ext_trl],
        )
        self.assertEqual(score_before, 72.0)
        self.assertEqual(params_before.get("fit_score"), 75.0)
        self.assertEqual(params_before.get("trl"), 6.0)

        # Set primary_frontend_metric on both definitions
        self.def_fit.primary_frontend_metric = "fit_insight"
        self.def_fit.save(update_fields=["primary_frontend_metric"])
        self.def_trl.primary_frontend_metric = "trl_label"
        self.def_trl.save(update_fields=["primary_frontend_metric"])

        score_after, details_after = compute_paper_signal_score(
            self.paper,
            preloaded_extractions=[self.ext_fit, self.ext_trl],
        )
        params_after = extract_paper_parameters(
            self.paper,
            preloaded_extractions=[self.ext_fit, self.ext_trl],
        )
        self.assertEqual(
            score_after,
            72.0,
            "Signal score must remain identical regardless of frontend display metrics!"
        )
        self.assertEqual(params_after.get("fit_score"), 75.0)
        self.assertEqual(params_after.get("trl"), 6.0)

    def test_shared_resolve_dimension_scale_aligns_metadata_and_dimensions(self):
        """
        Verify that resolve_dimension_scale ensures format_definitions_metadata
        and build_paper_scorecard_data agree on max (TRL = 9, (1-10) = 10, default = 100).
        """
        max_trl, is_trl = resolve_dimension_scale("Technology Readiness Level (TRL)")
        self.assertEqual(max_trl, 9)
        self.assertTrue(is_trl)

        max_ten, is_ten = resolve_dimension_scale("Feasibility Score (1-10)")
        self.assertEqual(max_ten, 10)
        self.assertFalse(is_ten)

        max_def, is_def = resolve_dimension_scale("Research Quality")
        self.assertEqual(max_def, 100)
        self.assertFalse(is_def)

        # End-to-end scorecard check
        data = build_paper_scorecard_data(self.paper)
        ws_defs = {d["name"]: d for d in data["workspace"]["definitions"]}
        paper_dims = {d["name"]: d for d in data["paper"]["dimensions"]}

        self.assertEqual(ws_defs["Technology Readiness Level (TRL)"]["max"], 9)
        self.assertEqual(paper_dims["Technology Readiness Level (TRL)"]["max"], 9)

        self.assertEqual(ws_defs["Schwarz Fit"]["max"], 100)
        self.assertEqual(paper_dims["Schwarz Fit"]["max"], 100)

    def test_definitions_metadata_includes_is_risk_and_affiliation(self):
        """
        Verify that format_definitions_metadata includes is_risk_and_affiliation flag.
        """
        def_risk = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Risk and Affiliation",
            order=3,
            exit_metrics="risk_score",
            response_schema={"type": "object"},
            is_active=True,
        )
        meta = format_definitions_metadata([self.def_fit, self.def_trl, def_risk])
        meta_by_name = {m["name"]: m for m in meta}

        self.assertFalse(meta_by_name["Schwarz Fit"]["is_risk_and_affiliation"])
        self.assertFalse(meta_by_name["Technology Readiness Level (TRL)"]["is_risk_and_affiliation"])
        self.assertTrue(meta_by_name["Risk and Affiliation"]["is_risk_and_affiliation"])
