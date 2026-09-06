"""
Comprehensive test suite validating dynamic extraction schema generation,
strict JSON Schema validation of LLM outputs (with negative failure tests),
and safe fallback behavior in dynamic signal scoring formulas.
"""
import json
from unittest.mock import patch, MagicMock
from django.test import TestCase

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    Paper,
    PaperMetric,
    ExtractionDefinition,
    Extraction,
)
from research_intelligence.tasks.step_5_extraction.extract import _run_single_extraction_worker
from research_intelligence.tasks.step_6_signal_score.scorer import compute_paper_signal_score, extract_paper_parameters


class DynamicExtractionSchemaAndScoringTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Aerospace Deep-Tech Radar",
            signal_score_code="""
score = 0.5 * fit_score + 0.3 * novelty_score + 0.2 * trl_level
return round(score * 10.0, 2)
"""
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="aero_paper_001",
            title="Hypersonic Thermal Protection System with Ceramic Composites",
            abstract="Experimental evaluation of silicon-carbide composites for atmospheric re-entry.",
            arxiv_id="2405.00001"
        )
        self.pm = PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="full_text_passed"
        )

        # 1. Dynamic Definition: TRL Level (requires number between 1-9)
        self.def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
            exit_metrics="trl_level",
            system_prompt="Assess Technology Readiness Level (1-9).",
            user_prompt_template="Assess paper: {paper_text}",
            response_schema={
                "type": "object",
                "properties": {
                    "trl_level": {"type": "number", "minimum": 1, "maximum": 9},
                    "reasoning": {"type": "string"}
                },
                "required": ["trl_level"]
            },
            is_active=True
        )

        # 2. Dynamic Definition: Fit Score (requires number 0-10)
        self.def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Fit Score",
            exit_metrics="fit_score",
            system_prompt="Assess mission fit score (0-10).",
            user_prompt_template="Assess paper: {paper_text}",
            response_schema={
                "type": "object",
                "properties": {
                    "fit_score": {"type": "number", "minimum": 0, "maximum": 10},
                    "evidence_quote": {"type": "string"}
                },
                "required": ["fit_score"]
            },
            is_active=True
        )

        # 3. Dynamic Definition: Novelty Score (requires number 0-10)
        self.def_nov = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Score",
            exit_metrics="novelty_score",
            system_prompt="Assess technological novelty (0-10).",
            user_prompt_template="Assess paper: {paper_text}",
            response_schema={
                "type": "object",
                "properties": {
                    "novelty_score": {"type": "number", "minimum": 0, "maximum": 10}
                },
                "required": ["novelty_score"]
            },
            is_active=True
        )

    def test_workspace_dynamic_composite_schema_synthesis(self):
        """
        Validates that Workspace.get_composite_extraction_schema() dynamically inspects
        all active extraction definitions and synthesizes a unified JSON Schema (Draft-07).
        """
        schema = self.workspace.get_composite_extraction_schema()

        self.assertEqual(schema["type"], "object")
        self.assertIn("properties", schema)
        self.assertIn("trl_level", schema["properties"])
        self.assertIn("fit_score", schema["properties"])
        self.assertIn("novelty_score", schema["properties"])

        self.assertEqual(schema["properties"]["trl_level"]["type"], "number")
        self.assertEqual(schema["properties"]["fit_score"]["type"], "number")
        self.assertIn("trl_level", schema["required"])
        self.assertIn("fit_score", schema["required"])
        self.assertIn("novelty_score", schema["required"])

        # Dynamically deactivate one definition -> schema updates dynamically
        self.def_nov.is_active = False
        self.def_nov.save()

        updated_schema = self.workspace.get_composite_extraction_schema()
        self.assertNotIn("novelty_score", updated_schema["properties"])
        self.assertNotIn("novelty_score", updated_schema["required"])
        self.assertEqual(len(updated_schema["required"]), 2)

    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    def test_schema_validation_negative_test_missing_required_fields(self, mock_get_provider):
        """
        Negative Test: LLM returns completely incorrect / missing fields (e.g. {"wrong_field": 123}).
        Verifies that:
        1. Extraction.validation_status is set to 'fail'.
        2. Extraction.review_required is set to True.
        3. Detailed schema errors are recorded in version_info['validation_errors'].
        """
        mock_provider = MagicMock()
        # Simulated rogue LLM response that violates the schema
        mock_provider.generate.return_value = {
            "wrong_field": "unrelated value",
            "hallucinated_param": 999
        }
        mock_get_provider.return_value = mock_provider

        res = _run_single_extraction_worker(
            paper=self.paper,
            definition=self.def_trl,
            workspace=self.workspace
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["validation_status"], "fail")

        ext = Extraction.objects.get(paper=self.paper, extraction_definition=self.def_trl)
        self.assertEqual(ext.validation_status, "fail")
        self.assertTrue(ext.review_required)
        self.assertIn("validation_errors", ext.version_info)
        errors = ext.version_info["validation_errors"]
        self.assertTrue(any("trl_level" in str(e) for e in errors))

    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    def test_schema_validation_negative_test_wrong_type(self, mock_get_provider):
        """
        Negative Test: LLM returns wrong datatype (string instead of number for fit_score).
        Verifies that JSON schema validation detects type mismatch and flags 'fail' or 'warn'.
        """
        mock_provider = MagicMock()
        mock_provider.generate.return_value = {
            "fit_score": "not_a_valid_float_number",
            "evidence_quote": "Valid quote"
        }
        mock_get_provider.return_value = mock_provider

        res = _run_single_extraction_worker(
            paper=self.paper,
            definition=self.def_fit,
            workspace=self.workspace
        )

        self.assertIn(res["validation_status"], ["fail", "warn"])
        ext = Extraction.objects.get(paper=self.paper, extraction_definition=self.def_fit)
        self.assertTrue(ext.review_required)
        self.assertTrue(len(ext.version_info.get("validation_errors", [])) > 0)

    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    def test_schema_validation_positive_test(self, mock_get_provider):
        """
        Positive Test: LLM returns fully compliant data matching JSON Schema and exit_metric.
        Verifies that validation_status is 'pass' and review_required is False.
        """
        mock_provider = MagicMock()
        mock_provider.generate.return_value = {
            "trl_level": 6.0,
            "reasoning": "Prototype validated in relevant hypersonic wind tunnel environment."
        }
        mock_get_provider.return_value = mock_provider

        res = _run_single_extraction_worker(
            paper=self.paper,
            definition=self.def_trl,
            workspace=self.workspace
        )

        self.assertEqual(res["validation_status"], "pass")
        ext = Extraction.objects.get(paper=self.paper, extraction_definition=self.def_trl)
        self.assertEqual(ext.validation_status, "pass")
        self.assertFalse(ext.review_required)
        self.assertEqual(ext.exit_metric, "6.0")

    def test_signal_scoring_safe_defaults_when_extractions_fail_or_missing(self):
        """
        Validates that compute_paper_signal_score handles missing or failed extractions gracefully:
        - Missing/failed variables default safely to 0.0 (no KeyError).
        - Formula calculates with available variables.
        - Result is saved to PaperMetric without crashing the pipeline.
        """
        # 1. Provide a successful extraction ONLY for fit_score=8.0
        Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=self.def_fit,
            fields_data={"fit_score": 8.0},
            validation_status="pass"
        )
        # 2. Provide a FAILED extraction for trl_level (contains invalid data)
        Extraction.objects.create(
            paper=self.paper,
            workspace=self.workspace,
            extraction_definition=self.def_trl,
            fields_data={"garbage_key": 999},
            validation_status="fail"
        )
        # 3. novelty_score is completely omitted (never extracted)

        # Context vars must cleanly default missing/invalid variables to 0.0
        context_vars = extract_paper_parameters(self.paper, pipeline_run=self.pipeline_run)
        self.assertEqual(context_vars["fit_score"], 8.0)
        self.assertEqual(context_vars["trl_level"], 0.0)
        self.assertEqual(context_vars["novelty_score"], 0.0)

        # Execute scoring formula:
        # score = 0.5 * 8.0 + 0.3 * 0.0 + 0.2 * 0.0 = 4.0 -> return round(4.0 * 10.0, 2) = 40.0
        score, details = compute_paper_signal_score(self.paper, pipeline_run=self.pipeline_run)
        self.assertEqual(score, 40.0)
        self.assertIsNone(details["error"])

        self.pm.refresh_from_db()
        self.assertEqual(self.pm.signal_score, 40.0)

    def test_dynamic_scoring_formula_with_variable_count_and_syntax_resilience(self):
        """
        Validates dynamic formula execution when the workspace formula references
        an undeclared variable, encounters division by zero, or uses forbidden syntax:
        - Undeclared variables are safely initialized to 0.0 by the AST sandbox (score=0.0, no KeyError).
        - Forbidden syntax (like imports) or division by zero are safely caught by sandbox error handler.
        """
        # 1. Formula referencing undeclared variable -> AST sandbox auto-initializes to 0.0 default
        undeclared_formula = "return unknown_variable_xyz * 2.0"
        score, details = compute_paper_signal_score(
            self.paper,
            custom_code=undeclared_formula,
            pipeline_run=self.pipeline_run
        )
        self.assertEqual(score, 0.0)
        self.assertIsNone(details["error"])

        # 2. Formula with forbidden import statement -> caught by SandboxSecurityError
        forbidden_formula = "import os\nreturn 5.0"
        score_forbid, details_forbid = compute_paper_signal_score(
            self.paper,
            custom_code=forbidden_formula,
            pipeline_run=self.pipeline_run
        )
        self.assertEqual(score_forbid, 0.0)
        self.assertIn("Imports are strictly forbidden", str(details_forbid["error"]))

        # 3. Formula with division by zero -> sandbox safely intercepts ZeroDivisionError and defaults to 0.0
        div_zero_formula = "return 100.0 / fit_score"  # fit_score is 0.0
        Extraction.objects.filter(paper=self.paper).delete()
        score_div, details_div = compute_paper_signal_score(
            self.paper,
            custom_code=div_zero_formula,
            pipeline_run=self.pipeline_run
        )
        self.assertEqual(score_div, 0.0)
