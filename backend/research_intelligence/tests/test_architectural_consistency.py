import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from research_intelligence.models import Workspace, WorkspaceMember, PipelineRun, Paper, Extraction, ExtractionDefinition
from research_intelligence.tasks.step_2_download.fetch import download_pdf_to_s3
from research_intelligence.tasks.step_3_ocr.convert import run_ocr_conversion
from mcp_server.tools.extractions import get_paper_extractions_matrix_logic

User = get_user_model()


class ArchitecturalConsistencyTestCase(TestCase):
    """
    Validates architectural invariants and consistency guarantees:
    1. Canonical storage path resolution: Tasks always write to workspaces/{ws_id}/... and never to bare 'papers/'.
    2. Dynamic exit_metric property extraction across flat and nested fields_data payloads.
    3. Screening status alias resolution ('accepted', 'all_passed', 'all_screened') in MCP extraction matrix tool.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="arch_checker", email="arch@example.com", password="password123")
        self.workspace = Workspace.objects.create(
            name="Architecture Consistency Lab",
            ocr_provider="pypdf",
            screening_llm_model="google/gemini-3.8-flash"
        )
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            triggered_by=self.user,
            status="completed"
        )

    def test_canonical_storage_paths_for_download_and_ocr(self):
        """
        Validates that download_pdf_to_s3 and run_ocr_conversion resolve to canonical
        workspaces/{ws_id}/runs/{run_id}/documents/{hash_id}/... paths rather than legacy 'papers/'.
        """
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="canonical_hash_007",
            title="Consistent Storage Architectures in SLR Systems",
            original_pdf_path="https://arxiv.org/pdf/2401.77777.pdf",
            source_database="arxiv",
            screening_status="pending"
        )

        mock_pdf_binary = b"%PDF-1.4 Canonical PDF Stream Content"

        # 1. Test PDF download storage path resolution
        with patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file", return_value=mock_pdf_binary):
            dl_success = download_pdf_to_s3(paper.id)
            self.assertTrue(dl_success)

        paper.refresh_from_db()
        expected_pdf_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{paper.hash_id}/original.pdf"
        self.assertEqual(paper.original_pdf_path, expected_pdf_path)
        self.assertTrue(default_storage.exists(expected_pdf_path))
        self.assertFalse(paper.original_pdf_path.startswith("papers/"))

        # 2. Test OCR markdown conversion storage path resolution
        with patch("research_intelligence.ocr_providers.pypdf_provider.PyPDFOCRProvider.convert", return_value="# Structured Markdown OCR"):
            ocr_result = run_ocr_conversion(paper.id, paper_obj=paper)
            self.assertTrue(ocr_result["success"])

        paper.refresh_from_db()
        expected_ocr_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{paper.hash_id}/ocr.md"
        self.assertEqual(paper.converted_md_path, expected_ocr_path)
        self.assertTrue(default_storage.exists(expected_ocr_path))
        self.assertFalse(paper.converted_md_path.startswith("papers/"))

    def test_canonical_storage_isolation_across_multiple_runs(self):
        """
        Validates that different PipelineRuns within the same Workspace maintain
        isolated document folders without path collision or bare 'papers/' leakage.
        """
        run_2 = PipelineRun.objects.create(workspace=self.workspace, triggered_by=self.user, status="running")
        paper_run_2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run_2,
            hash_id="canonical_hash_007",  # same hash in separate run
            title="Consistent Storage in Second Run",
            original_pdf_path="https://arxiv.org/pdf/2401.77777.pdf",
            source_database="arxiv"
        )

        with patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file", return_value=b"%PDF-1.4 Data"):
            dl_success = download_pdf_to_s3(paper_run_2.id)
            self.assertTrue(dl_success)

        paper_run_2.refresh_from_db()
        expected_run_2_path = f"workspaces/{self.workspace.id}/runs/{run_2.id}/documents/{paper_run_2.hash_id}/original.pdf"
        self.assertEqual(paper_run_2.original_pdf_path, expected_run_2_path)
        self.assertTrue(default_storage.exists(expected_run_2_path))
        self.assertFalse(paper_run_2.original_pdf_path.startswith("papers/"))

    def test_dynamic_exit_metric_resolution(self):
        """
        Validates Extraction.exit_metric property extraction across:
        - Flat dictionary fields_data
        - Nested {'fields': {...}} dictionary fields_data
        - Nested {'value': ...} dictionary values
        - Fallback '-' when key is missing or undefined
        """
        definition = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Tensile Strength Target",
            exit_metric="tensile_strength_mpa",
            llm_model="google/gemini-3.8-flash",
            response_schema={"type": "object", "properties": {"tensile_strength_mpa": {"type": "number"}}}
        )

        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_metric_test",
            title="Graphene Enhanced Titanium Alloy",
            screening_status="full_text_passed"
        )

        # 1. Flat dictionary
        ext_flat = Extraction.objects.create(
            workspace=self.workspace,
            paper=paper,
            extraction_definition=definition,
            category="Mechanical Properties",
            fields_data={"tensile_strength_mpa": 1450.5, "yield_strength_mpa": 1280.0}
        )
        self.assertEqual(ext_flat.exit_metric, "1450.5")

        # 2. Nested {'fields': {...}} dictionary
        ext_nested = Extraction.objects.create(
            workspace=self.workspace,
            paper=paper,
            extraction_definition=definition,
            category="Mechanical Properties",
            fields_data={"fields": {"tensile_strength_mpa": 1600.0, "unit": "MPa"}}
        )
        self.assertEqual(ext_nested.exit_metric, "1600.0")

        # 3. Nested {'value': ...} dictionary
        ext_val_dict = Extraction.objects.create(
            workspace=self.workspace,
            paper=paper,
            extraction_definition=definition,
            category="Mechanical Properties",
            fields_data={"tensile_strength_mpa": {"value": 1820.0, "confidence": 0.95}}
        )
        self.assertEqual(ext_val_dict.exit_metric, "1820.0")

        # 4. Fallback when key is missing
        ext_missing = Extraction.objects.create(
            workspace=self.workspace,
            paper=paper,
            extraction_definition=definition,
            category="Mechanical Properties",
            fields_data={"density_g_cm3": 4.5}
        )
        self.assertEqual(ext_missing.exit_metric, "-")

    def test_screening_status_aliases_in_extraction_matrix(self):
        """
        Validates that get_paper_extractions_matrix_logic resolves:
        - 'accepted' -> captures both full_text_passed and abstract_passed papers
        - 'all_passed' -> captures both full_text_passed and abstract_passed papers
        - 'all_screened' -> captures passed + rejected papers
        """
        p_ft_passed = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="p_ft_passed",
            title="Full Text Accepted Paper",
            screening_status="full_text_passed"
        )
        p_abs_passed = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="p_abs_passed",
            title="Abstract Accepted Paper",
            screening_status="abstract_passed"
        )
        p_rejected = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="p_rejected",
            title="Rejected Paper",
            screening_status="rejected"
        )
        p_pending = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="p_pending",
            title="Pending Paper",
            screening_status="pending"
        )

        # 1. Filter: 'accepted'
        matrix_accepted = json.loads(get_paper_extractions_matrix_logic(
            user=self.user,
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id),
            screening_status="accepted"
        ))
        accepted_ids = {p["paper_id"] for p in matrix_accepted["papers"]}
        self.assertIn(str(p_ft_passed.id), accepted_ids)
        self.assertIn(str(p_abs_passed.id), accepted_ids)
        self.assertNotIn(str(p_rejected.id), accepted_ids)
        self.assertNotIn(str(p_pending.id), accepted_ids)

        # 2. Filter: 'all_passed'
        matrix_all_passed = json.loads(get_paper_extractions_matrix_logic(
            user=self.user,
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id),
            screening_status="all_passed"
        ))
        all_passed_ids = {p["paper_id"] for p in matrix_all_passed["papers"]}
        self.assertEqual(all_passed_ids, accepted_ids)

        # 3. Filter: 'all_screened'
        matrix_all_screened = json.loads(get_paper_extractions_matrix_logic(
            user=self.user,
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id),
            screening_status="all_screened"
        ))
        all_screened_ids = {p["paper_id"] for p in matrix_all_screened["papers"]}
        self.assertIn(str(p_ft_passed.id), all_screened_ids)
        self.assertIn(str(p_abs_passed.id), all_screened_ids)
        self.assertIn(str(p_rejected.id), all_screened_ids)
        self.assertNotIn(str(p_pending.id), all_screened_ids)

    def test_workspace_screening_defaults_and_custom_override_invariants(self):
        """
        Validates that Workspace model methods return well-formed defaults when fields are None/empty,
        and cleanly return custom overrides when configured.
        """
        ws_default = Workspace.objects.create(name="Default Workspace")
        
        # 1. Check default abstract screening properties
        self.assertIn("expert AI Research Scanner", ws_default.get_abstract_screening_system_prompt())
        self.assertIn("Title: {title}", ws_default.get_abstract_screening_user_prompt_template())
        default_abs_schema = ws_default.get_abstract_screening_response_schema()
        self.assertEqual(default_abs_schema["type"], "object")
        self.assertIn("passed", default_abs_schema["properties"])
        self.assertIn("decision_category", default_abs_schema["properties"])
        self.assertEqual(ws_default.get_abstract_screening_exit_metric(), "decision_category")

        # 2. Check default full-text screening properties
        self.assertIn("expert AI Research Analyst", ws_default.get_full_text_screening_system_prompt())
        self.assertIn("Full-Text Markdown Content:", ws_default.get_full_text_screening_user_prompt_template())
        default_ft_schema = ws_default.get_full_text_screening_response_schema()
        self.assertEqual(default_ft_schema["type"], "object")
        self.assertIn("passed", default_ft_schema["properties"])
        self.assertEqual(ws_default.get_full_text_screening_exit_metric(), "decision_category")

        # 3. Check custom overrides
        custom_schema = {"type": "object", "properties": {"score": {"type": "number"}}}
        ws_custom = Workspace.objects.create(
            name="Custom Workspace",
            abstract_screening_system_prompt="Custom abstract system prompt.",
            abstract_screening_user_prompt_template="Custom abstract template {title}",
            abstract_screening_response_schema=custom_schema,
            abstract_screening_exit_metric="score",
            full_text_screening_system_prompt="Custom full text system prompt.",
            full_text_screening_user_prompt_template="Custom full text template {full_text}",
            full_text_screening_response_schema=custom_schema,
            full_text_screening_exit_metric="custom_fit"
        )
        self.assertEqual(ws_custom.get_abstract_screening_system_prompt(), "Custom abstract system prompt.")
        self.assertEqual(ws_custom.get_abstract_screening_user_prompt_template(), "Custom abstract template {title}")
        self.assertEqual(ws_custom.get_abstract_screening_response_schema(), custom_schema)
        self.assertEqual(ws_custom.get_abstract_screening_exit_metric(), "score")
        self.assertEqual(ws_custom.get_full_text_screening_system_prompt(), "Custom full text system prompt.")
        self.assertEqual(ws_custom.get_full_text_screening_user_prompt_template(), "Custom full text template {full_text}")
        self.assertEqual(ws_custom.get_full_text_screening_response_schema(), custom_schema)
        self.assertEqual(ws_custom.get_full_text_screening_exit_metric(), "custom_fit")

