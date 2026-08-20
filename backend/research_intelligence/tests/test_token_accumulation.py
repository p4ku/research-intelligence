import json
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    ComponentRun,
    Paper,
    ExtractionDefinition,
    Extraction
)
from research_intelligence.tasks.step_4_screening.abstract import execute_screening_job
from research_intelligence.tasks.step_4_screening.full_text import execute_full_text_screening_job
from research_intelligence.tasks.step_5_extraction.extract import execute_extraction_job


class PipelineTokenAccumulationTestCase(TestCase):
    """
    Validates that LLM token usage and USD costs are strictly accumulated (summed)
    across all pipeline stages (Abstract Screening -> Full-Text Screening -> Extraction)
    and are NEVER overwritten on the PipelineRun or Workspace instances.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Token Accumulation Workspace",
            screening_llm_model="google/gemini-3.7-flash",
            abstract_acceptance_criteria="Quantum algorithms",
            abstract_rejection_criteria="Classical algorithms",
            full_text_acceptance_criteria="Quantum error correction benchmarks",
            full_text_rejection_criteria="Pure survey"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.paper1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="hash_tok_001",
            title="Scalable Quantum Error Correction with Surface Codes",
            abstract="We present a scalable architecture for surface code error correction.",
            screening_status="pending"
        )
        self.paper2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="hash_tok_002",
            title="Fault-Tolerant Quantum Computing Architectures",
            abstract="Analysis of logical qubits and threshold theorems.",
            screening_status="pending"
        )
        self.extraction_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Threshold Extraction",
            exit_metric="error_threshold",
            system_prompt="Extract physical error threshold percentage.",
            user_prompt_template="Paper text: {paper_text}",
            response_schema={
                "type": "object",
                "properties": {
                    "error_threshold": {"type": "string"},
                    "confidence": {"type": "number"}
                },
                "required": ["error_threshold"]
            }
        )

    def test_multi_step_token_and_cost_accumulation(self):
        """
        Executes Step 4a, Step 4b, and Step 5 sequentially and confirms that:
        1. Tokens In, Tokens Out, Total Tokens Consumed accumulate additively.
        2. USD Cost accumulates additively without rounding truncation.
        3. No step resets or overwrites previous step's token counts.
        """
        # ==========================================
        # STEP 4a: Abstract Screening
        # ==========================================
        step4a_comp = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            component_name="abstract_screening",
            step_type="screening",
            status="pending"
        )

        mock_4a_response = {
            "success": True,
            "passed": True,
            "screening_status": "abstract_passed",
            "reasoning": "Passes abstract criteria on quantum computing",
            "evidence_quotes": ["scalable architecture"],
            "decision_category": "ACCEPTED",
            "duration_seconds": 1.0,
            "usage": {
                "tokens_in": 1200,
                "tokens_out": 300,
                "total_tokens": 1500
            }
        }

        def mock_4a_side_effect(paper_id, workspace_id, **kwargs):
            p = Paper.objects.get(id=paper_id)
            p.screening_status = "abstract_passed"
            p.save(update_fields=['screening_status'])
            return mock_4a_response

        with patch("research_intelligence.tasks.step_4_screening.abstract.screen_abstract", side_effect=mock_4a_side_effect):
            success_4a = execute_screening_job(str(step4a_comp.id))
            self.assertTrue(success_4a)

        self.pipeline_run.refresh_from_db()
        step4a_comp.refresh_from_db()

        # Step 4a processed 2 papers: 2 * 1200 in = 2400, 2 * 300 out = 600, total = 3000
        step4a_tokens_in = 2400
        step4a_tokens_out = 600
        step4a_tokens_total = 3000
        self.assertEqual(self.pipeline_run.tokens_in, step4a_tokens_in)
        self.assertEqual(self.pipeline_run.tokens_out, step4a_tokens_out)
        self.assertEqual(self.pipeline_run.tokens_consumed, step4a_tokens_total)
        step4a_cost = self.pipeline_run.usd_cost
        self.assertGreater(step4a_cost, Decimal('0.0000'))

        # ==========================================
        # STEP 4b: Full-Text Screening
        # ==========================================
        step4b_comp = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            component_name="full_text_screening",
            step_type="screening",
            status="pending"
        )

        mock_4b_response = {
            "success": True,
            "passed": True,
            "screening_status": "full_text_passed",
            "reasoning": "Full text contains rigorous error correction proofs",
            "evidence_quotes": ["threshold is 1.1%"],
            "decision_category": "ACCEPTED",
            "input_source": "abstract_fallback",
            "duration_seconds": 1.5,
            "usage": {
                "tokens_in": 2500,
                "tokens_out": 500,
                "total_tokens": 3000
            }
        }

        def mock_4b_side_effect(paper_id, workspace_id, **kwargs):
            p = Paper.objects.get(id=paper_id)
            p.screening_status = "full_text_passed"
            p.save(update_fields=['screening_status'])
            return mock_4b_response

        with patch("research_intelligence.tasks.step_4_screening.full_text.screen_full_text", side_effect=mock_4b_side_effect):
            success_4b = execute_full_text_screening_job(str(step4b_comp.id))
            self.assertTrue(success_4b)

        self.pipeline_run.refresh_from_db()
        step4b_comp.refresh_from_db()

        # Step 4b processed 2 papers: 2 * 2500 in = 5000, 2 * 500 out = 1000, total = 6000
        step4b_tokens_in = 5000
        step4b_tokens_out = 1000
        step4b_tokens_total = 6000

        # Verify PipelineRun contains the SUM of 4a + 4b (NOT overwritten)
        expected_cumulative_in_after_4b = step4a_tokens_in + step4b_tokens_in       # 2400 + 5000 = 7400
        expected_cumulative_out_after_4b = step4a_tokens_out + step4b_tokens_out   # 600 + 1000 = 1600
        expected_cumulative_total_after_4b = step4a_tokens_total + step4b_tokens_total # 3000 + 6000 = 9000

        self.assertEqual(self.pipeline_run.tokens_in, expected_cumulative_in_after_4b)
        self.assertEqual(self.pipeline_run.tokens_out, expected_cumulative_out_after_4b)
        self.assertEqual(self.pipeline_run.tokens_consumed, expected_cumulative_total_after_4b)
        self.assertGreater(self.pipeline_run.usd_cost, step4a_cost)
        step4b_cost = self.pipeline_run.usd_cost

        # ==========================================
        # STEP 5: Dynamic Parameter Extraction
        # ==========================================
        step5_comp = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            component_name="extraction",
            step_type="extraction",
            status="pending"
        )

        mock_5_response = {
            "success": True,
            "paper_id": str(self.paper1.id),
            "paper_title": self.paper1.title,
            "definition_id": str(self.extraction_def.id),
            "definition_name": self.extraction_def.name,
            "validation_status": "pass",
            "confidence_score": 0.95,
            "extracted_fields_count": 2,
            "duration_seconds": 1.8,
            "usage": {
                "tokens_in": 1500,
                "tokens_out": 400,
                "total_tokens": 1900
            }
        }

        with patch("research_intelligence.tasks.step_5_extraction.extract._run_single_extraction_worker", return_value=mock_5_response):
            success_5 = execute_extraction_job(str(step5_comp.id))
            self.assertTrue(success_5)

        self.pipeline_run.refresh_from_db()
        step5_comp.refresh_from_db()

        # Step 5 processed 2 papers x 1 def = 2 extractions: 2 * 1500 in = 3000, 2 * 400 out = 800, total = 3800
        step5_tokens_in = 3000
        step5_tokens_out = 800
        step5_tokens_total = 3800

        # Verify PipelineRun contains the COMPLETE SUM of 4a + 4b + 5
        expected_final_in = expected_cumulative_in_after_4b + step5_tokens_in          # 7400 + 3000 = 10400
        expected_final_out = expected_cumulative_out_after_4b + step5_tokens_out       # 1600 + 800 = 2400
        expected_final_total = expected_cumulative_total_after_4b + step5_tokens_total # 9000 + 3800 = 12800

        self.assertEqual(self.pipeline_run.tokens_in, expected_final_in)
        self.assertEqual(self.pipeline_run.tokens_out, expected_final_out)
        self.assertEqual(self.pipeline_run.tokens_consumed, expected_final_total)
        self.assertGreater(self.pipeline_run.usd_cost, step4b_cost)

        # Verify ComponentRun breakdown vs PipelineRun total
        sum_component_tokens = (
            step4a_comp.metrics.get("tokens_in", 0) + step4a_comp.metrics.get("tokens_out", 0) +
            step4b_comp.metrics.get("tokens_in", 0) + step4b_comp.metrics.get("tokens_out", 0) +
            step5_comp.metrics.get("tokens_in", 0) + step5_comp.metrics.get("tokens_out", 0)
        )
        self.assertEqual(sum_component_tokens, self.pipeline_run.tokens_consumed)

        # Verify ComponentRun metrics persist positive USD cost
        self.assertGreater(step4a_comp.metrics.get("usd_cost", 0.0), 0.0)
        self.assertGreater(step4b_comp.metrics.get("usd_cost", 0.0), 0.0)
        self.assertGreater(step5_comp.metrics.get("usd_cost", 0.0), 0.0)

        sum_component_costs = (
            step4a_comp.metrics.get("usd_cost", 0.0) +
            step4b_comp.metrics.get("usd_cost", 0.0) +
            step5_comp.metrics.get("usd_cost", 0.0)
        )
        self.assertAlmostEqual(sum_component_costs, float(self.pipeline_run.usd_cost), places=4)

        # Verify Workspace monthly quota recorded all tokens
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.tokens_consumed_this_month, expected_final_total)

    def test_component_run_cost_rendering_and_legacy_fallback(self):
        """
        Validates render_component_cost formatting across various scenarios:
        1. Completed LLM step with persisted usd_cost and total_tokens.
        2. Legacy/historical step with tokens_in/tokens_out but usd_cost=0 or missing.
        3. Non-LLM step (search, download) -> renders $0.0000.
        """
        from research_intelligence.admin import render_component_cost, render_component_metrics_summary

        # 1. Step with persisted usd_cost
        comp_llm = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            component_name="abstract_screening",
            step_type="screening",
            status="completed",
            metrics={
                "usd_cost": 0.0125,
                "total_tokens": 15000,
                "total_screened": 10,
                "passed": 8,
                "rejected": 2
            }
        )
        html_cost = str(render_component_cost(comp_llm))
        self.assertIn("$0.0125", html_cost)
        self.assertIn("15,000 tok", html_cost)

        html_summary = str(render_component_metrics_summary(comp_llm))
        self.assertIn("10 screened:", html_summary)
        self.assertIn("8 passed", html_summary)
        self.assertIn("2 rejected", html_summary)

        # 2. Legacy step with tokens_in/tokens_out but usd_cost was missing / 0.0
        comp_legacy = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            component_name="full_text_screening",
            step_type="screening",
            status="completed",
            metrics={
                "model_used": "google/gemini-3.7-flash",
                "tokens_in": 10000,
                "tokens_out": 2000,
                "total_tokens": 12000,
                "usd_cost": 0.0
            }
        )
        html_legacy_cost = str(render_component_cost(comp_legacy))
        self.assertNotIn("$0.0000", html_legacy_cost)
        self.assertIn("12,000 tok", html_legacy_cost)

        # 3. Non-LLM step without tokens (e.g. search / download)
        comp_non_llm = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            component_name="arxiv_scraper",
            step_type="search",
            status="completed",
            metrics={"total_fetched": 24}
        )
        html_non_llm = str(render_component_cost(comp_non_llm))
        self.assertIn("$0.0000", html_non_llm)

    def test_calculate_llm_cost_precision(self):
        """
        Validates calculate_llm_cost calculation and precision boundaries.
        """
        from research_intelligence.llm_providers.pricing import calculate_llm_cost

        # 0 tokens -> 0.0000
        cost_zero = calculate_llm_cost("google/gemini-3.7-flash", 0, 0)
        self.assertEqual(cost_zero, Decimal("0.0000"))

        # Small tokens (e.g. 10 in, 5 out) -> should return minimum 0.0001
        cost_micro = calculate_llm_cost("google/gemini-3.7-flash", 10, 5)
        self.assertGreaterEqual(cost_micro, Decimal("0.0001"))

        # 1M input tokens for gemini-3.7-flash ($0.75 / 1M in) -> 0.7500
        cost_1m = calculate_llm_cost("google/gemini-3.7-flash", 1_000_000, 0)
        self.assertEqual(cost_1m, Decimal("0.7500"))

