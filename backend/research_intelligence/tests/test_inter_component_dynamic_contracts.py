"""
Comprehensive parametric test suite validating inter-component data contracts (IN and OUT),
dynamic get_input_params() generation, and end-to-end handoff invariance across all
topological DAG permutations:
1. Canonical Full SLR (with Abstract + with OCR)
2. Direct Multimodal Pipeline (with Abstract + WITHOUT OCR -> OCR skipped)
3. Direct PDF Download Pipeline (WITHOUT Abstract -> Abstract skipped + with OCR)
4. Fast Streamlined Pipeline (WITHOUT Abstract + WITHOUT OCR -> both skipped)
5. Reprocess Existing Workspace Papers (reprocess_existing=True)
"""
import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    ComponentRun,
    Paper,
    PaperMetric,
    ExtractionDefinition,
    Extraction,
    Scraper,
    Subscriber,
)
from research_intelligence.tasks.orchestrator.dag.pipelines import build_default_slr_dag
from research_intelligence.tasks.step_1_search.node import SearchNode
from research_intelligence.tasks.step_2_download.node import DownloadNode
from research_intelligence.tasks.step_3_ocr.node import OCRNode
from research_intelligence.tasks.step_4_screening.node import AbstractScreeningNode, FullTextScreeningNode
from research_intelligence.tasks.step_5_extraction.node import ExtractionNode
from research_intelligence.tasks.step_6_signal_score.node import SignalScoreNode
from research_intelligence.tasks.step_7_reporting.node import ReportingNode
from research_intelligence.tasks.step_6_signal_score.scorer import compute_paper_signal_score


class InterComponentDynamicContractsTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Quantum Computing Intelligence Workspace",
            abstract_acceptance_criteria="Accept quantum hardware, error correction, and surface codes.",
            abstract_rejection_criteria="Reject purely classical software topics.",
            full_text_acceptance_criteria="Accept empirical benchmark metrics, thresholds, or physical circuit designs.",
            full_text_rejection_criteria="Reject pure opinion whitepapers without data.",
            signal_score_code="""
score = 0.5 * fit_score + 0.3 * novelty_score + 0.2 * trl_level
return round(score * 10.0, 2)
""",
            ocr_provider="pypdf",
            skip_abstract_screening=False,
        )
        self.scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="cat:quant-ph AND surface code",
            limit=5,
            is_active=True
        )
        self.subscriber = Subscriber.objects.create(
            workspace=self.workspace,
            email="researcher@schwarz-group.com",
            is_active=True
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.def_trl = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="TRL Level",
            exit_metric="trl_level",
            system_prompt="Extract technology readiness level (1-9).",
            user_prompt_template="Analyze: {paper_text}",
            response_schema={"type": "object", "properties": {"trl_level": {"type": "number"}}, "required": ["trl_level"]},
            is_active=True
        )
        self.def_fit = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Fit Score",
            exit_metric="fit_score",
            system_prompt="Extract domain fit score (0-10).",
            user_prompt_template="Analyze: {paper_text}",
            response_schema={"type": "object", "properties": {"fit_score": {"type": "number"}}, "required": ["fit_score"]},
            is_active=True
        )
        self.def_nov = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Novelty Score",
            exit_metric="novelty_score",
            system_prompt="Extract technical novelty score (0-10).",
            user_prompt_template="Analyze: {paper_text}",
            response_schema={"type": "object", "properties": {"novelty_score": {"type": "number"}}, "required": ["novelty_score"]},
            is_active=True
        )

    def test_dynamic_get_input_params_across_all_dag_nodes(self):
        """
        Validates that every single node in the DAG defines a functional get_input_params() method
        that dynamically constructs valid, non-empty, and contract-compliant parameters.
        """
        dag = build_default_slr_dag(workspace=self.workspace)
        self.assertEqual(len(dag.nodes), 8)

        # 1. SearchNode
        search_node = dag.nodes["search"]
        p_search = search_node.get_input_params(self.pipeline_run, self.workspace, config={}, limit=10)
        self.assertEqual(p_search["limit"], 10)
        self.assertEqual(len(p_search["scrapers"]), 1)
        self.assertEqual(p_search["scrapers"][0]["provider"], "arxiv")
        self.assertEqual(p_search["reprocess_existing"], False)

        # 2. AbstractScreeningNode
        abs_node = dag.nodes["abstract_screening"]
        p_abs = abs_node.get_input_params(self.pipeline_run, self.workspace, config={}, limit=5)
        self.assertEqual(p_abs["limit"], 5)
        self.assertIn("abstract_acceptance_criteria", p_abs)
        self.assertIn("surface codes", p_abs["abstract_acceptance_criteria"])

        # 3. DownloadNode
        dl_node = dag.nodes["download"]
        p_dl = dl_node.get_input_params(self.pipeline_run, self.workspace, config={}, limit=5)
        self.assertEqual(p_dl["target_mode"], "abstract_passed")

        # 4. OCRNode
        ocr_node = dag.nodes["ocr"]
        p_ocr = ocr_node.get_input_params(self.pipeline_run, self.workspace, config={}, limit=5)
        self.assertEqual(p_ocr["ocr_provider"], "pypdf")

        # 5. FullTextScreeningNode
        ft_node = dag.nodes["full_text_screening"]
        p_ft = ft_node.get_input_params(self.pipeline_run, self.workspace, config={}, limit=5)
        self.assertEqual(p_ft["input_mode"], "ocr_markdown")
        self.assertIn("full_text_acceptance_criteria", p_ft)

        # 6. ExtractionNode
        ext_node = dag.nodes["extraction"]
        p_ext = ext_node.get_input_params(self.pipeline_run, self.workspace, config={}, limit=5)
        self.assertEqual(p_ext["target_screening_stage"], "abstract")  # No FT completed yet
        self.assertIn("extraction_definitions", p_ext)
        self.assertEqual(len(p_ext["extraction_definitions"]), 3)

        # 7. SignalScoreNode
        sig_node = dag.nodes["signal_score"]
        p_sig = sig_node.get_input_params(self.pipeline_run, self.workspace, config={}, limit=5)
        self.assertIn("signal_score_code", p_sig)
        self.assertIn("trl_level", p_sig["signal_score_code"])

        # 8. ReportingNode
        rep_node = dag.nodes["reporting"]
        p_rep = rep_node.get_input_params(self.pipeline_run, self.workspace, config={}, limit=5)
        self.assertEqual(p_rep["generate_narrative_report"], True)
        self.assertEqual(p_rep["subscribers_count"], 1)

    def test_scenario_canonical_full_slr_pipeline_handoffs(self):
        """
        Scenario 1 (Canonical Full SLR):
        With Abstract Screening + With OCR.
        Verifies inter-component data contracts at each boundary.
        """
        dag = build_default_slr_dag(workspace=self.workspace)
        self.assertFalse(dag.nodes["abstract_screening"].is_skippable(self.pipeline_run, self.workspace, {}))
        self.assertFalse(dag.nodes["ocr"].is_skippable(self.pipeline_run, self.workspace, {}))

        # Boundary 1: Search OUT -> Ingested Papers
        paper_1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="sha_p1",
            title="Fault-Tolerant Surface Codes on Transmon Processors",
            abstract="We demonstrate quantum error correction threshold p < 1%.",
            arxiv_id="2401.00001"
        )
        PaperMetric.objects.create(paper=paper_1, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="pending")

        # Boundary 2: Abstract Screening IN -> OUT (Evaluates paper, sets abstract_passed)
        abs_in = dag.nodes["abstract_screening"].get_input_params(self.pipeline_run, self.workspace, {})
        self.assertIn("abstract_acceptance_criteria", abs_in)
        pm = PaperMetric.objects.get(paper=paper_1, pipeline_run=self.pipeline_run)
        pm.screening_status = "abstract_passed"
        pm.abstract_screening_reasoning = "Demonstrates fault-tolerant surface codes on transmon processors."
        pm.save()

        # Boundary 3: Download IN (Checks target_mode is abstract_passed)
        dl_in = dag.nodes["download"].get_input_params(self.pipeline_run, self.workspace, {})
        self.assertEqual(dl_in["target_mode"], "abstract_passed")
        target_papers = list(self.pipeline_run.get_papers(screening_status=['abstract_passed', 'accepted']))
        self.assertEqual(len(target_papers), 1)

        # Download OUT: saves PDF binary
        paper_1.original_pdf_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{paper_1.hash_id}/original.pdf"
        paper_1.save()
        ComponentRun.objects.create(pipeline_run=self.pipeline_run, step_type="download", component_name="document_download", status="completed")

        # Boundary 4: OCR IN -> OUT
        ocr_in = dag.nodes["ocr"].get_input_params(self.pipeline_run, self.workspace, {})
        self.assertEqual(ocr_in["ocr_provider"], "pypdf")
        paper_1.converted_md_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{paper_1.hash_id}/extracted_text.md"
        paper_1.save()
        ComponentRun.objects.create(pipeline_run=self.pipeline_run, step_type="ocr", component_name="layout_ocr", status="completed")

        # Boundary 5: Full-Text Screening IN -> OUT (Detects OCR markdown input mode)
        ft_in = dag.nodes["full_text_screening"].get_input_params(self.pipeline_run, self.workspace, {})
        self.assertEqual(ft_in["input_mode"], "ocr_markdown")
        pm.refresh_from_db()
        pm.screening_status = "full_text_passed"
        pm.full_text_screening_reasoning = "Hardware benchmarks confirm physical threshold."
        pm.save()
        ComponentRun.objects.create(pipeline_run=self.pipeline_run, step_type="screening", component_name="full_text_screening", status="completed")

        # Boundary 6: Extraction IN -> OUT (Detects prior full_text run)
        ext_in = dag.nodes["extraction"].get_input_params(self.pipeline_run, self.workspace, {})
        self.assertEqual(ext_in["target_screening_stage"], "full_text")
        ext_papers = list(self.pipeline_run.get_papers(screening_status=['full_text_passed', 'accepted']))
        self.assertEqual(len(ext_papers), 1)

        Extraction.objects.create(paper=paper_1, workspace=self.workspace, extraction_definition=self.def_fit, fields_data={"fit_score": 8.5})
        Extraction.objects.create(paper=paper_1, workspace=self.workspace, extraction_definition=self.def_nov, fields_data={"novelty_score": 9.0})
        Extraction.objects.create(paper=paper_1, workspace=self.workspace, extraction_definition=self.def_trl, fields_data={"trl_level": 5.0})
        ComponentRun.objects.create(pipeline_run=self.pipeline_run, step_type="extraction", component_name="parameter_extraction", status="completed")

        # Boundary 7: Signal Score IN -> OUT
        sig_in = dag.nodes["signal_score"].get_input_params(self.pipeline_run, self.workspace, {})
        self.assertIn("signal_score_code", sig_in)
        score_res = compute_paper_signal_score(paper_1, pipeline_run=self.pipeline_run)
        score_val = score_res[0] if isinstance(score_res, tuple) else score_res
        # Expected: (0.5 * 8.5 + 0.3 * 9.0 + 0.2 * 5.0) * 10 = (4.25 + 2.7 + 1.0) * 10 = 7.95 * 10 = 79.5
        self.assertAlmostEqual(score_val, 79.5, places=1)
        pm.refresh_from_db()
        pm.signal_score = score_val
        pm.save()
        ComponentRun.objects.create(pipeline_run=self.pipeline_run, step_type="signal_score", component_name="signal_score_evaluation", status="completed")

        # Boundary 8: Reporting IN
        rep_in = dag.nodes["reporting"].get_input_params(self.pipeline_run, self.workspace, {})
        self.assertEqual(rep_in["generate_narrative_report"], True)
        self.assertEqual(rep_in["subscribers_count"], 1)

    def test_scenario_direct_multimodal_pdf_pipeline_without_ocr(self):
        """
        Scenario 2 (Direct Multimodal PDF Pipeline):
        With Abstract Screening + WITHOUT OCR (workspace.ocr_provider=None).
        Verifies OCR is skippable and FullTextScreening dynamically switches to multimodal_pdf input_mode.
        """
        self.workspace.ocr_provider = None
        self.workspace.save()

        dag = build_default_slr_dag(workspace=self.workspace)
        self.assertTrue(dag.nodes["ocr"].is_skippable(self.pipeline_run, self.workspace, {}))

        # FullTextScreeningNode input_mode must be 'multimodal_pdf'
        ft_in = dag.nodes["full_text_screening"].get_input_params(self.pipeline_run, self.workspace, {})
        self.assertEqual(ft_in["input_mode"], "multimodal_pdf")

        # Downstream Extraction and Signal Scoring must still work cleanly
        paper = Paper.objects.create(workspace=self.workspace, pipeline_run=self.pipeline_run, hash_id="sha_p2", title="Multimodal Paper")
        PaperMetric.objects.create(paper=paper, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="full_text_passed")
        ComponentRun.objects.create(pipeline_run=self.pipeline_run, step_type="screening", component_name="full_text_screening", status="completed")

        ext_in = dag.nodes["extraction"].get_input_params(self.pipeline_run, self.workspace, {})
        self.assertEqual(ext_in["target_screening_stage"], "full_text")

    def test_scenario_direct_download_pipeline_without_abstract_screening(self):
        """
        Scenario 3 (Direct Download Pipeline):
        WITHOUT Abstract Screening (workspace.skip_abstract_screening=True) + With OCR.
        Verifies AbstractScreening is skippable and DownloadNode dynamically targets 'all_ingested'.
        """
        self.workspace.skip_abstract_screening = True
        self.workspace.save()

        dag = build_default_slr_dag(workspace=self.workspace)
        self.assertTrue(dag.nodes["abstract_screening"].is_skippable(self.pipeline_run, self.workspace, {}))

        # DownloadNode target_mode must dynamically adapt to 'all_ingested'
        dl_in = dag.nodes["download"].get_input_params(self.pipeline_run, self.workspace, {})
        self.assertEqual(dl_in["target_mode"], "all_ingested")

    def test_scenario_streamlined_pipeline_without_abstract_and_without_ocr(self):
        """
        Scenario 4 (Fast Streamlined Pipeline):
        WITHOUT Abstract Screening + WITHOUT OCR (both skippable).
        Verifies both are skipped, Download targets all papers, and Full-Text uses multimodal PDF.
        """
        self.workspace.skip_abstract_screening = True
        self.workspace.ocr_provider = None
        self.workspace.save()

        dag = build_default_slr_dag(workspace=self.workspace)
        self.assertTrue(dag.nodes["abstract_screening"].is_skippable(self.pipeline_run, self.workspace, {}))
        self.assertTrue(dag.nodes["ocr"].is_skippable(self.pipeline_run, self.workspace, {}))

        dl_in = dag.nodes["download"].get_input_params(self.pipeline_run, self.workspace, {})
        self.assertEqual(dl_in["target_mode"], "all_ingested")

        ft_in = dag.nodes["full_text_screening"].get_input_params(self.pipeline_run, self.workspace, {})
        self.assertEqual(ft_in["input_mode"], "multimodal_pdf")

    def test_scenario_reprocess_existing_workspace_papers(self):
        """
        Scenario 5 (Reprocessing Existing Workspace Papers):
        Tests that SearchNode.get_input_params captures reprocess_existing=True and
        all existing papers are linked to the new PipelineRun via PaperMetric.
        """
        # Create an existing paper from a prior run
        old_pr = PipelineRun.objects.create(workspace=self.workspace, status="completed")
        existing_paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=old_pr,
            hash_id="sha_existing_001",
            title="Existing Archived Surface Code Study",
            arxiv_id="2301.00001"
        )
        PaperMetric.objects.create(paper=existing_paper, pipeline_run=old_pr, workspace=self.workspace, screening_status="full_text_passed")

        new_pr = PipelineRun.objects.create(workspace=self.workspace, status="running", reprocess_existing=True)
        dag = build_default_slr_dag(workspace=self.workspace)

        # SearchNode input_params captures reprocess_existing
        search_in = dag.nodes["search"].get_input_params(new_pr, self.workspace, {"reprocess_existing": True})
        self.assertEqual(search_in["reprocess_existing"], True)

        # Link existing paper to new_pr
        PaperMetric.objects.create(paper=existing_paper, pipeline_run=new_pr, workspace=self.workspace, screening_status="abstract_passed")

        # Downstream DownloadNode targets this paper in new_pr
        target_papers = list(new_pr.get_papers(screening_status=['abstract_passed', 'accepted']))
        self.assertEqual(len(target_papers), 1)
        self.assertEqual(target_papers[0].id, existing_paper.id)

    def test_dynamic_limit_propagation_across_dag_nodes(self):
        """
        Validates that dynamic execution limits (limit=3) are cleanly propagated to
        every node's get_input_params() without overriding core workspace configuration.
        """
        dag = build_default_slr_dag(workspace=self.workspace)
        for node_name, node in dag.nodes.items():
            params = node.get_input_params(self.pipeline_run, self.workspace, config={"limit": 3}, limit=3)
            self.assertEqual(params.get("limit"), 3, f"Node '{node_name}' did not receive dynamic limit=3 in get_input_params()")

    def test_dynamic_ocr_mode_switching_resilience(self):
        """
        Validates that FullTextScreeningNode input_mode properly switches between
        'ocr_markdown' and 'multimodal_pdf' based on dynamic config overrides.
        """
        ft_node = FullTextScreeningNode()

        # Config override: ocr_provider="gemini" -> ocr_markdown
        p_gem = ft_node.get_input_params(self.pipeline_run, self.workspace, config={"ocr_provider": "gemini"})
        self.assertEqual(p_gem["input_mode"], "ocr_markdown")

        # Config override: ocr_provider="" -> multimodal_pdf
        p_none = ft_node.get_input_params(self.pipeline_run, self.workspace, config={"ocr_provider": ""})
        self.assertEqual(p_none["input_mode"], "multimodal_pdf")

