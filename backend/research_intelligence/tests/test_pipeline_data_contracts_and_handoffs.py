"""
Comprehensive integration tests validating strict data contracts, inter-stage handoffs,
and state transitions across the entire 8-step SLR processing pipeline.
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.core.files.storage import default_storage

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    Paper,
    ComponentRun,
    ExtractionDefinition,
    Extraction,
    PaperMetric,
    ResearchAgentProcess,
)
from research_intelligence.tasks.orchestrator.dag.pipelines import build_default_slr_dag
from research_intelligence.tasks.step_2_download.fetch import execute_pdf_download_job
from research_intelligence.tasks.step_3_ocr.convert import execute_ocr_job
from research_intelligence.tasks.step_4_screening.abstract import execute_screening_job
from research_intelligence.tasks.step_4_screening.full_text import execute_full_text_screening_job
from research_intelligence.tasks.step_5_extraction.extract import execute_extraction_job
from research_intelligence.tasks.step_6_signal_score.scorer import execute_signal_score_job


class PipelineDataContractsAndHandoffsTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="End-to-End Quantum SLR Project",
            abstract_acceptance_criteria="Accept quantum computing and fault-tolerant algorithms.",
            abstract_rejection_criteria="Reject classical heuristics or non-peer-reviewed notes.",
            full_text_acceptance_criteria="Must provide hardware benchmark metrics or error threshold proofs.",
            full_text_rejection_criteria="Purely speculative non-empirical whitepapers.",
            signal_score_code="""
# Weighted composite calculation
base = 0.5 * fit_score + 0.3 * novelty_score + 0.2 * trl_level
if trl_level >= 6:
    base = base * 1.15
return round(min(base, 10.0), 2)
""",
            ocr_provider=None  # Default: direct multimodal PDF ingestion
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.agent_process = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            current_step="search",
            status="idle"
        )

        # Create extraction definitions with valid schema
        self.def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
            exit_metrics="trl_level",
            system_prompt="Extract TRL level with exact quote.",
            user_prompt_template="Analyze this text: {paper_text}",
            response_schema={
                "type": "object",
                "properties": {
                    "trl_level": {"type": "number", "minimum": 1, "maximum": 9},
                    "reasoning": {"type": "string"},
                    "evidence_quote": {"type": "string"}
                },
                "required": ["trl_level"]
            },
            is_active=True
        )
        self.def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Fit Score",
            exit_metrics="fit_score",
            system_prompt="Extract Fit Score.",
            user_prompt_template="Analyze this text: {paper_text}",
            response_schema={
                "type": "object",
                "properties": {
                    "fit_score": {"type": "number", "minimum": 0, "maximum": 10},
                    "reasoning": {"type": "string"},
                    "evidence_quote": {"type": "string"}
                },
                "required": ["fit_score"]
            },
            is_active=True
        )
        self.def_novelty = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Score",
            exit_metrics="novelty_score",
            system_prompt="Extract Novelty Score.",
            user_prompt_template="Analyze this text: {paper_text}",
            response_schema={
                "type": "object",
                "properties": {
                    "novelty_score": {"type": "number", "minimum": 0, "maximum": 10},
                    "reasoning": {"type": "string"},
                    "evidence_quote": {"type": "string"}
                },
                "required": ["novelty_score"]
            },
            is_active=True
        )

    def test_slr_dag_topology_and_contracts(self):
        dag = build_default_slr_dag(workspace=self.workspace)
        self.assertEqual(len(dag.nodes), 8)
        self.assertIn("search", dag.nodes)
        self.assertIn("abstract_screening", dag.nodes)
        self.assertIn("download", dag.nodes)
        self.assertIn("ocr", dag.nodes)
        self.assertIn("full_text_screening", dag.nodes)
        self.assertIn("extraction", dag.nodes)
        self.assertIn("signal_score", dag.nodes)
        self.assertIn("reporting", dag.nodes)

        # Verify OCRNode is skippable when ocr_provider is None
        ocr_node = dag.nodes["ocr"]
        self.assertTrue(ocr_node.is_skippable(self.pipeline_run, self.workspace, {}))

    @patch("research_intelligence.tasks.step_6_signal_score.scorer.compute_paper_signal_score")
    @patch("research_intelligence.tasks.step_5_extraction.extract.get_llm_provider")
    @patch("research_intelligence.tasks.step_4_screening.full_text.get_llm_provider")
    @patch("research_intelligence.tasks.step_4_screening.abstract.get_llm_provider")
    @patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file")
    def test_full_pipeline_data_handoff_contract_flow(
        self,
        mock_arxiv_download_file,
        mock_abstract_llm_provider,
        mock_fulltext_llm_provider,
        mock_extraction_llm_provider,
        mock_calc_signal_score,
    ):
        # 1. STEP 1 (Search Output Contract): Ingest papers
        paper_1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="quantum_paper_001",
            title="Fault-Tolerant Surface Code Architecture on Superconducting Qubits",
            authors="John Martinis, Devoret",
            abstract="We present a 100-qubit fault-tolerant quantum processor architecture with surface code error correction.",
            doi="10.1038/s41586-024-0001",
            arxiv_id="2401.00001",
            source_database="arxiv"
        )
        paper_2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="classical_paper_002",
            title="Classical Monte Carlo Heuristics for Matrix Multiplication",
            authors="Traditionalist",
            abstract="A simple classical algorithm without any quantum mechanisms.",
            arxiv_id="2401.00002",
            source_database="arxiv"
        )

        self.assertEqual(self.pipeline_run.papers.count(), 2)

        # Setup all LLM & provider mocks up front
        mock_arxiv_download_file.return_value = b"%PDF-1.4 Fake Quantum Document Binary Stream with Surface Code"

        abstract_llm = MagicMock()
        def mock_abstract_eval(prompt="", **kwargs):
            if "Fault-Tolerant Surface Code" in str(prompt):
                return (
                    {"passed": True, "decision_category": "ACCEPT", "reasoning": "Strong match for quantum algorithms."},
                    {"prompt_tokens": 300, "candidates_tokens": 80, "total_tokens": 380}
                )
            else:
                return (
                    {"passed": False, "decision_category": "REJECT", "reasoning": "Purely classical heuristic."},
                    {"prompt_tokens": 300, "candidates_tokens": 80, "total_tokens": 380}
                )
        abstract_llm.generate.side_effect = mock_abstract_eval
        mock_abstract_llm_provider.return_value = abstract_llm

        fulltext_llm = MagicMock()
        fulltext_llm.generate.return_value = (
            {"passed": True, "decision_category": "FULL_TEXT_PASSED", "reasoning": "Empirical threshold proofs included."},
            {"prompt_tokens": 1200, "candidates_tokens": 120, "total_tokens": 1320}
        )
        mock_fulltext_llm_provider.return_value = fulltext_llm

        extraction_llm = MagicMock()
        def mock_extract(prompt=None, system_instruction=None, **kwargs):
            comb = (str(prompt or "") + " " + str(system_instruction or "")).lower()
            if "trl" in comb:
                return (
                    {"trl_level": 7.0, "reasoning": "Demonstrated 100-qubit processor.", "confidence_score": 0.95, "evidence_quote": "Demonstrated operational stability."},
                    {"prompt_tokens": 500, "candidates_tokens": 100, "total_tokens": 600}
                )
            elif "fit" in comb:
                return (
                    {"fit_score": 9.5, "reasoning": "Direct match for quantum fault tolerance.", "confidence_score": 0.98, "evidence_quote": "Surface code threshold demonstrated."},
                    {"prompt_tokens": 500, "candidates_tokens": 100, "total_tokens": 600}
                )
            else:
                return (
                    {"novelty_score": 8.8, "reasoning": "Breakthrough in lattice topology.", "confidence_score": 0.92, "evidence_quote": "Novel lattice connectivity."},
                    {"prompt_tokens": 500, "candidates_tokens": 100, "total_tokens": 600}
                )
        extraction_llm.generate.side_effect = mock_extract
        mock_extraction_llm_provider.return_value = extraction_llm
        mock_calc_signal_score.return_value = (8.75, {"score": 8.75})

        # 2. STEP 2 (Abstract Screening Contract Handoff):
        screening_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="abstract_screening",
            status="pending"
        )
        abstract_res = execute_screening_job(str(screening_comp_run.id))
        self.assertTrue(abstract_res)

        pm1 = PaperMetric.objects.get(paper=paper_1, pipeline_run=self.pipeline_run)
        pm2 = PaperMetric.objects.get(paper=paper_2, pipeline_run=self.pipeline_run)
        self.assertEqual(pm1.screening_status, "abstract_passed")
        self.assertEqual(pm2.screening_status, "rejected")

        # 3. STEP 3 (Download Contract Handoff - Targets ONLY abstract_passed papers):
        download_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="download",
            component_name="pdf_downloader",
            status="pending"
        )
        download_res = execute_pdf_download_job(str(download_comp_run.id))
        self.assertTrue(download_res)

        paper_1.refresh_from_db()
        paper_2.refresh_from_db()
        self.assertTrue(default_storage.exists(paper_1.original_pdf_path))
        self.assertFalse(default_storage.exists(f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{paper_2.hash_id}/original.pdf"))

        download_comp_run.refresh_from_db()
        self.assertEqual(download_comp_run.metrics["downloaded"], 1)

        # 4. STEP 4 (OCR Skippable Check):
        ocr_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="ocr",
            component_name="ocr_converter",
            status="pending"
        )
        ocr_res = execute_ocr_job(str(ocr_comp_run.id))
        self.assertTrue(ocr_res)
        ocr_comp_run.refresh_from_db()
        self.assertEqual(ocr_comp_run.status, "skipped")

        # 5. STEP 5 (Full-Text Multimodal Screening Contract Handoff):
        fulltext_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="full_text_screening",
            status="pending"
        )
        fulltext_res = execute_full_text_screening_job(str(fulltext_comp_run.id))
        self.assertTrue(fulltext_res)

        pm1.refresh_from_db()
        self.assertEqual(pm1.screening_status, "full_text_passed")

        # 6. STEP 6 (Dynamic Extraction Contract Handoff):
        extraction_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="extraction",
            component_name="dynamic_extractor",
            status="pending"
        )
        extraction_res = execute_extraction_job(str(extraction_comp_run.id))
        self.assertTrue(extraction_res)

        # Verify database extractions and validation status
        exts = Extraction.objects.filter(paper=paper_1)
        self.assertEqual(exts.count(), 3)
        for ext in exts:
            self.assertEqual(ext.validation_status, "pass")
        self.assertEqual(Extraction.objects.filter(paper=paper_2).count(), 0)

        # Validate that intermediate extractions satisfy the dynamic composite schema
        composite_schema = self.workspace.get_composite_extraction_schema()
        import jsonschema
        from research_intelligence.tasks.step_6_signal_score.scorer import extract_paper_parameters
        context_vars = extract_paper_parameters(paper_1, pipeline_run=self.pipeline_run)
        jsonschema.validate(instance=context_vars, schema=composite_schema)

        # 7. STEP 7 (Signal Score AST Calculation Contract Handoff):
        signal_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="signal_score",
            component_name="signal_scorer",
            status="pending"
        )
        signal_res = execute_signal_score_job(str(signal_comp_run.id))
        self.assertTrue(signal_res["success"])

        metric = PaperMetric.objects.filter(paper=paper_1, pipeline_run=self.pipeline_run).first()
        self.assertIsNotNone(metric)
        self.assertEqual(metric.signal_score, 8.75)

    @patch("research_intelligence.tasks.step_4_screening.abstract.get_llm_provider")
    @patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file")
    def test_abstract_screening_filters_download_handoff_and_json_contracts(
        self,
        mock_arxiv_download_file,
        mock_abstract_llm_provider,
    ):
        """
        Validates the strict data contract between Step 2 (Abstract Screening) and Step 3 (Download):
        - Abstract screening evaluates paper titles & abstracts against acceptance criteria.
        - Produces JSON output_data with screening results, reasoning, and decisions.
        - Download step inspects prior abstract screening component run and fetches PDFs ONLY
          for papers with screening_status='abstract_passed'.
        - Rejected and withdrawn papers are NEVER downloaded.
        """
        run = PipelineRun.objects.create(workspace=self.workspace, status="running")

        # 3 candidate papers
        paper_pass = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="doc_pass_001",
            title="Superconducting Qubit Topological Braiding",
            authors="Alice Qubit",
            abstract="Experimental demonstration of non-Abelian anyon braiding in superconducting circuits.",
            arxiv_id="2402.00001",
            source_database="arxiv"
        )
        paper_reject = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="doc_reject_002",
            title="Overview of Traditional Relational Database Indexing",
            authors="Bob RDBMS",
            abstract="A comprehensive study of B-Tree indices in relational databases.",
            arxiv_id="2402.00002",
            source_database="arxiv"
        )
        paper_withdrawn = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="doc_withdrawn_003",
            title="Withdrawn Quantum Study",
            authors="Charlie",
            abstract="This paper was withdrawn by the authors.",
            arxiv_id="2402.00003",
            source_database="arxiv"
        )
        PaperMetric.objects.create(paper=paper_withdrawn, pipeline_run=run, workspace=self.workspace, screening_status="withdrawn")

        # Mock Abstract Screening LLM
        mock_llm = MagicMock()
        def mock_eval(prompt, **kwargs):
            if "Topological Braiding" in prompt:
                return (
                    {
                        "passed": True,
                        "decision_category": "ACCEPT",
                        "reasoning": "Direct match for fault-tolerant quantum computing criteria.",
                        "evidence_quotes": ["demonstration of non-Abelian anyon braiding"]
                    },
                    {"prompt_tokens": 250, "candidates_tokens": 60, "total_tokens": 310}
                )
            else:
                return (
                    {
                        "passed": False,
                        "decision_category": "REJECT",
                        "reasoning": "Purely classical relational database study.",
                        "evidence_quotes": ["B-Tree indices in relational databases"]
                    },
                    {"prompt_tokens": 250, "candidates_tokens": 60, "total_tokens": 310}
                )
        mock_llm.generate.side_effect = mock_eval
        mock_abstract_llm_provider.return_value = mock_llm

        # 1. Execute Step 2 (Abstract Screening)
        screen_comp = ComponentRun.objects.create(
            pipeline_run=run,
            step_type="screening",
            component_name="abstract_screening",
            status="pending"
        )
        screen_success = execute_screening_job(str(screen_comp.id))
        self.assertTrue(screen_success)

        screen_comp.refresh_from_db()
        self.assertEqual(screen_comp.status, "completed")
        self.assertEqual(screen_comp.metrics["passed"], 1)
        self.assertEqual(screen_comp.metrics["rejected"], 1)
        self.assertEqual(screen_comp.metrics["withdrawn"], 1)

        # Verify JSON Output Contract on ComponentRun
        output_data = screen_comp.output_data
        self.assertIn("screened_papers", output_data)
        self.assertEqual(len(output_data["screened_papers"]), 3)
        screened_map = {item["paper_id"]: item for item in output_data["screened_papers"]}
        self.assertTrue(screened_map[str(paper_pass.id)]["passed"])
        self.assertEqual(screened_map[str(paper_pass.id)]["screening_status"], "abstract_passed")
        self.assertFalse(screened_map[str(paper_reject.id)]["passed"])
        self.assertEqual(screened_map[str(paper_reject.id)]["screening_status"], "rejected")

        # Verify PaperMetric status
        pm_p = PaperMetric.objects.get(paper=paper_pass, pipeline_run=run)
        pm_r = PaperMetric.objects.get(paper=paper_reject, pipeline_run=run)
        pm_w = PaperMetric.objects.get(paper=paper_withdrawn, pipeline_run=run)
        self.assertEqual(pm_p.screening_status, "abstract_passed")
        self.assertEqual(pm_r.screening_status, "rejected")
        self.assertEqual(pm_w.screening_status, "withdrawn")

        # 2. Execute Step 3 (Download)
        mock_arxiv_download_file.return_value = b"%PDF-1.4 Fake Topological Braiding PDF Content"
        download_comp = ComponentRun.objects.create(
            pipeline_run=run,
            step_type="download",
            component_name="pdf_downloader",
            status="pending"
        )
        download_success = execute_pdf_download_job(str(download_comp.id))
        self.assertTrue(download_success)

        download_comp.refresh_from_db()
        self.assertEqual(download_comp.status, "completed")
        self.assertEqual(download_comp.metrics["total_processed"], 1)
        self.assertEqual(download_comp.metrics["downloaded"], 1)

        paper_pass.refresh_from_db()
        paper_reject.refresh_from_db()
        # Verify that ONLY the passed paper was downloaded to storage
        self.assertTrue(default_storage.exists(paper_pass.original_pdf_path))
        self.assertFalse(default_storage.exists(f"workspaces/{self.workspace.id}/runs/{run.id}/documents/{paper_reject.hash_id}/original.pdf"))
        # Verify ArXiv downloader was called exactly once (for paper_pass only)
        self.assertEqual(mock_arxiv_download_file.call_count, 1)

    @patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file")
    def test_skip_abstract_screening_downloads_all_candidate_papers(
        self,
        mock_arxiv_download_file,
    ):
        """
        Validates that when abstract screening is skipped (skip_abstract_screening=True),
        DownloadNode downloads ALL ingested candidate papers (excluding withdrawn).
        """
        skip_ws = Workspace.objects.create(
            name="Skip Abstract Screening Lab",
            skip_abstract_screening=True,
            abstract_acceptance_criteria="Quantum",
            abstract_rejection_criteria="None"
        )
        run = PipelineRun.objects.create(workspace=skip_ws, status="running")

        # Ingest 3 papers
        p1 = Paper.objects.create(
            workspace=skip_ws,
            pipeline_run=run,
            hash_id="skip_doc_001",
            title="Quantum Annealing Architectures",
            arxiv_id="2403.00001",
            source_database="arxiv"
        )
        p2 = Paper.objects.create(
            workspace=skip_ws,
            pipeline_run=run,
            hash_id="skip_doc_002",
            title="Photonic Quantum Computing",
            arxiv_id="2403.00002",
            source_database="arxiv"
        )
        p3 = Paper.objects.create(
            workspace=skip_ws,
            pipeline_run=run,
            hash_id="skip_doc_003",
            title="Trapped Ion Qubits",
            arxiv_id="2403.00003",
            source_database="arxiv"
        )

        # Check that AbstractScreeningNode reports is_skippable == True
        from research_intelligence.tasks.step_4_screening.node import AbstractScreeningNode
        abs_node = AbstractScreeningNode()
        self.assertTrue(abs_node.is_skippable(run, skip_ws, {}))

        # Abstract screening is marked skipped
        ComponentRun.objects.create(
            pipeline_run=run,
            step_type="screening",
            component_name="abstract_screening",
            status="skipped"
        )

        # Execute DownloadNode
        mock_arxiv_download_file.return_value = b"%PDF-1.4 Generic Valid PDF Bytes"
        download_comp = ComponentRun.objects.create(
            pipeline_run=run,
            step_type="download",
            component_name="pdf_downloader",
            status="pending"
        )
        download_success = execute_pdf_download_job(str(download_comp.id))
        self.assertTrue(download_success)

        download_comp.refresh_from_db()
        self.assertEqual(download_comp.status, "completed")
        self.assertEqual(download_comp.metrics["total_processed"], 3)
        self.assertEqual(download_comp.metrics["downloaded"], 3)

        p1.refresh_from_db()
        p2.refresh_from_db()
        p3.refresh_from_db()
        self.assertTrue(default_storage.exists(p1.original_pdf_path))
        self.assertTrue(default_storage.exists(p2.original_pdf_path))
        self.assertTrue(default_storage.exists(p3.original_pdf_path))
        self.assertEqual(mock_arxiv_download_file.call_count, 3)

    def test_intermediate_extraction_schema_mismatch_resilience(self):
        """
        Validates intermediate data resilience when Extraction produces schema mismatches / failures:
        - Extraction.validation_status transitions to 'fail'.
        - SignalScoreNode consumer receives clean defaults (0.0) rather than raising KeyError.
        - The pipeline handoff completes successfully.
        """
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="doc_mismatch_001",
            title="Non-compliant quantum paper"
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="full_text_passed"
        )

        # 1. Simulate an extraction with schema failure (missing required exit_metric 'trl_level')
        Extraction.objects.create(
            paper=paper,
            workspace=self.workspace,
            extraction_definition=self.def_trl,
            fields_data={"hallucinated_field": 123},
            validation_status="fail",
            review_required=True
        )
        # 2. Simulate successful extraction for fit_score
        Extraction.objects.create(
            paper=paper,
            workspace=self.workspace,
            extraction_definition=self.def_fit,
            fields_data={"fit_score": 6.0},
            validation_status="pass"
        )

        # 3. Execute SignalScoreNode job
        signal_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="signal_score",
            component_name="signal_scorer",
            status="pending"
        )
        signal_res = execute_signal_score_job(str(signal_comp_run.id))
        self.assertTrue(signal_res["success"])

        # trl_level defaults to 0.0 (no KeyError). fit_score=6.0.
        # base = 0.5 * 6.0 + 0.3 * 0.0 + 0.2 * 0.0 = 3.0
        # min(3.0, 10.0) = 3.0
        pm = PaperMetric.objects.get(paper=paper, pipeline_run=self.pipeline_run)
        self.assertEqual(pm.signal_score, 3.0)
