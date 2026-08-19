import json
from unittest.mock import patch, MagicMock
from django.test import TestCase

from research_intelligence.tests.pipeline_harness import PipelineTestHarness
from research_intelligence.mcp.tools.extractions import get_paper_extractions_matrix_logic


class PipelineMatrixCombinationsTestCase(TestCase):
    """
    Parametric end-to-end simulation tests using PipelineTestHarness across all workspace topologies:
    1. Direct Full-Text Screening (skip_abstract_screening=True) without OCR (direct multimodal PDF).
    2. Direct Full-Text Screening (skip_abstract_screening=True) with OCR (pypdf).
    3. 2-Stage Screening (Stage 4a: Abstract -> Stage 4b: Full-Text) without OCR.
    4. 2-Stage Screening (Stage 4a: Abstract -> Stage 4b: Full-Text) with OCR.
    5. Mid-Pipeline Search Failure injection (fails cleanly with error log).
    6. Empty Search Result handling (halts early without downloading or screening).

    Uses a comprehensive multi-paper test cohort representing:
    - Index 0: Fully Accepted Paper (Passes Download, Abstract & Full-Text)
    - Index 1: Abstract-Rejected Paper (Out-of-domain scope)
    - Index 2: Download-Failed Paper (404 Not Found at source -> Auto-Withdrawn)
    - Index 3: Full-Text Rejected Paper (Flawed methodology in PDF body)
    - Index 4: Pre-Withdrawn Paper (Withdrawn by authors at source)
    - Index 5: Second Fully Accepted Paper (Passes Download, Abstract & Full-Text)
    """

    def setUp(self):
        self.sleep_patcher = patch("time.sleep", return_value=None)
        self.sleep_patcher.start()
        self.addCleanup(self.sleep_patcher.stop)

        self.llm_patcher = patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
        self.mock_llm = self.llm_patcher.start()
        self.mock_llm.return_value = {
            "passed": True,
            "reasoning": "Mocked LLM response",
            "evidence_quotes": ["mock evidence"],
            "decision_category": "ACCEPTED"
        }
        self.addCleanup(self.llm_patcher.stop)

        self.cohort_papers = [
            {
                "hash_id": "qml_p0_all_passed",
                "title": "Quantum Machine Learning Algorithms for High Energy Physics",
                "abstract": "We demonstrate variational quantum circuits on CERN datasets with high fidelity.",
                "arxiv_id": "2401.00010"
            },
            {
                "hash_id": "qml_p1_abstract_rejected",
                "title": "Classical Gradient Boosting for Retail Forecasting",
                "abstract": "Standard XGBoost on tabular retail sales data without quantum components.",
                "arxiv_id": "2401.00020"
            },
            {
                "hash_id": "qml_p2_download_failed",
                "title": "404 Broken Source Link Document",
                "abstract": "Quantum annealing study where remote PDF host returns 404.",
                "arxiv_id": "2401.00030"
            },
            {
                "hash_id": "qml_p3_full_text_rejected",
                "title": "Uncalibrated Quantum Annealing Benchmarks",
                "abstract": "Experimental results on D-Wave processor with potential speedup claims.",
                "arxiv_id": "2401.00040"
            },
            {
                "hash_id": "qml_p4_withdrawn_at_search",
                "title": "Retracted Room-Temperature Superconducting Study",
                "abstract": "Study on LK-99 quantum resistance measurements.",
                "arxiv_id": "2401.00050"
            },
            {
                "hash_id": "qml_p5_second_accepted",
                "title": "Error Mitigation in Noisy Transmon Quantum Processors",
                "abstract": "Zero-noise extrapolation benchmark results on 127-qubit quantum processor.",
                "arxiv_id": "2401.00060"
            }
        ]

    def test_direct_full_text_screening_without_ocr_with_cohort(self):
        """
        Configuration 1: skip_abstract_screening=True, ocr_provider=None (Direct Multimodal PDF)
        Tests full cohort filtering:
        - Download failure at index 2 -> Withdrawn
        - Full-text screening evaluates remaining papers: indices [0, 5] pass, index [1, 3, 4] rejected
        - Extraction processes only indices [0, 5]
        """
        harness = (
            PipelineTestHarness(name="Direct Full-Text Multimodal Cohort Lab")
            .configure_workspace(ocr_provider=None, skip_abstract_screening=True)
            .add_scraper(provider="arxiv", search_query="quantum machine learning")
            .add_extraction_definition(
                name="Quantum Metrics",
                exit_metric="fidelity_score",
                response_schema={"type": "object", "properties": {"fidelity_score": {"type": "number"}}}
            )
            .start_agent("Direct FT Cohort Agent")
        )

        self.assertEqual(harness.agent_process.current_step, "search")

        # Step 1: Ingest 6 papers
        harness.complete_step_1_search(self.cohort_papers)
        self.assertEqual(len(harness.papers), 6)
        self.assertEqual(harness.agent_process.current_step, "download")

        # Step 2: Download with failure on index 2 (404) -> Skips OCR (ocr_provider=None) -> transitions to 'screening'
        harness.complete_step_2_download(failed_paper_indices=[2])
        self.assertEqual(harness.agent_process.current_step, "screening")
        self.assertEqual(harness.papers[2].screening_status, "withdrawn")

        # Step 4: Direct Full-Text Screening (Paper 0 and Paper 5 pass; others rejected)
        harness.complete_step_4b_full_text_screening(passed_paper_indices=[0, 5])
        self.assertEqual(harness.agent_process.current_step, "extraction")
        self.assertEqual(harness.papers[0].screening_status, "full_text_passed")
        self.assertEqual(harness.papers[5].screening_status, "full_text_passed")
        self.assertEqual(harness.papers[1].screening_status, "rejected")

        # Step 5: Complete Extraction
        harness.complete_step_5_extraction(sample_extracted_fields={"fidelity_score": 0.994})
        self.assertEqual(harness.agent_process.current_step, "completed")
        self.assertEqual(harness.agent_process.status, "completed")
        self.assertEqual(harness.pipeline_run.status, "completed")

        # Verify audit history
        history_steps = harness.get_step_names_history()
        self.assertIn("search", history_steps)
        self.assertIn("download", history_steps)
        self.assertNotIn("ocr", history_steps)  # Correctly skipped
        self.assertNotIn("abstract_screening", history_steps)  # Correctly skipped
        self.assertIn("full_text_screening", history_steps)
        self.assertIn("extraction", history_steps)

        # Verify extraction matrix has exactly 2 passed papers
        matrix = json.loads(get_paper_extractions_matrix_logic(
            user=harness.user,
            workspace_id=str(harness.workspace.id),
            screening_status="accepted"
        ))
        self.assertEqual(matrix["total_papers"], 2)
        extracted_titles = [p["title"] for p in matrix["papers"]]
        self.assertIn("Quantum Machine Learning Algorithms for High Energy Physics", extracted_titles)
        self.assertIn("Error Mitigation in Noisy Transmon Quantum Processors", extracted_titles)

    def test_two_stage_screening_with_ocr_and_full_cohort(self):
        """
        Configuration 4: skip_abstract_screening=False, ocr_provider='pypdf'
        Tests multi-stage funnel filtering across entire cohort:
        - 6 Ingested
        - Index 2 download fails (withdrawn) -> 5 proceed
        - OCR runs on 5 active papers
        - Stage 4a Abstract Screening: indices [0, 3, 5] pass (3 passed); index [1, 4] rejected
        - Stage 4b Full-Text Screening: indices [0, 5] pass (2 passed); index 3 rejected (methodology flaw)
        - Step 5 Extraction: processes exactly indices [0, 5]
        """
        harness = (
            PipelineTestHarness(name="2-Stage OCR Cohort Lab")
            .configure_workspace(ocr_provider="pypdf", skip_abstract_screening=False)
            .add_scraper(provider="arxiv", search_query="quantum processors")
            .add_extraction_definition(
                name="Processor Specs",
                exit_metric="qubit_count",
                response_schema={"type": "object", "properties": {"qubit_count": {"type": "integer"}}}
            )
            .start_agent("2-Stage OCR Agent")
        )

        harness.complete_step_1_search(self.cohort_papers)
        self.assertEqual(harness.agent_process.current_step, "download")

        harness.complete_step_2_download(failed_paper_indices=[2])
        self.assertEqual(harness.agent_process.current_step, "ocr")

        harness.complete_step_3_ocr_if_needed()
        self.assertEqual(harness.agent_process.current_step, "screening")

        # Stage 4a: Abstract Screening (0, 3, 5 pass; 1, 4 rejected)
        harness.complete_step_4a_abstract_screening(passed_paper_indices=[0, 3, 5])
        self.assertEqual(harness.agent_process.current_step, "screening")
        self.assertEqual(harness.papers[1].screening_status, "rejected")

        # Stage 4b: Full-Text Screening (0, 5 pass; 3 rejected)
        harness.complete_step_4b_full_text_screening(passed_paper_indices=[0, 5])
        self.assertEqual(harness.agent_process.current_step, "extraction")
        self.assertEqual(harness.papers[3].screening_status, "rejected")

        # Step 5: Extraction
        harness.complete_step_5_extraction(sample_extracted_fields={"qubit_count": 127})
        self.assertEqual(harness.agent_process.status, "completed")

        history_steps = harness.get_step_names_history()
        self.assertIn("search", history_steps)
        self.assertIn("download", history_steps)
        self.assertIn("ocr", history_steps)
        self.assertIn("abstract_screening", history_steps)
        self.assertIn("full_text_screening", history_steps)
        self.assertIn("extraction", history_steps)

        # Verify matrix contains only the 2 final survivors
        matrix = json.loads(get_paper_extractions_matrix_logic(
            user=harness.user,
            workspace_id=str(harness.workspace.id),
            screening_status="accepted"
        ))
        self.assertEqual(matrix["total_papers"], 2)
        self.assertEqual(matrix["papers"][0]["metrics_summary"]["Processor Specs"], "127")

    def test_mid_pipeline_failure_halt(self):
        """
        Simulates an upstream search scraper network timeout or failure:
        State engine transitions to 'failed', updates pipeline run status, and logs error.
        """
        harness = (
            PipelineTestHarness(name="Failure Simulation Lab")
            .configure_workspace()
            .add_scraper(provider="arxiv", search_query="fail query")
            .start_agent("Failing Agent")
        )

        self.assertEqual(harness.agent_process.current_step, "search")

        # Inject failure at Step 1
        harness.inject_failure_at_current_step(error_message="ArXiv API 504 Gateway Timeout")

        self.assertEqual(harness.agent_process.status, "failed")
        self.assertEqual(harness.pipeline_run.status, "failed")
        self.assertIn("504 Gateway Timeout", harness.agent_process.error_message)
