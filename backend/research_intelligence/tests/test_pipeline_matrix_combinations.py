import json
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone

from research_intelligence.models import ComponentRun
from research_intelligence.mcp.tools.extractions import get_paper_extractions_matrix_logic
from research_intelligence.mcp.tools.agent_processes import get_research_agent_status_logic
from research_intelligence.mcp.tools.pipeline_runs import get_pipeline_run_status_logic
from research_intelligence.tests.pipeline_harness import PipelineTestHarness


class PipelineMatrixCombinationsTestCase(TestCase):
    """
    Parametric test suite executing end-to-end pipeline matrices and failure modes:
    1. Direct Full-Text Screening (skip_abstract_screening=True, ocr_provider=None - Multimodal PDF)
    2. Two-Stage Screening (skip_abstract_screening=False, ocr_provider='pypdf')
    3. Positive End-to-End ComponentRun structure & Token/Cost accumulation audit
    4. Negative Failure Halts at each individual pipeline step (Search, Download, OCR, Screening, Extraction)
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
                "abstract": "Variational quantum circuits applied to collider dataset analysis.",
                "arxiv_id": "2401.00010"
            },
            {
                "hash_id": "qml_p1_abstract_rejected",
                "title": "A Survey of Classical Machine Learning for E-Commerce Recommendation",
                "abstract": "We evaluate collaborative filtering and matrix factorization for online retail.",
                "arxiv_id": "2401.00020"
            },
            {
                "hash_id": "qml_p2_download_failed",
                "title": "Withdrawn: Fault-Tolerant Quantum Surface Codes",
                "abstract": "This preprint was retracted by the authors due to calibration discrepancies.",
                "arxiv_id": "2401.00030"
            },
            {
                "hash_id": "qml_p3_full_text_rejected",
                "title": "Experimental Realization of Room Temperature Quantum Supercomputing",
                "abstract": "We describe experimental protocols for quantum advantage at room temperature.",
                "arxiv_id": "2401.00040"
            },
            {
                "hash_id": "qml_p4_pre_withdrawn",
                "title": "Duplicate Publication of Quantum Annealing Benchmarks",
                "abstract": "Duplicate submission of D-Wave benchmark results.",
                "arxiv_id": "2401.00050"
            },
            {
                "hash_id": "qml_p5_all_passed_2",
                "title": "Error Mitigation in Noisy Transmon Quantum Processors",
                "abstract": "Zero-noise extrapolation and probabilistic error cancellation benchmarks.",
                "arxiv_id": "2401.00060"
            }
        ]

    def test_direct_full_text_screening_without_ocr_with_cohort(self):
        """
        Configuration 1: skip_abstract_screening=True, ocr_provider=None (Direct Multimodal PDF)
        Pipeline jumps directly from PDF Download to Full-Text Screening.
        """
        harness = (
            PipelineTestHarness(name="Direct Full-Text Multimodal Lab")
            .configure_workspace(ocr_provider=None, skip_abstract_screening=True)
            .add_scraper(provider="arxiv", search_query="quantum variational")
            .add_extraction_definition(
                name="Quantum Benchmark",
                exit_metric="fidelity",
                response_schema={"type": "object", "properties": {"fidelity": {"type": "number"}}}
            )
            .start_agent("Direct FT Multimodal Agent")
        )

        # Step 1: Search & Ingestion (6 papers ingested)
        harness.complete_step_1_search(self.cohort_papers)
        self.assertEqual(harness.agent_process.current_step, "download")

        # Step 2: PDF Download (Index 2 fails download -> withdrawn)
        harness.complete_step_2_download(failed_paper_indices=[2])
        self.assertEqual(harness.papers[2].screening_status, "withdrawn")
        # Direct multimodal skips OCR -> goes directly to screening
        self.assertEqual(harness.agent_process.current_step, "screening")

        # Step 4: Full-Text Screening (papers 0 and 5 pass, papers 1, 3, 4 rejected)
        harness.complete_step_4b_full_text_screening(passed_paper_indices=[0, 5])
        self.assertEqual(harness.agent_process.current_step, "extraction")
        self.assertEqual(harness.papers[0].screening_status, "full_text_passed")
        self.assertEqual(harness.papers[1].screening_status, "rejected")

        # Step 5: Parameter Extraction
        harness.complete_step_5_extraction(sample_extracted_fields={"fidelity": 0.998})
        self.assertEqual(harness.agent_process.status, "completed")
        self.assertEqual(harness.pipeline_run.status, "completed")

        history_steps = harness.get_step_names_history()
        self.assertIn("search", history_steps)
        self.assertIn("download", history_steps)
        self.assertNotIn("ocr", history_steps)
        self.assertIn("full_text_screening", history_steps)
        self.assertIn("extraction", history_steps)

        # Verify Extraction Matrix
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
        Configuration 2: skip_abstract_screening=False, ocr_provider='pypdf'
        Tests multi-stage funnel filtering across entire cohort:
        - 6 Ingested
        - Index 2 download fails (withdrawn) -> 5 proceed
        - OCR runs on active papers
        - Stage 4a Abstract Screening: indices [0, 3, 5] pass (3 passed); index [1, 4] rejected
        - Stage 4b Full-Text Screening: indices [0, 5] pass (2 passed); index 3 rejected
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

    def test_positive_pipeline_component_runs_and_token_accumulation(self):
        """
        Positive End-to-End Audit:
        1. Validates that every pipeline stage creates well-formed ComponentRun objects.
        2. Validates that tokens_in, tokens_out, and usd_cost accumulate monotonically across all steps.
        3. Validates that status tools (get_research_agent_status, get_pipeline_run_status) expose complete metrics.
        """
        harness = (
            PipelineTestHarness(name="Positive Metrics Audit Lab")
            .configure_workspace(ocr_provider="pypdf", skip_abstract_screening=False)
            .add_scraper(provider="arxiv", search_query="quantum simulation")
            .add_extraction_definition(
                name="Simulation Metrics",
                exit_metric="runtime_seconds",
                response_schema={"type": "object", "properties": {"runtime_seconds": {"type": "number"}}}
            )
            .start_agent("Metrics Audit Agent")
        )

        harness.complete_step_1_search(self.cohort_papers[:3])
        harness.complete_step_2_download()
        harness.complete_step_3_ocr_if_needed()

        # Step 4a: Abstract Screening with token consumption
        harness.complete_step_4a_abstract_screening(
            passed_paper_indices=[0, 1],
            tokens_in=3500,
            tokens_out=450,
            usd_cost=0.0042
        )

        # Step 4b: Full-Text Screening with token consumption
        harness.complete_step_4b_full_text_screening(
            passed_paper_indices=[0],
            tokens_in=18500,
            tokens_out=1200,
            usd_cost=0.0215
        )

        # Step 5: Extraction with token consumption
        harness.complete_step_5_extraction(
            sample_extracted_fields={"runtime_seconds": 45.2},
            tokens_in=6200,
            tokens_out=800,
            usd_cost=0.0084
        )

        self.assertEqual(harness.agent_process.status, "completed")
        self.assertEqual(harness.pipeline_run.status, "completed")

        # 1. Component Runs Audit
        comp_runs = ComponentRun.objects.filter(pipeline_run=harness.pipeline_run)
        step_types = [cr.step_type for cr in comp_runs]
        self.assertIn("search", step_types)
        self.assertIn("download", step_types)
        self.assertIn("ocr", step_types)
        self.assertIn("screening", step_types)
        self.assertIn("extraction", step_types)

        for cr in comp_runs:
            self.assertEqual(cr.status, "completed")
            self.assertIsNotNone(cr.started_at)
            self.assertIsNotNone(cr.completed_at)
            self.assertIsNotNone(cr.metrics)

        # 2. Token & Cost Accumulation Audit
        expected_tokens_in = 3500 + 18500 + 6200
        expected_tokens_out = 450 + 1200 + 800
        expected_tokens_consumed = expected_tokens_in + expected_tokens_out
        expected_cost = round(0.0042 + 0.0215 + 0.0084, 4)

        self.assertEqual(harness.pipeline_run.tokens_in, expected_tokens_in)
        self.assertEqual(harness.pipeline_run.tokens_out, expected_tokens_out)
        self.assertEqual(harness.pipeline_run.tokens_consumed, expected_tokens_consumed)
        self.assertAlmostEqual(float(harness.pipeline_run.usd_cost), expected_cost, places=4)

        # 3. Status Tool Inspection via MCP logic
        agent_status = json.loads(get_research_agent_status_logic(
            user=harness.user,
            process_id=str(harness.agent_process.id)
        ))
        self.assertEqual(agent_status["status"], "completed")
        self.assertEqual(agent_status["current_step"], "completed")
        self.assertEqual(agent_status["paper_metrics"]["tokens_in"], expected_tokens_in)
        self.assertEqual(agent_status["paper_metrics"]["tokens_out"], expected_tokens_out)
        self.assertEqual(agent_status["paper_metrics"]["tokens_consumed"], expected_tokens_consumed)
        self.assertAlmostEqual(agent_status["paper_metrics"]["usd_cost"], expected_cost, places=4)
        self.assertEqual(agent_status["paper_metrics"]["total_papers_fetched"], 3)
        self.assertEqual(agent_status["paper_metrics"]["extractions_count"], 1)

        run_status = json.loads(get_pipeline_run_status_logic(
            user=harness.user,
            pipeline_run_id=str(harness.pipeline_run.id)
        ))
        self.assertEqual(run_status["status"], "completed")
        self.assertEqual(run_status["tokens_in"], expected_tokens_in)
        self.assertEqual(run_status["tokens_out"], expected_tokens_out)

    def test_step_1_search_failure_halt(self):
        """
        Negative Test: Upstream search scraper fails (504 Gateway Timeout).
        Verifies that state engine transitions to 'failed', sets error_message, and exposes it via status tools.
        """
        harness = (
            PipelineTestHarness(name="Search Failure Lab")
            .configure_workspace()
            .add_scraper(provider="arxiv", search_query="fail query")
            .start_agent("Failing Search Agent")
        )
        self.assertEqual(harness.agent_process.current_step, "search")

        harness.inject_failure_at_current_step(error_message="ArXiv API 504 Gateway Timeout")

        self.assertEqual(harness.agent_process.status, "failed")
        self.assertEqual(harness.pipeline_run.status, "failed")
        self.assertIn("504 Gateway Timeout", harness.agent_process.error_message)

        status_json = json.loads(get_research_agent_status_logic(user=harness.user, process_id=str(harness.agent_process.id)))
        self.assertEqual(status_json["status"], "failed")
        self.assertIn("504 Gateway Timeout", status_json["error_message"])

    def test_step_2_download_failure_halt(self):
        """
        Negative Test: Unrecoverable PDF download crash (e.g. S3 Storage connection pool exhausted).
        Verifies that pipeline halts immediately at Step 2 with full error traceability.
        """
        harness = (
            PipelineTestHarness(name="Download Failure Lab")
            .configure_workspace()
            .add_scraper(provider="arxiv", search_query="quantum download")
            .start_agent("Failing Download Agent")
        )
        harness.complete_step_1_search(self.cohort_papers[:2])
        self.assertEqual(harness.agent_process.current_step, "download")

        harness.inject_failure_at_current_step(error_message="S3 Storage Connection Pool Exhausted")

        self.assertEqual(harness.agent_process.status, "failed")
        self.assertEqual(harness.pipeline_run.status, "failed")
        self.assertIn("S3 Storage Connection Pool Exhausted", harness.agent_process.error_message)

        status_json = json.loads(get_research_agent_status_logic(user=harness.user, process_id=str(harness.agent_process.id)))
        self.assertEqual(status_json["status"], "failed")
        self.assertIn("S3 Storage Connection Pool Exhausted", status_json["error_message"])

    def test_step_3_ocr_failure_halt(self):
        """
        Negative Test: Layout OCR engine unrecoverable crash (e.g. Mistral OCR 500 Internal Error).
        Verifies that pipeline halts at Step 3 with error logged in audit trail.
        """
        harness = (
            PipelineTestHarness(name="OCR Failure Lab")
            .configure_workspace(ocr_provider="pypdf")
            .add_scraper(provider="arxiv", search_query="quantum ocr")
            .start_agent("Failing OCR Agent")
        )
        harness.complete_step_1_search(self.cohort_papers[:2])
        harness.complete_step_2_download()
        self.assertEqual(harness.agent_process.current_step, "ocr")

        harness.inject_failure_at_current_step(error_message="Mistral OCR API 500 Internal Server Error")

        self.assertEqual(harness.agent_process.status, "failed")
        self.assertEqual(harness.pipeline_run.status, "failed")
        self.assertIn("Mistral OCR API 500", harness.agent_process.error_message)

        status_json = json.loads(get_research_agent_status_logic(user=harness.user, process_id=str(harness.agent_process.id)))
        self.assertEqual(status_json["status"], "failed")
        self.assertIn("Mistral OCR API 500", status_json["error_message"])

    def test_step_4_screening_failure_halt(self):
        """
        Negative Test: Screening LLM backend fatal error (e.g. Rate limit 429 quota exhausted after max retries).
        Verifies that pipeline halts at Step 4 and preserves partial progress.
        """
        harness = (
            PipelineTestHarness(name="Screening Failure Lab")
            .configure_workspace(ocr_provider=None, skip_abstract_screening=True)
            .add_scraper(provider="arxiv", search_query="quantum screening")
            .start_agent("Failing Screening Agent")
        )
        harness.complete_step_1_search(self.cohort_papers[:2])
        harness.complete_step_2_download()
        self.assertEqual(harness.agent_process.current_step, "screening")

        harness.inject_failure_at_current_step(error_message="LLM Provider Quota Exhausted: 429 RESOURCE_EXHAUSTED")

        self.assertEqual(harness.agent_process.status, "failed")
        self.assertEqual(harness.pipeline_run.status, "failed")
        self.assertIn("RESOURCE_EXHAUSTED", harness.agent_process.error_message)

        status_json = json.loads(get_research_agent_status_logic(user=harness.user, process_id=str(harness.agent_process.id)))
        self.assertEqual(status_json["status"], "failed")
        self.assertIn("RESOURCE_EXHAUSTED", status_json["error_message"])

    def test_step_5_extraction_failure_halt(self):
        """
        Negative Test: Extraction parser unrecoverable schema validation failure.
        Verifies that pipeline halts at Step 5.
        """
        harness = (
            PipelineTestHarness(name="Extraction Failure Lab")
            .configure_workspace(ocr_provider=None, skip_abstract_screening=True)
            .add_scraper(provider="arxiv", search_query="quantum extract")
            .add_extraction_definition(name="Crucial Parameter")
            .start_agent("Failing Extraction Agent")
        )
        harness.complete_step_1_search(self.cohort_papers[:2])
        harness.complete_step_2_download()
        harness.complete_step_4b_full_text_screening(passed_paper_indices=[0])
        self.assertEqual(harness.agent_process.current_step, "extraction")

        harness.inject_failure_at_current_step(error_message="JSON Schema Validation Fatal: missing required properties")

        self.assertEqual(harness.agent_process.status, "failed")
        self.assertEqual(harness.pipeline_run.status, "failed")
        self.assertIn("JSON Schema Validation Fatal", harness.agent_process.error_message)

        status_json = json.loads(get_research_agent_status_logic(user=harness.user, process_id=str(harness.agent_process.id)))
        self.assertEqual(status_json["status"], "failed")
        self.assertIn("JSON Schema Validation Fatal", status_json["error_message"])
