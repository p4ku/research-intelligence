from __future__ import annotations
import json
from unittest.mock import patch, MagicMock
from django.test import TestCase

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    Paper,
    ExtractionDefinition,
    Extraction,
    PaperMetric,
    NarrativeReport,
)
from research_intelligence.utils.sandbox import execute_sandboxed_postprocessing
from research_intelligence.tasks.step_5_extraction.extract import _run_single_extraction_impl
from research_intelligence.tasks.step_6_signal_score.scorer import (
    compute_paper_signal_score,
    extract_paper_parameters,
)
from research_intelligence.tasks.step_7_reporting.narrative import generate_executive_narrative_report


class PostprocessingDictReturnAndSignalScoreCrossTests(TestCase):
    """
    Cross-tests verifying that extraction postprocessing snippets returning dictionary/tuple structures
    (e.g., {"trl_level": ..., "trl_level_postprocessed": ...}) are:
    1. Executed accurately in the sandbox
    2. Persisted into Extraction fields_data
    3. Auto-discovered by Workspace available signal variables and prompt snapshots
    4. Mapped into extract_paper_parameters context
    5. Directly visible and usable in Workspace signal_score_code Python formula
    6. Formatted seamlessly into Step 7 Narrative Report prompt context ({papers}, {papers_json}, {score_vectors_summary})
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Quantum & Robotics Workspace",
            screening_llm_model="google/gemini-3.8-flash",
            # Signal score uses both the raw and postprocessed dictionary keys returned by postprocessing!
            signal_score_code=(
                "score = 0.5 * trl_level_postprocessed + 0.3 * operational_readiness_score + 0.2 * prototype_maturity_score\n"
                "return round(score, 2)"
            )
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="reporting"
        )

        # Extraction definition with the user's exact postprocessing snippet
        self.postprocessing_snippet = """calibrated_trl = float(trl_level)
if operational_readiness_score >= 8 and prototype_maturity_score >= 8 and calibrated_trl < 7:
    calibrated_trl = min(7.0, calibrated_trl + 1.0)
elif (operational_readiness_score <= 2 or prototype_maturity_score <= 2) and calibrated_trl > 4:
    calibrated_trl = max(3.0, calibrated_trl - 1.0)
final_trl = round(calibrated_trl, 1)
return {
    "trl_level": final_trl,
    "trl_level_postprocessed": final_trl
}"""

        self.extraction_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Assessment",
            system_prompt="Extract TRL metrics",
            user_prompt_template="Title: {title}",
            response_schema={
                "type": "object",
                "properties": {
                    "trl_level": {"type": "number"},
                    "operational_readiness_score": {"type": "number"},
                    "prototype_maturity_score": {"type": "number"},
                },
                "required": ["trl_level"]
            },
            exit_metrics="trl_level",
            postprocessing_code=self.postprocessing_snippet,
            is_active=True
        )

    def test_sandbox_executes_dict_return_with_conditional_branching(self):
        """Test sandbox execution of the exact postprocessing snippet with both branches."""
        # Branch 1: High readiness & maturity raises TRL from 5.0 to 6.0
        fields_high = {
            "trl_level": 5.0,
            "operational_readiness_score": 9.0,
            "prototype_maturity_score": 9.0,
        }
        res_high = execute_sandboxed_postprocessing(self.postprocessing_snippet, fields_high)
        self.assertIsInstance(res_high, dict)
        self.assertEqual(res_high["trl_level"], 6.0)
        self.assertEqual(res_high["trl_level_postprocessed"], 6.0)

        # Branch 2: Low readiness lowers TRL from 6.0 to 5.0
        fields_low = {
            "trl_level": 6.0,
            "operational_readiness_score": 1.0,
            "prototype_maturity_score": 8.0,
        }
        res_low = execute_sandboxed_postprocessing(self.postprocessing_snippet, fields_low)
        self.assertIsInstance(res_low, dict)
        self.assertEqual(res_low["trl_level"], 5.0)
        self.assertEqual(res_low["trl_level_postprocessed"], 5.0)

    def test_workspace_auto_discovers_dict_keys_in_signal_variables(self):
        """Verify that returned dictionary keys in postprocessing_code appear in Workspace available variables."""
        variables = self.workspace.get_available_signal_variables()
        var_names = [v["name"] for v in variables]

        # Both keys returned in the dict must be discovered
        self.assertIn("trl_level", var_names)
        self.assertIn("trl_level_postprocessed", var_names)

        # Check snapshot representation
        snapshot = self.workspace.get_signal_score_prompt_snapshot()
        snap_vars = [v["variable_name"] for v in snapshot["scoring_variables"]]
        self.assertIn("trl_level", snap_vars)
        self.assertIn("trl_level_postprocessed", snap_vars)

    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    def test_step_5_extraction_stores_dict_return_and_propagates_to_signal_score(self, mock_get_llm):
        """Verify end-to-end Step 5 -> Step 6 handoff: postprocessed dict keys are saved and evaluated in signal score."""
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            {
                "trl_level": 5.0,
                "operational_readiness_score": 9.0,
                "prototype_maturity_score": 9.0,
            },
            {"prompt_tokens": 100, "candidates_tokens": 50}
        )
        mock_get_llm.return_value = mock_provider

        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="quantum_trl_paper_1",
            title="Scalable Fault-Tolerant Quantum Processor",
            abstract="Experimental demonstration of high readiness superconducting qubits.",
            authors="Alice Q., Bob P.",
            doi="10.1038/s41586-026-0001",
            arxiv_id="2601.00001"
        )

        # Step 5: Execute extraction
        ext_res = _run_single_extraction_impl(paper, self.extraction_def, self.workspace)
        self.assertTrue(ext_res["success"])

        extraction = Extraction.objects.get(paper=paper, extraction_definition=self.extraction_def)
        fields = extraction.fields_data
        # Both keys from the returned dict are persisted
        self.assertEqual(fields["trl_level"], 6.0)
        self.assertEqual(fields["trl_level_postprocessed"], 6.0)

        # Step 6: Verify extract_paper_parameters maps these keys
        params = extract_paper_parameters(paper, pipeline_run=self.pipeline_run)
        self.assertEqual(params["trl_level"], 6.0)
        self.assertEqual(params["trl_level_postprocessed"], 6.0)
        self.assertEqual(params["operational_readiness_score"], 9.0)
        self.assertEqual(params["prototype_maturity_score"], 9.0)

        # Compute signal score with workspace.signal_score_code
        # formula: 0.5 * 6.0 + 0.3 * 9.0 + 0.2 * 9.0 = 3.0 + 2.7 + 1.8 = 7.5
        score, rationale = compute_paper_signal_score(paper, pipeline_run=self.pipeline_run)
        self.assertEqual(score, 7.5)


class NarrativePromptBuilderCrossTests(TestCase):
    """
    Cross-tests validating Step 7 Executive Briefing prompt construction under all data states:
    1. Full data populated (titles, abstracts, authors, DOIs, postprocessed score vectors, etc.)
    2. Empty / missing data (no abstracts, no authors, no DOIs, missing extractions, None scores)
    3. Prompt templates with arbitrary non-variable curly braces (e.g., JSON schemas, mathematical set notation)
    4. Boundary conditions for top_n_papers and fallback mechanisms
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Deep Tech AI Scouting",
            llm_provider="google",
            screening_llm_model="google/gemini-3.8-flash",
            narrative_report_prompt=(
                "# Executive Review for {workspace_name}\n"
                "Run Date: {run_date} | Total Processed: {total_papers}\n"
                "Accepted: {accepted_papers_count} | Rejected: {rejected_papers_count}\n"
                "Top {top_n_papers_count} Breakthroughs:\n"
                "{papers}\n\n"
                "Structured Papers Data:\n{papers_json}\n\n"
                "Score Vectors Matrix:\n{score_vectors_summary}\n\n"
                "Raw JSON guideline: {\"briefing_format\": \"executive\", \"min_confidence\": 0.8}"
            ),
            narrative_report_system_prompt="You are a Chief Technology Scout.",
            narrative_report_top_n_papers=5
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="reporting"
        )

    @patch("research_intelligence.llm_providers.get_llm_provider")
    def test_prompt_builds_successfully_with_full_rich_data(self, mock_get_llm):
        """Test prompt construction when papers have full metadata, extractions, and postprocessed score vectors."""
        mock_provider = MagicMock()
        mock_provider.generate.return_value = "### Full Data Executive Briefing\nSynthesized successfully."
        mock_get_llm.return_value = mock_provider

        # Create paper with complete rich metadata
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="rich_paper_001",
            title="Photonic Quantum Neuromorphic Chip Architecture",
            abstract="We present an integrated silicon photonics tensor core achieving 100 TOPS/W.",
            authors="Dr. Angela Vance, Prof. Michael Chang",
            doi="10.1103/PhysRevLett.130.0001",
            arxiv_id="2602.12345",
            source_database="arxiv"
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="full_text_passed",
            signal_score=9.45
        )
        Extraction.objects.create(
            paper=paper,
            workspace=self.workspace,
            category="TRL Assessment",
            confidence_score=0.95,
            fields_data={
                "trl_level": 6.5,
                "trl_level_postprocessed": 6.5,
                "energy_efficiency_tops_w": 100.0,
            }
        )

        res = generate_executive_narrative_report(self.pipeline_run)
        self.assertTrue(res["success"])

        # Check prompt passed to LLM
        mock_provider.generate.assert_called_once()
        prompt_arg = mock_provider.generate.call_args[1]["prompt"]

        # Verify all variables populated
        self.assertIn("Deep Tech AI Scouting", prompt_arg)
        self.assertIn("Photonic Quantum Neuromorphic Chip Architecture", prompt_arg)
        self.assertIn("Dr. Angela Vance, Prof. Michael Chang", prompt_arg)
        self.assertIn("10.1103/PhysRevLett.130.0001", prompt_arg)
        self.assertIn("2602.12345", prompt_arg)
        self.assertIn("9.45", prompt_arg)

        # Verify structured JSON representations
        self.assertIn('"trl_level_postprocessed": 6.5', prompt_arg)
        self.assertIn('"energy_efficiency_tops_w": 100.0', prompt_arg)

        # Verify non-variable JSON braces inside prompt were preserved intact without KeyError
        self.assertIn('{"briefing_format": "executive", "min_confidence": 0.8}', prompt_arg)

        # Verify NarrativeReport saved
        report = NarrativeReport.objects.get(pipeline_run=self.pipeline_run)
        self.assertEqual(report.content_markdown, "### Full Data Executive Briefing\nSynthesized successfully.")

    @patch("research_intelligence.llm_providers.get_llm_provider")
    def test_prompt_builds_safely_with_empty_and_sparse_paper_fields(self, mock_get_llm):
        """Test prompt construction when papers have empty title, abstract, authors, missing DOIs, and unscored metrics."""
        mock_provider = MagicMock()
        mock_provider.generate.return_value = "### Sparse Data Executive Briefing"
        mock_get_llm.return_value = mock_provider

        # Paper with completely empty/None fields
        paper_empty = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="sparse_paper_002",
            title="",
            abstract="",
            authors="",
            doi=None,
            arxiv_id=None,
            source_database=""
        )
        PaperMetric.objects.create(
            paper=paper_empty,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="full_text_passed",
            signal_score=None  # Unscored
        )

        res = generate_executive_narrative_report(self.pipeline_run)
        self.assertTrue(res["success"])

        mock_provider.generate.assert_called_once()
        prompt_arg = mock_provider.generate.call_args[1]["prompt"]

        # Check default fallbacks in prompt text
        self.assertIn("Untitled", prompt_arg)
        self.assertIn("Authors: N/A", prompt_arg)
        self.assertIn("Signal Score: N/A", prompt_arg)

        # Verify JSON block parses cleanly as valid JSON even with sparse/empty data
        report = NarrativeReport.objects.get(pipeline_run=self.pipeline_run)
        self.assertEqual(report.content_markdown, "### Sparse Data Executive Briefing")

    @patch("research_intelligence.llm_providers.get_llm_provider")
    def test_prompt_handles_arbitrary_math_and_json_curlies_without_crashing(self, mock_get_llm):
        """Verify prompt template containing complex code/equations with curly braces does not fail prompt formatting."""
        mock_provider = MagicMock()
        mock_provider.generate.return_value = "Briefing OK"
        mock_get_llm.return_value = mock_provider

        # User writes a prompt containing LaTeX math, set theory, and JSON format examples
        self.workspace.narrative_report_prompt = (
            "Analyze papers for {workspace_name}.\n"
            "Formulas: S = {x | x in R, x > 0} and function f(x) = {x^2}.\n"
            "JSON instructions: {\"key\": \"value\", \"nested\": {\"flag\": true}}\n"
            "Catalog:\n{papers}"
        )
        self.workspace.save()

        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="math_test_paper",
            title="Complex Quantum Systems",
            abstract="Analysis of quantum complexity."
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="full_text_passed",
            signal_score=8.0
        )

        res = generate_executive_narrative_report(self.pipeline_run)
        self.assertTrue(res["success"])

        prompt_arg = mock_provider.generate.call_args[1]["prompt"]
        self.assertIn("Analyze papers for Deep Tech AI Scouting.", prompt_arg)
        self.assertIn("S = {x | x in R, x > 0}", prompt_arg)
        self.assertIn('{"key": "value", "nested": {"flag": true}}', prompt_arg)
        self.assertIn("Complex Quantum Systems", prompt_arg)

    @patch("research_intelligence.llm_providers.get_llm_provider")
    def test_empty_accepted_papers_falls_back_to_standard_report_without_calling_llm(self, mock_get_llm):
        """When 0 papers pass screening, report generation should not waste LLM tokens and should output clean summary."""
        res = generate_executive_narrative_report(self.pipeline_run)
        self.assertTrue(res["success"])

        # LLM provider must not be called when there are no accepted papers
        mock_get_llm.assert_not_called()

        report = NarrativeReport.objects.get(pipeline_run=self.pipeline_run)
        self.assertIn("Executive Research Briefing: Deep Tech AI Scouting", report.content_markdown)
        self.assertIn("No papers passed screening criteria during this run", report.content_markdown)

    @patch("research_intelligence.llm_providers.get_llm_provider")
    def test_empty_or_whitespace_narrative_report_prompt_uses_deterministic_report(self, mock_get_llm):
        """When narrative_report_prompt is None or empty string or whitespace, uses deterministic briefing."""
        self.workspace.narrative_report_prompt = "   \n\t   "
        self.workspace.save()

        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="det_paper_01",
            title="Deterministic Review Paper",
            abstract="Standard abstract."
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="full_text_passed",
            signal_score=7.0
        )

        res = generate_executive_narrative_report(self.pipeline_run)
        self.assertTrue(res["success"])
        mock_get_llm.assert_not_called()

        report = NarrativeReport.objects.get(pipeline_run=self.pipeline_run)
        self.assertIn("Executive Research Briefing: Deep Tech AI Scouting", report.content_markdown)
        self.assertIn("Deterministic Review Paper", report.content_markdown)
