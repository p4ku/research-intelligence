import uuid
import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    Paper,
    ExtractionDefinition,
    Extraction,
    PaperMetric,
    ComponentRun,
)
from research_intelligence.utils.sandbox import (
    execute_sandboxed_postprocessing,
    SandboxSecurityError,
    SandboxExecutionError,
)
from research_intelligence.tasks.step_5_extraction.extract import (
    _run_single_extraction_impl,
    execute_extraction_job,
)
from research_intelligence.tasks.step_6_signal_score.scorer import (
    compute_paper_signal_score,
    extract_paper_parameters,
    execute_signal_score_job,
)

User = get_user_model()


class SandboxedPostprocessingUnitTests(TestCase):
    """
    Tests validating sandboxed execution of ExtractionDefinition postprocessing snippets.
    """

    def test_expression_without_return(self):
        code = "fit_score * 1.5"
        res = execute_sandboxed_postprocessing(code, {"fit_score": 10})
        self.assertEqual(res, 15.0)

    def test_statement_with_explicit_return(self):
        code = """
if fit_score >= 8:
    return 100.0
else:
    return 20.0
"""
        res_high = execute_sandboxed_postprocessing(code, {"fit_score": 9})
        self.assertEqual(res_high, 100.0)

        res_low = execute_sandboxed_postprocessing(code, {"fit_score": 5})
        self.assertEqual(res_low, 20.0)

    def test_variable_assignment(self):
        code = "val = (fit_score + novelty_score) / 2"
        res = execute_sandboxed_postprocessing(code, {"fit_score": 10, "novelty_score": 6})
        self.assertEqual(res, 8.0)

    def test_dict_return(self):
        code = """
return {
    "normalized_score": fit_score / 10.0,
    "is_high_value": fit_score > 7
}
"""
        res = execute_sandboxed_postprocessing(code, {"fit_score": 8})
        self.assertIsInstance(res, dict)
        self.assertEqual(res["normalized_score"], 0.8)
        self.assertTrue(res["is_high_value"])

    def test_access_full_json_via_data_and_fields_data(self):
        # Complex LLM output JSON payload
        llm_json = {
            "fit_score": 8.5,
            "trl_level": 4,
            "metrics": {
                "accuracy": 0.94,
                "latency_ms": 12.5
            },
            "benchmarks": ["glue", "squad"]
        }

        # 1. Access nested elements via `data`
        code1 = "return data['metrics']['accuracy'] * 100"
        self.assertEqual(execute_sandboxed_postprocessing(code1, llm_json), 94.0)

        # 2. Access nested elements via `fields_data`
        code2 = "return fields_data['metrics']['latency_ms']"
        self.assertEqual(execute_sandboxed_postprocessing(code2, llm_json), 12.5)

        # 3. Access top-level dictionary directly as variable
        code3 = "return metrics['accuracy'] + trl_level"
        self.assertAlmostEqual(execute_sandboxed_postprocessing(code3, llm_json), 4.94)

        # 4. Access list length and elements
        code4 = "return len(benchmarks) * 10"
        self.assertEqual(execute_sandboxed_postprocessing(code4, llm_json), 20)

    def test_security_blocks_import(self):
        code = "import os\nreturn os.system('ls')"
        with self.assertRaises(SandboxSecurityError):
            execute_sandboxed_postprocessing(code, {"fit_score": 5})

    def test_security_blocks_dunder(self):
        code = "return ().__class__.__bases__[0].__subclasses__()"
        with self.assertRaises(SandboxSecurityError):
            execute_sandboxed_postprocessing(code, {"fit_score": 5})

    def test_security_blocks_open(self):
        code = "f = open('/etc/passwd')\nreturn f.read()"
        with self.assertRaises((SandboxSecurityError, SandboxExecutionError)):
            execute_sandboxed_postprocessing(code, {"fit_score": 5})

    def test_infinite_loop_prevention(self):
        code = "while True:\n    pass\nreturn 1"
        with self.assertRaises(SandboxExecutionError) as ctx:
            execute_sandboxed_postprocessing(code, {"fit_score": 5})
        self.assertIn("loop limit", str(ctx.exception).lower())


class ExtractionPostprocessingTaskIntegrationTests(TestCase):
    """
    Tests validating Step 5 extraction execution with postprocessing_code.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Postprocessing Workspace",
            screening_llm_model="google/gemini-3.8-flash"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="extraction"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Advanced Machine Learning Methods",
            abstract="We present an end-to-end framework."
        )
        PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="full_text_passed"
        )

    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    def test_extraction_runs_postprocessing_code_successfully(self, mock_get_llm):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            {
                "fit_score": 8,
                "novelty_score": 6,
                "rationale": "High quality paper"
            },
            {"prompt_tokens": 100, "candidates_tokens": 50}
        )
        mock_get_llm.return_value = mock_provider

        definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Fit & Novelty",
            exit_metrics="fit_score",
            system_prompt="Extract metrics",
            user_prompt_template="Title: {{paper_title}}",
            response_schema={"type": "object"},
            postprocessing_code="return (fit_score * 2) + novelty_score"
        )

        res = _run_single_extraction_impl(self.paper, definition, self.workspace)
        self.assertTrue(res["success"])

        extraction = Extraction.objects.get(paper=self.paper, extraction_definition=definition)
        fields = extraction.fields_data

        # Original fields intact
        self.assertEqual(fields["fit_score"], 8)
        self.assertEqual(fields["novelty_score"], 6)

        # Unique postprocessed field populated
        # definition name "Fit & Novelty" -> slug "fit_novelty"
        expected_key = "fit_novelty_postprocessed"
        self.assertIn(expected_key, fields)
        self.assertEqual(fields[expected_key], 22.0)  # (8 * 2) + 6 = 22.0

        expected_computed_key = "fit_novelty_computed"
        self.assertIn(expected_computed_key, fields)
        self.assertEqual(fields[expected_computed_key], 22.0)

        # Also exit metric slug is populated
        self.assertEqual(fields["fit_score_postprocessed"], 22.0)

    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    def test_extraction_handles_postprocessing_error_gracefully(self, mock_get_llm):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            {
                "fit_score": 0,
                "rationale": "Edge case"
            },
            {"prompt_tokens": 80, "candidates_tokens": 20}
        )
        mock_get_llm.return_value = mock_provider

        # Code that raises division by zero
        definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Error Def",
            exit_metrics="fit_score",
            response_schema={},
            postprocessing_code="return 100 / fit_score"
        )

        res = _run_single_extraction_impl(self.paper, definition, self.workspace)
        self.assertTrue(res["success"])

        extraction = Extraction.objects.get(paper=self.paper, extraction_definition=definition)
        fields = extraction.fields_data

        # Original fields still saved
        self.assertEqual(fields["fit_score"], 0)
        # Error logged in version_info without crashing extraction
        self.assertIn("postprocessing_error", extraction.version_info)
        self.assertIn("division by zero", extraction.version_info["postprocessing_error"].lower())
        self.assertEqual(fields.get("error_def_postprocessed"), 0.0)

    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    def test_extraction_dict_postprocessing_unpacks_fields(self, mock_get_llm):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            {
                "base_val": 10
            },
            {"prompt_tokens": 80, "candidates_tokens": 20}
        )
        mock_get_llm.return_value = mock_provider

        definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Multi Output",
            response_schema={},
            postprocessing_code="""
return {
    "scaled_val": base_val * 3,
    "is_valid": True
}
"""
        )

        res = _run_single_extraction_impl(self.paper, definition, self.workspace)
        self.assertTrue(res["success"])

        extraction = Extraction.objects.get(paper=self.paper, extraction_definition=definition)
        fields = extraction.fields_data
        self.assertEqual(fields["scaled_val"], 30)
        self.assertTrue(fields["is_valid"])


class PostprocessedSignalScorePipelineIntegrationTests(TestCase):
    """
    Tests verifying that postprocessed parameters from ExtractionDefinitions
    are seamlessly forwarded into Step 6 Signal Score calculation.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="End to End Pipeline Workspace",
            screening_llm_model="google/gemini-3.8-flash",
            # Signal score uses the postprocessed parameter directly!
            signal_score_code="return fit_assessment_postprocessed + 10.0"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="signal_score"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Quantum Annealing Breakthrough",
            abstract="Quantum annealing advances."
        )
        PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="full_text_passed"
        )

    def test_postprocessed_field_injected_into_signal_score_context(self):
        definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Fit Assessment",
            exit_metrics="fit_score",
            response_schema={},
            postprocessing_code="return fit_score * 2.5"
        )

        # Extraction with computed postprocessed metric
        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=definition,
            fields_data={
                "fit_score": 8,
                "fit_assessment_postprocessed": 20.0,
                "fit_assessment_computed": 20.0,
            }
        )

        # 1. Test parameter extraction
        params = extract_paper_parameters(self.paper)
        self.assertIn("fit_assessment_postprocessed", params)
        self.assertEqual(params["fit_assessment_postprocessed"], 20.0)

        # 2. Test compute_paper_signal_score
        score, details = compute_paper_signal_score(self.paper)

        # Formula: fit_assessment_postprocessed (20.0) + 10.0 = 30.0
        self.assertEqual(score, 30.0)
        self.assertIn("fit_assessment_postprocessed", details["variables"])
        self.assertEqual(details["variables"]["fit_assessment_postprocessed"], 20.0)

    def test_django_admin_extraction_definition_shows_bold_variable_preview(self):
        definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Schwarz Strategic Fit",
            exit_metrics="fit_score",
            system_prompt="Test prompt",
            user_prompt_template="Test template",
            response_schema={"type": "object"},
            postprocessing_code="return fit_score * 2.5"
        )
        admin_user = User.objects.create_superuser(
            username="testadmin",
            email="admin@test.com",
            password="password123"
        )
        self.client.force_login(admin_user)
        url = f"/admin/research_intelligence/extractiondefinition/{definition.id}/change/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        # Verify bold variable name is rendered in both the readonly field and the help text
        self.assertIn("schwarz_strategic_fit_postprocessed", content)
        self.assertIn("fit_score_postprocessed", content)
        self.assertIn("<b><code>schwarz_strategic_fit_postprocessed</code></b>", content)

    def test_duplicate_exit_metric_consistency_check_and_red_badge(self):
        from django.core.exceptions import ValidationError

        # 1. First definition with exit_metrics = "novelty_score"
        def1 = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Definition 1",
            exit_metrics="novelty_score",
            system_prompt="Extract novelty",
            user_prompt_template="Prompt",
            response_schema={}
        )

        # 2. Second definition in same workspace with duplicate exit_metrics = "novelty_score"
        def2 = ExtractionDefinition(
            workspace=self.workspace,
            name="Novelty Definition 2",
            exit_metrics="novelty_score",
            system_prompt="Extract novelty duplicate",
            user_prompt_template="Prompt",
            response_schema={}
        )

        # Calling clean() on duplicate definition in same workspace MUST raise ValidationError
        with self.assertRaises(ValidationError) as ctx:
            def2.clean()
        self.assertIn("exit_metrics", ctx.exception.message_dict)
        self.assertIn("Consistency Error", str(ctx.exception.message_dict["exit_metrics"]))

        # 3. Save def2 directly to test admin changelist red highlight
        def2.save()

        admin_user = User.objects.create_superuser(
            username="admin_consistency",
            email="admin_cons@test.com",
            password="password123"
        )
        self.client.force_login(admin_user)

        # Visit changelist: /admin/research_intelligence/extractiondefinition/
        list_url = "/admin/research_intelligence/extractiondefinition/"
        res_list = self.client.get(list_url)
        self.assertEqual(res_list.status_code, 200)
        list_content = res_list.content.decode("utf-8")

        # The duplicate exit metric MUST render in red with error text and mention conflicting definition
        self.assertIn("🚨 novelty_score (Duplicate: Novelty Definition 1)", list_content)

        # 4. Visit change form for def2: /admin/research_intelligence/extractiondefinition/{def2.id}/change/
        change_url = f"/admin/research_intelligence/extractiondefinition/{def2.id}/change/"
        res_change = self.client.get(change_url)
        self.assertEqual(res_change.status_code, 200)
        change_content = res_change.content.decode("utf-8")
        self.assertIn("🚨 CONSISTENCY ERROR: One or more exit metrics from this list are already defined", change_content)

        # 5. Third definition in DIFFERENT workspace with same exit_metric is ALLOWED (no cross-workspace collision)
        other_workspace = Workspace.objects.create(name="Other Workspace")
        def3 = ExtractionDefinition(
            workspace=other_workspace,
            name="Other Workspace Novelty",
            exit_metrics="novelty_score",
            system_prompt="Prompt",
            user_prompt_template="Prompt",
            response_schema={}
        )
        # Should not raise any ValidationError
        def3.clean()

    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    def test_comma_separated_exit_metrics_and_first_item_for_postprocessing(self, mock_get_llm):
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            {
                "rigour_score": 7.0,
                "param1": 15.0,
                "param2": 25.0,
                "confidence": 0.95
            },
            {"prompt_tokens": 100, "candidates_tokens": 50}
        )
        mock_get_llm.return_value = mock_provider

        # 1. Create definition with comma-separated exit_metrics and spaces: "rigour_score,  param1 , param2 "
        definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Methodology Evaluation",
            exit_metrics="rigour_score,  param1 , param2 ",
            system_prompt="Extract methodology scores",
            user_prompt_template="Prompt: {{paper_title}}",
            response_schema={},
            postprocessing_code="return rigour_score * 2.0"
        )

        # Verify parsed list stripped all spaces and sanitized
        self.assertEqual(definition.get_exit_metrics_list(), ["rigour_score", "param1", "param2"])
        # Verify 1st variable from list is the primary metric
        self.assertEqual(definition.get_primary_exit_metric(), "rigour_score")

        # 2. Run Step 5 extraction
        res = _run_single_extraction_impl(self.paper, definition, self.workspace)
        self.assertTrue(res["success"])

        extraction = Extraction.objects.get(paper=self.paper, extraction_definition=definition)
        fields = extraction.fields_data

        # Verify raw extracted fields
        self.assertEqual(fields["rigour_score"], 7.0)
        self.assertEqual(fields["param1"], 15.0)
        self.assertEqual(fields["param2"], 25.0)

        # Verify 1st variable from the list was used for _postprocessed
        self.assertEqual(fields["rigour_score_postprocessed"], 14.0)  # 7.0 * 2.0 = 14.0
        self.assertEqual(fields["methodology_evaluation_postprocessed"], 14.0)

        # 3. Test Signal Score extraction: all 3 metrics + 1st metric postprocessed MUST be in context!
        params = extract_paper_parameters(self.paper)
        self.assertEqual(params["rigour_score"], 7.0)
        self.assertEqual(params["param1"], 15.0)
        self.assertEqual(params["param2"], 25.0)
        self.assertEqual(params["rigour_score_postprocessed"], 14.0)

        # 4. Test signal score calculation using multiple parameters from the list
        self.workspace.signal_score_code = "return rigour_score_postprocessed + param1 + param2"
        self.workspace.save()

        score, details = compute_paper_signal_score(self.paper)
        # Expected: 14.0 (rigour postprocessed) + 15.0 (param1) + 25.0 (param2) = 54.0
        self.assertEqual(score, 54.0)


class SignalScoreVariableVisibilityScenariosTests(TestCase):
    """
    Dedicated test suite covering all 4 exit parameter configurations and validating
    variable visibility in Signal Score (extract_paper_parameters, get_signal_score_prompt_snapshot,
    and compute_paper_signal_score):
      1) No exit parameters (exit_metrics=None / empty)
      2) Single exit parameter (exit_metrics=["rigour_score"])
      3) Multiple exit parameters (exit_metrics=["rigour_score", "param1", "param2"])
      4) Single or multiple exit parameters WITH postprocessing code
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(name=f"Visibility Test WS {uuid.uuid4().hex[:6]}")
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="extraction"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Scalable Multi-Agent Intelligence Systems",
            abstract="Abstract covering research rigour and benchmark results."
        )
        PaperMetric.objects.create(
            paper=self.paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="full_text_passed"
        )

    # 1) Scenario 1: No exit parameters (exit_metric is empty / None)
    def test_scenario_1_no_exit_parameters_visible_in_signal_score(self):
        definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Evaluation",
            exit_metrics="",  # No exit parameter configured
            system_prompt="Extract novelty",
            user_prompt_template="Title: {{paper_title}}",
            response_schema={}
        )

        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=definition,
            category="evaluation",
            fields_data={
                "value": 8.5,
                "novelty_score": 8.5,
                "rationale": "Strong novelty"
            },
            validation_status="pass"
        )

        # Check prompt snapshot visibility
        snapshot = self.workspace.get_signal_score_prompt_snapshot()
        scoring_vars = [v["variable_name"] for v in snapshot["scoring_variables"]]
        self.assertIn("novelty_evaluation", scoring_vars)

        # Check extracted parameters in context
        params = extract_paper_parameters(self.paper)
        self.assertIn("novelty_evaluation", params)
        self.assertEqual(params["novelty_evaluation"], 8.5)
        self.assertIn("novelty_score", params)
        self.assertEqual(params["novelty_score"], 8.5)

        # Execute formula in Signal score code
        self.workspace.signal_score_code = "return novelty_evaluation * 2.0 + novelty_score"
        self.workspace.save()

        score, details = compute_paper_signal_score(self.paper)
        self.assertEqual(score, 25.5)  # (8.5 * 2.0) + 8.5 = 25.5
        self.assertEqual(details["variables"]["novelty_evaluation"], 8.5)
        self.assertEqual(details["variables"]["novelty_score"], 8.5)

    # 2) Scenario 2: Single exit parameter
    def test_scenario_2_single_exit_parameter_visible_in_signal_score(self):
        definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Methodology Rigour",
            exit_metrics="rigour_score",  # Single exit parameter
            system_prompt="Extract rigour",
            user_prompt_template="Title: {{paper_title}}",
            response_schema={}
        )

        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=definition,
            category="methodology",
            fields_data={
                "rigour_score": 7.5,
                "benchmark_rank": 1.0
            },
            validation_status="pass"
        )

        # Check prompt snapshot visibility
        snapshot = self.workspace.get_signal_score_prompt_snapshot()
        scoring_vars = [v["variable_name"] for v in snapshot["scoring_variables"]]
        self.assertIn("rigour_score", scoring_vars)

        # Check extracted parameters in context
        params = extract_paper_parameters(self.paper)
        self.assertIn("rigour_score", params)
        self.assertEqual(params["rigour_score"], 7.5)
        self.assertIn("methodology_rigour", params)
        self.assertEqual(params["methodology_rigour"], 7.5)

        # Execute formula in Signal score code
        self.workspace.signal_score_code = "return rigour_score * 10.0"
        self.workspace.save()

        score, details = compute_paper_signal_score(self.paper)
        self.assertEqual(score, 75.0)
        self.assertEqual(details["variables"]["rigour_score"], 7.5)

    # 3) Scenario 3: Multiple exit parameters (comma-separated with whitespace)
    def test_scenario_3_multiple_exit_parameters_visible_in_signal_score(self):
        definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Dataset & Experiment Stats",
            exit_metrics="rigour_score,  sample_size ,   p_value ",  # Multiple with messy spaces
            system_prompt="Extract stats",
            user_prompt_template="Title: {{paper_title}}",
            response_schema={}
        )

        # Verify parsed list stripped spaces
        self.assertEqual(definition.get_exit_metrics_list(), ["rigour_score", "sample_size", "p_value"])

        Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=definition,
            category="stats",
            fields_data={
                "rigour_score": 8.0,
                "sample_size": 250.0,
                "p_value": 0.005
            },
            validation_status="pass"
        )

        # Check prompt snapshot visibility - all metrics present
        snapshot = self.workspace.get_signal_score_prompt_snapshot()
        scoring_vars = [v["variable_name"] for v in snapshot["scoring_variables"]]
        self.assertIn("rigour_score", scoring_vars)
        self.assertIn("sample_size", scoring_vars)
        self.assertIn("p_value", scoring_vars)

        # Check extracted parameters in context
        params = extract_paper_parameters(self.paper)
        self.assertIn("rigour_score", params)
        self.assertEqual(params["rigour_score"], 8.0)
        self.assertIn("sample_size", params)
        self.assertEqual(params["sample_size"], 250.0)
        self.assertIn("p_value", params)
        self.assertEqual(params["p_value"], 0.005)

        # Execute formula in Signal score code referencing all variables
        self.workspace.signal_score_code = (
            "return (rigour_score * 10.0) + (sample_size / 2.0) + (100.0 if p_value < 0.01 else 0.0)"
        )
        self.workspace.save()

        score, details = compute_paper_signal_score(self.paper)
        # Expected: (8.0 * 10) + (250 / 2) + 100 = 80 + 125 + 100 = 305.0
        self.assertEqual(score, 305.0)
        self.assertEqual(details["variables"]["rigour_score"], 8.0)
        self.assertEqual(details["variables"]["sample_size"], 250.0)
        self.assertEqual(details["variables"]["p_value"], 0.005)

    # 4) Scenario 4: Single or multiple exit parameters with postprocessing snippet
    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    def test_scenario_4_single_and_multiple_exit_parameters_with_postprocessing(self, mock_get_llm):
        # 4A: Single exit metric with postprocessing code
        def_single = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Commercial Viability",
            exit_metrics="market_fit",
            system_prompt="Extract market fit",
            user_prompt_template="Title: {{paper_title}}",
            response_schema={},
            postprocessing_code="return market_fit * 1.5"
        )

        # 4B: Multiple exit metrics with postprocessing code
        def_multiple = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Clinical Rigour",
            exit_metrics="cohort_size, control_ratio, confidence_index",
            system_prompt="Extract clinical data",
            user_prompt_template="Title: {{paper_title}}",
            response_schema={},
            postprocessing_code="return (cohort_size * control_ratio) + confidence_index"
        )

        # Step 5 extraction execution for 4A
        mock_provider_a = MagicMock()
        mock_provider_a.generate.return_value = ({"market_fit": 6.0}, {"prompt_tokens": 50, "candidates_tokens": 20})
        mock_get_llm.return_value = mock_provider_a
        res_a = _run_single_extraction_impl(self.paper, def_single, self.workspace)
        self.assertTrue(res_a["success"])

        # Step 5 extraction execution for 4B
        mock_provider_b = MagicMock()
        mock_provider_b.generate.return_value = (
            {"cohort_size": 100.0, "control_ratio": 0.5, "confidence_index": 10.0},
            {"prompt_tokens": 50, "candidates_tokens": 20}
        )
        mock_get_llm.return_value = mock_provider_b
        res_b = _run_single_extraction_impl(self.paper, def_multiple, self.workspace)
        self.assertTrue(res_b["success"])

        # Verify prompt snapshot contains both raw and postprocessed variables
        snapshot = self.workspace.get_signal_score_prompt_snapshot()
        scoring_vars = [v["variable_name"] for v in snapshot["scoring_variables"]]
        # 4A variables
        self.assertIn("market_fit", scoring_vars)
        self.assertIn("market_fit_postprocessed", scoring_vars)
        # 4B variables (raw list + 1st metric postprocessed)
        self.assertIn("cohort_size", scoring_vars)
        self.assertIn("control_ratio", scoring_vars)
        self.assertIn("confidence_index", scoring_vars)
        self.assertIn("cohort_size_postprocessed", scoring_vars)

        # Verify extract_paper_parameters contains all values accurately
        params = extract_paper_parameters(self.paper)
        # 4A values
        self.assertEqual(params["market_fit"], 6.0)
        self.assertEqual(params["market_fit_postprocessed"], 9.0)  # 6.0 * 1.5 = 9.0
        self.assertEqual(params["commercial_viability_postprocessed"], 9.0)

        # 4B values
        self.assertEqual(params["cohort_size"], 100.0)
        self.assertEqual(params["control_ratio"], 0.5)
        self.assertEqual(params["confidence_index"], 10.0)
        # Postprocessed from 1st metric in list: (100 * 0.5) + 10 = 60.0
        self.assertEqual(params["cohort_size_postprocessed"], 60.0)
        self.assertEqual(params["clinical_rigour_postprocessed"], 60.0)

        # Verify compute_paper_signal_score executes formula with all postprocessed and raw variables
        self.workspace.signal_score_code = (
            "return market_fit_postprocessed + cohort_size_postprocessed + market_fit + control_ratio * 20.0"
        )
        self.workspace.save()

        score, details = compute_paper_signal_score(self.paper)
        # Expected: 9.0 (market_fit_postprocessed) + 60.0 (cohort_size_postprocessed) + 6.0 (market_fit) + 10.0 (0.5 * 20) = 85.0
        self.assertEqual(score, 85.0)
        self.assertEqual(details["variables"]["market_fit_postprocessed"], 9.0)
        self.assertEqual(details["variables"]["cohort_size_postprocessed"], 60.0)
        self.assertEqual(details["variables"]["market_fit"], 6.0)
        self.assertEqual(details["variables"]["control_ratio"], 0.5)


class FullPipelineE2EVariableMathTests(TestCase):
    """
    End-to-End Pipeline integration test executing Celery tasks Step 5 (execute_extraction_job)
    and Step 6 (execute_signal_score_job) sequentially on a live Workspace, verifying
    all 4 scenarios and checking the exact signal score math on PaperMetric.
    """

    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    def test_full_pipeline_step5_and_step6_e2e_all_scenarios_and_math(self, mock_get_llm):
        workspace = Workspace.objects.create(
            name=f"E2E Full Pipeline Math {uuid.uuid4().hex[:6]}",
            signal_score_code=(
                "# Math formula combining all 4 scenarios:\n"
                "score = (novelty * 1.0) + (rigour_score * 2.0) + (sample_size / 10.0) + (control_groups * 5.0) + (market_fit_postprocessed * 1.0) + (growth_potential * 0.5)\n"
                "return round(score, 2)"
            )
        )
        pipeline_run = PipelineRun.objects.create(
            workspace=workspace,
            status="running"
        )
        paper = Paper.objects.create(
            workspace=workspace,
            pipeline_run=pipeline_run,
            hash_id=uuid.uuid4().hex,
            title="Self-Supervised Representation Learning at Scale",
            abstract="Empirical study across diverse multimodal foundation benchmarks."
        )
        # Accepted in screening
        pm = PaperMetric.objects.create(
            paper=paper,
            pipeline_run=pipeline_run,
            workspace=workspace,
            screening_status="full_text_passed"
        )

        # 1) Scenario 1: No exit parameters
        def_none = ExtractionDefinition.objects.create(
            workspace=workspace,
            name="Novelty",
            exit_metrics="",
            system_prompt="Prompt for novelty",
            user_prompt_template="Prompt: {{paper_title}}",
            response_schema={},
            is_active=True
        )

        # 2) Scenario 2: Single exit parameter
        def_single = ExtractionDefinition.objects.create(
            workspace=workspace,
            name="Methodology Rigour",
            exit_metrics="rigour_score",
            system_prompt="Prompt for rigour",
            user_prompt_template="Prompt: {{paper_title}}",
            response_schema={},
            is_active=True
        )

        # 3) Scenario 3: Multiple exit parameters with whitespace
        def_multi = ExtractionDefinition.objects.create(
            workspace=workspace,
            name="Dataset Metrics",
            exit_metrics="sample_size,   control_groups ,  p_value ",
            system_prompt="Prompt for dataset metrics",
            user_prompt_template="Prompt: {{paper_title}}",
            response_schema={},
            is_active=True
        )

        # 4) Scenario 4: Exit parameters with postprocessing snippet
        def_post = ExtractionDefinition.objects.create(
            workspace=workspace,
            name="Market Viability",
            exit_metrics="market_fit, growth_potential",
            postprocessing_code="return (market_fit * 1.5) + growth_potential",
            system_prompt="Prompt for market viability",
            user_prompt_template="Prompt: {{paper_title}}",
            response_schema={},
            is_active=True
        )

        # Mock LLM provider responses per definition
        def side_effect_generate(*args, **kwargs):
            sys_str = str(kwargs.get("system_instruction") or "")
            prompt_str = str(kwargs.get("prompt") or "")
            if args:
                sys_str += " " + " ".join(str(a) for a in args)
            combined = (sys_str + " " + prompt_str).lower()
            if "novelty" in combined:
                return ({"novelty": 7.0, "value": 7.0}, {"prompt_tokens": 10, "candidates_tokens": 5})
            if "rigour" in combined:
                return ({"rigour_score": 8.0}, {"prompt_tokens": 10, "candidates_tokens": 5})
            if "dataset" in combined:
                return ({"sample_size": 200.0, "control_groups": 4.0, "p_value": 0.001}, {"prompt_tokens": 10, "candidates_tokens": 5})
            # Market Viability
            return ({"market_fit": 6.0, "growth_potential": 10.0}, {"prompt_tokens": 10, "candidates_tokens": 5})

        mock_provider = MagicMock()
        mock_provider.generate.side_effect = side_effect_generate
        mock_get_llm.return_value = mock_provider

        # Execute Step 5 (Extraction Component Job)
        comp_extract = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type="extraction",
            component_name="parameter_extraction",
            status="pending"
        )
        extract_success = execute_extraction_job(str(comp_extract.id))
        self.assertTrue(extract_success)

        comp_extract.refresh_from_db()
        self.assertEqual(comp_extract.status, "completed")

        # Verify all 4 extractions exist
        extractions = Extraction.objects.filter(paper=paper)
        self.assertEqual(extractions.count(), 4)

        # Execute Step 6 (Signal Score Component Job)
        comp_score = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type="signal_score",
            component_name="signal_score",
            status="pending"
        )
        score_success = execute_signal_score_job(str(comp_score.id))
        self.assertTrue(score_success)

        comp_score.refresh_from_db()
        self.assertEqual(comp_score.status, "completed")

        # Verify Paper and PaperMetric have signal_score calculated and match exact math
        pm.refresh_from_db()
        self.assertIsNotNone(pm.signal_score)

        # Expected Math:
        # novelty = 7.0 * 1.0 = 7.0
        # rigour_score = 8.0 * 2.0 = 16.0
        # sample_size = 200.0 / 10.0 = 20.0
        # control_groups = 4.0 * 5.0 = 20.0
        # market_fit_postprocessed = (6.0 * 1.5) + 10.0 = 19.0 * 1.0 = 19.0
        # growth_potential = 10.0 * 0.5 = 5.0
        # Total = 7.0 + 16.0 + 20.0 + 20.0 + 19.0 + 5.0 = 87.0
        expected_math = 87.0
        self.assertEqual(pm.signal_score, expected_math)

        # Verify audit details
        details = pm.signal_score_details
        self.assertIsNotNone(details)
        vars_dict = details.get("variables", {})
        self.assertEqual(vars_dict.get("novelty"), 7.0)
        self.assertEqual(vars_dict.get("rigour_score"), 8.0)
        self.assertEqual(vars_dict.get("sample_size"), 200.0)
        self.assertEqual(vars_dict.get("control_groups"), 4.0)
        self.assertEqual(vars_dict.get("market_fit"), 6.0)
        self.assertEqual(vars_dict.get("growth_potential"), 10.0)
        self.assertEqual(vars_dict.get("market_fit_postprocessed"), 19.0)


class ExtractionDefinitionAPITests(TestCase):
    """
    Tests validating REST API endpoints for ExtractionDefinition:
    - Support for list of exit parameters (`exit_metrics: list[str]`)
    - Support for Python postprocessing code snippets (`postprocessing_code: str`)
    - Syntax validation and error reporting on invalid Python code
    - Unpacking in nested Workspace creation
    """

    def setUp(self):
        from rest_framework.test import APIClient
        from research_intelligence.models import WorkspaceMember
        self.client = APIClient()
        self.user = User.objects.create_user(username=f"api_test_{uuid.uuid4().hex[:8]}", password="password123")
        self.workspace = Workspace.objects.create(name=f"API Test Workspace {uuid.uuid4().hex[:8]}")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")
        self.client.force_authenticate(user=self.user)

    def test_api_create_and_update_extraction_definition_with_exit_metrics_and_postprocessing(self):
        url = "/api/extraction-definitions/"
        payload = {
            "workspace": str(self.workspace.id),
            "name": "Market Evaluation",
            "system_prompt": "Extract market and risk metrics.",
            "user_prompt_template": "Paper text: {paper_text}",
            "response_schema": {
                "type": "object",
                "properties": {
                    "market_fit": {"type": "number"},
                    "risk_factor": {"type": "number"}
                }
            },
            "exit_metrics": ["market_fit", "risk_factor"],
            "postprocessing_code": "return market_fit * 2.0 - risk_factor"
        }

        # 1. Create via POST
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, 201)
        data = res.json()
        defn_id = data["id"]
        self.assertNotIn("exit_metric", data)
        self.assertEqual(data["exit_metrics"], ["market_fit", "risk_factor"])
        self.assertEqual(data["postprocessing_code"], "return market_fit * 2.0 - risk_factor")
        self.assertTrue(data["has_postprocessing_code"])

        # 2. Retrieve via GET
        detail_url = f"/api/extraction-definitions/{defn_id}/"
        get_res = self.client.get(detail_url)
        self.assertEqual(get_res.status_code, 200)
        get_data = get_res.json()
        self.assertNotIn("exit_metric", get_data)
        self.assertEqual(get_data["exit_metrics"], ["market_fit", "risk_factor"])
        self.assertEqual(get_data["postprocessing_code"], "return market_fit * 2.0 - risk_factor")
        self.assertTrue(get_data["has_postprocessing_code"])

        # 3. Update via PATCH with new exit metrics list and postprocessing code
        patch_payload = {
            "exit_metrics": ["market_fit", "growth_score"],
            "postprocessing_code": "return market_fit + growth_score"
        }
        patch_res = self.client.patch(detail_url, patch_payload, format="json")
        self.assertEqual(patch_res.status_code, 200)
        patch_data = patch_res.json()
        self.assertNotIn("exit_metric", patch_data)
        self.assertEqual(patch_data["exit_metrics"], ["market_fit", "growth_score"])
        self.assertEqual(patch_data["postprocessing_code"], "return market_fit + growth_score")

        # 4. Test syntax error validation in postprocessing_code
        bad_payload = {
            "postprocessing_code": "def broken(:"
        }
        bad_res = self.client.patch(detail_url, bad_payload, format="json")
        self.assertEqual(bad_res.status_code, 400)
        self.assertIn("postprocessing_code", bad_res.json())
        self.assertIn("Invalid Python syntax", bad_res.json()["postprocessing_code"][0])

    def test_api_create_workspace_with_nested_extraction_definitions(self):
        from research_intelligence.models import ExtractionDefinition
        ws_url = "/api/workspaces/"
        payload = {
            "name": f"Nested Defs Workspace {uuid.uuid4().hex[:8]}",
            "abstract_acceptance_criteria": "Accept AI papers",
            "abstract_rejection_criteria": "Reject hardware",
            "full_text_acceptance_criteria": "Accept AI papers",
            "full_text_rejection_criteria": "Reject hardware",
            "extraction_definitions": [
                {
                    "name": "Nested Target",
                    "system_prompt": "Extract parameters",
                    "user_prompt_template": "{paper_text}",
                    "response_schema": {"type": "object"},
                    "exit_metrics": ["param_one", "param_two"],
                    "postprocessing_code": "return param_one + param_two"
                }
            ]
        }

        res = self.client.post(ws_url, payload, format="json")
        self.assertEqual(res.status_code, 201)
        ws_id = res.json()["id"]

        nested_def = ExtractionDefinition.objects.get(workspace_id=ws_id, name="Nested Target")
        self.assertEqual(nested_def.get_exit_metrics_list(), ["param_one", "param_two"])
        self.assertEqual(nested_def.postprocessing_code, "return param_one + param_two")


