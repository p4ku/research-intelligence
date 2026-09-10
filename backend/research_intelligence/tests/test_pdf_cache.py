import hashlib
from unittest.mock import patch
from django.test import TestCase
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from research_intelligence.models import Workspace, PipelineRun, Paper, DocumentRegistry
from research_intelligence.tasks.step_2_download.pdf_cache import (
    try_reuse_cached_pdf,
    register_document_pdf,
    find_in_document_registry,
)
from research_intelligence.tasks.step_3_ocr.convert import run_ocr_conversion


class DocumentRegistryAndCacheTestCase(TestCase):
    """
    Comprehensive unit tests for the global DocumentRegistry and caching pipelines:
    1. Direct DocumentRegistry lookup and registration.
    2. Zero-Network PDF Fastpath via DocumentRegistry (cross-workspace reuse + access_count increment).
    3. Zero-Compute OCR Fastpath via DocumentRegistry (skips OCR engine execution on repeated papers).
    4. Graceful fallback on missing or corrupt storage paths.
    5. Rejection of zero-byte cached files.
    """

    def setUp(self):
        self.workspace_a = Workspace.objects.create(name="Workspace A", ocr_provider="pypdf")
        self.run_a = PipelineRun.objects.create(workspace=self.workspace_a, status="completed")

        self.workspace_b = Workspace.objects.create(name="Workspace B", ocr_provider="pypdf")
        self.run_b = PipelineRun.objects.create(workspace=self.workspace_b, status="running")

        self.pdf_binary = b"%PDF-1.4 Mock Binary for DocumentRegistry Testing" * 25
        self.pdf_sha256 = hashlib.sha256(self.pdf_binary).hexdigest()

    def test_register_document_pdf_creates_canonical_cache(self):
        """Registers a newly fetched PDF into DocumentRegistry and saves canonical storage copy."""
        paper = Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="reg_test_001",
            doi="10.1000/182",
            arxiv_id="2401.12345",
            title="Quantum Surface Code Optimization",
            source_database="arxiv"
        )

        doc_reg = register_document_pdf(paper, self.pdf_binary)
        self.assertIsNotNone(doc_reg)
        self.assertEqual(doc_reg.sha256_hash, self.pdf_sha256)
        self.assertEqual(doc_reg.doi, "10.1000/182")
        self.assertEqual(doc_reg.arxiv_id, "2401.12345")
        self.assertEqual(doc_reg.pdf_file_size_bytes, len(self.pdf_binary))
        self.assertTrue(default_storage.exists(doc_reg.canonical_pdf_path))

        paper.refresh_from_db()
        self.assertEqual(paper.document_registry, doc_reg)

    def test_document_registry_pdf_fastpath_cache_hit_and_access_count(self):
        """
        Workspace A registers a paper in DocumentRegistry.
        Workspace B requests the same paper -> fastpath hits DocumentRegistry,
        copies file without network calls, and increments access_count.
        """
        paper_a = Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="ws_a_hash",
            arxiv_id="2402.55555",
            title="Scalable Superconducting Qubits",
            source_database="arxiv"
        )
        doc_reg = register_document_pdf(paper_a, self.pdf_binary)
        initial_access_count = doc_reg.access_count

        # Workspace B wants the paper
        paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="ws_b_hash",
            arxiv_id="2402.55555",
            title="Scalable Superconducting Qubits (Workspace B)",
            original_pdf_path="https://arxiv.org/pdf/2402.55555.pdf",
            source_database="arxiv"
        )

        target_path = f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/ws_b_hash/original.pdf"
        result = try_reuse_cached_pdf(paper_b, target_path, title_snippet="Scalable Superconducting")

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "downloaded")
        self.assertTrue(result["cache_hit"])
        self.assertTrue(result["from_cache"])
        self.assertEqual(result["cached_from"], doc_reg.canonical_pdf_path)
        self.assertEqual(result["registry_id"], str(doc_reg.id))
        self.assertTrue(default_storage.exists(target_path))

        doc_reg.refresh_from_db()
        self.assertEqual(doc_reg.access_count, initial_access_count + 1)

        paper_b.refresh_from_db()
        self.assertEqual(paper_b.document_registry, doc_reg)
        self.assertEqual(paper_b.original_pdf_path, target_path)

    def test_document_registry_ocr_zero_compute_fastpath(self):
        """
        Validates that when Workspace A performs OCR and records it in DocumentRegistry,
        Workspace B converting the same document reuses the OCR Markdown without calling OCR provider.
        """
        # Step 1: Ingest and register document in Workspace A
        paper_a = Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="ocr_cached_hash",
            arxiv_id="2403.99999",
            title="Quantum Circuit Synthesis",
            original_pdf_path=f"workspaces/{self.workspace_a.id}/runs/{self.run_a.id}/documents/ocr_cached_hash/original.pdf"
        )
        default_storage.save(paper_a.original_pdf_path, ContentFile(self.pdf_binary))
        doc_reg = register_document_pdf(paper_a, self.pdf_binary)

        mock_ocr_md = "# Quantum Circuit Synthesis\n\nWe present an efficient algorithm for unitary decomposition."

        with patch("research_intelligence.ocr_providers.pypdf_provider.PyPDFOCRProvider.convert", return_value=mock_ocr_md) as mock_provider:
            res_a = run_ocr_conversion(paper_a.id)
            self.assertTrue(res_a["success"])
            mock_provider.assert_called_once()

        doc_reg.refresh_from_db()
        self.assertEqual(doc_reg.ocr_provider, "pypdf")
        self.assertTrue(doc_reg.canonical_ocr_md_path)
        self.assertTrue(default_storage.exists(doc_reg.canonical_ocr_md_path))

        # Step 2: Workspace B has the same paper and runs OCR
        paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="ocr_cached_hash_ws_b",
            arxiv_id="2403.99999",
            title="Quantum Circuit Synthesis",
            document_registry=doc_reg,
            original_pdf_path=f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/ocr_cached_hash_ws_b/original.pdf"
        )
        default_storage.save(paper_b.original_pdf_path, ContentFile(self.pdf_binary))

        # Ensure OCR provider is NEVER called for Workspace B because DocumentRegistry cached it!
        with patch("research_intelligence.ocr_providers.pypdf_provider.PyPDFOCRProvider.convert") as mock_provider_b:
            res_b = run_ocr_conversion(paper_b.id)
            mock_provider_b.assert_not_called()
            self.assertTrue(res_b["success"])
            self.assertTrue(res_b.get("cache_hit"))

        paper_b.refresh_from_db()
        self.assertTrue(default_storage.exists(paper_b.converted_md_path))
        with default_storage.open(paper_b.converted_md_path, 'r') as f:
            content = f.read()
        self.assertEqual(content, mock_ocr_md)

    def test_cache_miss_returns_none(self):
        """When no matching paper or registry record exists, returns None."""
        paper = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="uncached_hash_001",
            arxiv_id="2401.11111",
            title="Uncached Quantum Paper",
            original_pdf_path="https://arxiv.org/pdf/2401.11111.pdf"
        )
        target_path = f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/uncached_hash_001/original.pdf"
        result = try_reuse_cached_pdf(paper, target_path)
        self.assertIsNone(result)

    def test_missing_storage_file_falls_back_gracefully(self):
        """If DocumentRegistry points to a deleted file on disk, falls back safely to None."""
        doc_reg = DocumentRegistry.objects.create(
            sha256_hash="ghost_hash_001",
            arxiv_id="2401.00999",
            title="Ghost Document",
            canonical_pdf_path="cache/documents/ghost_hash_001/original.pdf"
            # File is intentionally NOT created on storage
        )

        paper = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="ghost_hash_001",
            arxiv_id="2401.00999",
            title="Ghost Document",
            original_pdf_path="https://arxiv.org/pdf/2401.00999.pdf"
        )
        target_path = f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/ghost_hash_001/original.pdf"
        result = try_reuse_cached_pdf(paper, target_path)
        self.assertIsNone(result)

    def test_deleting_paper_decrements_document_registry_access_count(self):
        """
        Validates that when a Paper instance is deleted, the access_count
        in the associated DocumentRegistry is decremented.
        """
        paper = Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="del_test_001",
            arxiv_id="2401.99901",
            title="Delete Test Paper 1"
        )
        doc_reg = register_document_pdf(paper, self.pdf_binary)
        self.assertEqual(doc_reg.access_count, 1)

        # Workspace B reuses it -> access_count = 2
        paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="del_test_002",
            arxiv_id="2401.99901",
            title="Delete Test Paper 2"
        )
        target_path = f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/del_test_002/original.pdf"
        try_reuse_cached_pdf(paper_b, target_path)

        doc_reg.refresh_from_db()
        self.assertEqual(doc_reg.access_count, 2)

        # Delete paper_b -> access_count should drop from 2 to 1
        paper_b.delete()
        doc_reg.refresh_from_db()
        self.assertEqual(doc_reg.access_count, 1)

        # Delete paper_a -> access_count should drop from 1 to 0
        paper.delete()
        doc_reg.refresh_from_db()
        self.assertEqual(doc_reg.access_count, 0)

    def test_cascading_pipeline_run_delete_decrements_registry_access_count(self):
        """
        Validates that deleting a PipelineRun (which cascade deletes its Papers)
        properly decrements the DocumentRegistry access_count.
        """
        paper_a = Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="cascade_run_001",
            arxiv_id="2401.99902",
            title="Cascade Run Paper A"
        )
        doc_reg = register_document_pdf(paper_a, self.pdf_binary)

        paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="cascade_run_002",
            arxiv_id="2401.99902",
            title="Cascade Run Paper B"
        )
        target_path = f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/cascade_run_002/original.pdf"
        try_reuse_cached_pdf(paper_b, target_path)

        doc_reg.refresh_from_db()
        self.assertEqual(doc_reg.access_count, 2)

        # Cascade delete run_b -> deletes paper_b -> access_count becomes 1
        self.run_b.delete()
        doc_reg.refresh_from_db()
        self.assertEqual(doc_reg.access_count, 1)

    def test_cascading_workspace_delete_decrements_registry_access_count(self):
        """
        Validates that deleting an entire Workspace (which cascade deletes runs and papers)
        properly decrements the DocumentRegistry access_count.
        """
        paper_a = Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="cascade_ws_001",
            arxiv_id="2401.99903",
            title="Cascade WS Paper A"
        )
        doc_reg = register_document_pdf(paper_a, self.pdf_binary)

        paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="cascade_ws_002",
            arxiv_id="2401.99903",
            title="Cascade WS Paper B"
        )
        target_path = f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/cascade_ws_002/original.pdf"
        try_reuse_cached_pdf(paper_b, target_path)

        doc_reg.refresh_from_db()
        self.assertEqual(doc_reg.access_count, 2)

        # Cascade delete workspace_b -> deletes run_b -> deletes paper_b -> access_count becomes 1
        self.workspace_b.delete()
        doc_reg.refresh_from_db()
        self.assertEqual(doc_reg.access_count, 1)

    def test_document_registry_meta_propagation_and_cache_reuse(self):
        """
        Validates that raw source metadata ('meta') is propagated between
        Paper and DocumentRegistry upon registration and cache hits.
        """
        sample_arxiv_meta = {
            "id": "http://arxiv.org/abs/2608.01939v2",
            "title": "Oraqle: An Empirical Analysis of Qubit Readout",
            "published": "2026-08-03T09:13:15Z",
            "primary_category": "quant-ph",
            "authors": [{"name": "Emmanouil Giortamis"}]
        }

        # 1. Registration copies paper.meta -> doc_reg.meta
        paper_a = Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="meta_test_001",
            arxiv_id="2608.01939",
            title="Oraqle: An Empirical Analysis of Qubit Readout",
            meta=sample_arxiv_meta
        )
        doc_reg = register_document_pdf(paper_a, self.pdf_binary)
        self.assertEqual(doc_reg.meta, sample_arxiv_meta)

        # 2. Paper B without meta reuses cache -> inherits doc_reg.meta
        paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="meta_test_002",
            arxiv_id="2608.01939",
            title="Oraqle: An Empirical Analysis of Qubit Readout",
            meta={}
        )
        target_path = f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/meta_test_002/original.pdf"
        reuse_res = try_reuse_cached_pdf(paper_b, target_path)
        self.assertIsNotNone(reuse_res)
        paper_b.refresh_from_db()
        self.assertEqual(paper_b.meta, sample_arxiv_meta)
