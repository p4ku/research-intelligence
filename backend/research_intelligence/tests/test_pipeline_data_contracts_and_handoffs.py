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
            status="running"
        )

        # Create extraction definitions with valid schema
        self.def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
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

        # 2. STEP 2 (Download Contract Handoff):
        download_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="download",
            component_name="pdf_downloader",
            status="pending"
        )
        mock_arxiv_download_file.return_value = b"%PDF-1.4 Fake Quantum Document Binary Stream with Surface Code"

        download_res = execute_pdf_download_job(str(download_comp_run.id))
        self.assertTrue(download_res)

        # 3. STEP 3 (OCR Skippable Check):
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

        # 4. STEP 4 (Dual-Stage Screening Contract Handoff):
        abstract_llm = MagicMock()
        def mock_abstract_eval(prompt, **kwargs):
            if "Fault-Tolerant Surface Code" in prompt:
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

        screening_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="abstract_screening",
            status="pending"
        )
        abstract_res = execute_screening_job(str(screening_comp_run.id))
        self.assertTrue(abstract_res)

        paper_1.refresh_from_db()
        paper_2.refresh_from_db()
        self.assertEqual(paper_1.screening_status, "abstract_passed")
        self.assertEqual(paper_2.screening_status, "rejected")

        # Stage B: Full-Text Multimodal Screening
        fulltext_llm = MagicMock()
        fulltext_llm.generate.return_value = (
            {"passed": True, "decision_category": "FULL_TEXT_PASSED", "reasoning": "Empirical threshold proofs included."},
            {"prompt_tokens": 1200, "candidates_tokens": 120, "total_tokens": 1320}
        )
        mock_fulltext_llm_provider.return_value = fulltext_llm

        fulltext_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="full_text_screening",
            status="pending"
        )
        with patch("django.core.files.storage.default_storage.exists", return_value=True), \
             patch("django.core.files.storage.default_storage.open", return_value=MagicMock(read=lambda: b"%PDF-1.4 Fake PDF")):
            paper_1.original_pdf_path = "workspaces/fake/original.pdf"
            paper_1.save(update_fields=['original_pdf_path'])
            fulltext_res = execute_full_text_screening_job(str(fulltext_comp_run.id))
            self.assertTrue(fulltext_res)

        paper_1.refresh_from_db()
        self.assertEqual(paper_1.screening_status, "full_text_passed")

        # 5. STEP 5 (Dynamic Extraction Contract Handoff):
        extraction_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="extraction",
            component_name="dynamic_extractor",
            status="pending"
        )
        extraction_llm = MagicMock()
        def mock_extract(prompt, **kwargs):
            if "TRL Level" in prompt:
                return (
                    {"trl_level": 7, "reasoning": "Demonstrated 100-qubit processor.", "confidence_score": 0.95, "evidence_quote": "Demonstrated operational stability."},
                    {"prompt_tokens": 500, "candidates_tokens": 100, "total_tokens": 600}
                )
            elif "Fit Score" in prompt:
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

        extraction_res = execute_extraction_job(str(extraction_comp_run.id))
        self.assertTrue(extraction_res)

        # Verify database extractions
        exts = Extraction.objects.filter(paper=paper_1)
        self.assertEqual(exts.count(), 3)
        self.assertEqual(Extraction.objects.filter(paper=paper_2).count(), 0)

        # 6. STEP 6 (Signal Score AST Calculation Contract Handoff):
        signal_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="signal_score",
            component_name="signal_scorer",
            status="pending"
        )
        mock_calc_signal_score.return_value = (8.75, {"score": 8.75})

        signal_res = execute_signal_score_job(str(signal_comp_run.id))
        self.assertTrue(signal_res["success"])

        paper_1.refresh_from_db()
        self.assertEqual(paper_1.signal_score, 8.75)

        metric = PaperMetric.objects.filter(paper=paper_1, pipeline_run=self.pipeline_run).first()
        self.assertIsNotNone(metric)
        self.assertEqual(metric.signal_score, 8.75)
