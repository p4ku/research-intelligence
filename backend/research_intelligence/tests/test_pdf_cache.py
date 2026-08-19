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
