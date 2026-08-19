from unittest.mock import patch
from django.test import TestCase
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from research_intelligence.models import Workspace, PipelineRun, Paper
from research_intelligence.tasks.step_2_download.pdf_cache import try_reuse_cached_pdf


class PDFCacheTestCase(TestCase):
    """
    Comprehensive unit tests for the PDF Cache Reuse utility (step_2_download/pdf_cache.py):
    1. Cache Miss (no prior records).
    2. Cache Hit via DOI matching.
    3. Cache Hit via arXiv ID matching.
    4. Cache Hit via SHA-256 hash_id matching.
    5. Graceful fallback on deleted storage files or corrupted paths.
    6. Rejection of zero-byte cached files.
    """

    def setUp(self):
        self.workspace_a = Workspace.objects.create(name="Workspace A")
        self.run_a = PipelineRun.objects.create(workspace=self.workspace_a, status="completed")

        self.workspace_b = Workspace.objects.create(name="Workspace B")
        self.run_b = PipelineRun.objects.create(workspace=self.workspace_b, status="running")

        self.pdf_binary = b"%PDF-1.4 Mock Binary for Quantum Cache Testing" * 30

    def test_cache_miss_returns_none(self):
        """When no matching paper exists in DB, returns None."""
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

    def test_cache_hit_via_doi(self):
        """Matches cached document via normalized DOI across different workspaces."""
        stored_path = f"workspaces/{self.workspace_a.id}/runs/{self.run_a.id}/documents/doc_doi_001/original.pdf"
        default_storage.save(stored_path, ContentFile(self.pdf_binary))

        Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="doc_doi_001",
            doi="10.1038/s41586-024-00001-x",
            title="Nature Quantum Supremacy",
            original_pdf_path=stored_path
        )

        paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="doc_doi_002_diff_hash",
            doi="10.1038/s41586-024-00001-x",
            title="Nature Quantum Supremacy (Ingested by Workspace B)",
            original_pdf_path="https://nature.com/articles/s41586-024-00001-x.pdf"
        )

        target_path = f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/doc_doi_002_diff_hash/original.pdf"
        result = try_reuse_cached_pdf(paper_b, target_path, title_snippet="Nature Quantum")

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "downloaded")
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["cached_from"], stored_path)
        self.assertEqual(result["storage_path"], target_path)
        self.assertTrue(default_storage.exists(target_path))

        paper_b.refresh_from_db()
        self.assertEqual(paper_b.original_pdf_path, target_path)

    def test_cache_hit_via_arxiv_id(self):
        """Matches cached document via arXiv ID across runs."""
        stored_path = f"workspaces/{self.workspace_a.id}/runs/{self.run_a.id}/documents/arxiv_doc_01/original.pdf"
        default_storage.save(stored_path, ContentFile(self.pdf_binary))

        Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="arxiv_doc_01",
            arxiv_id="2401.77777",
            title="QEC Surface Codes",
            original_pdf_path=stored_path
        )

        paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="arxiv_doc_ws_b",
            arxiv_id="2401.77777",
            title="QEC Surface Codes (Workspace B)",
            original_pdf_path="https://arxiv.org/pdf/2401.77777.pdf"
        )

        target_path = f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/arxiv_doc_ws_b/original.pdf"
        result = try_reuse_cached_pdf(paper_b, target_path)

        self.assertIsNotNone(result)
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["size_bytes"], len(self.pdf_binary))

    def test_cache_hit_via_hash_or_cross_reference(self):
        """Matches cached document via cross-reference query when hash/arxiv/doi match."""
        stored_path = f"workspaces/{self.workspace_a.id}/runs/{self.run_a.id}/documents/hash_match_001/original.pdf"
        default_storage.save(stored_path, ContentFile(self.pdf_binary))

        Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="hash_match_001",
            doi="10.1103/PhysRevA.100.012345",
            arxiv_id="2401.55555",
            title="Identical Quantum Paper",
            original_pdf_path=stored_path
        )

        paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="hash_match_ws_b",
            doi="10.1103/PhysRevA.100.012345",
            title="Identical Quantum Paper (Workspace B)",
            original_pdf_path="https://journals.aps.org/pra/pdf/10.1103/PhysRevA.100.012345"
        )

        target_path = f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/hash_match_ws_b/original.pdf"
        result = try_reuse_cached_pdf(paper_b, target_path)
        self.assertIsNotNone(result)
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["cached_from"], stored_path)
        self.assertEqual(result["size_bytes"], len(self.pdf_binary))

    def test_missing_storage_file_falls_back_gracefully_to_none(self):
        """If Paper DB row points to a file that was deleted from disk, returns None."""
        ghost_path = f"workspaces/{self.workspace_a.id}/runs/{self.run_a.id}/documents/ghost_doc/original.pdf"
        # Notice: we do NOT call default_storage.save, so default_storage.exists(ghost_path) is False

        Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="ghost_doc",
            arxiv_id="2401.99000",
            title="Ghost Document",
            original_pdf_path=ghost_path
        )

        paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="ghost_doc_b",
            arxiv_id="2401.99000",
            title="Ghost Document (WS B)",
            original_pdf_path="https://arxiv.org/pdf/2401.99000.pdf"
        )

        target_path = f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/ghost_doc_b/original.pdf"
        result = try_reuse_cached_pdf(paper_b, target_path)
        self.assertIsNone(result)

    def test_zero_byte_cached_file_rejected(self):
        """If cached storage file is 0 bytes, rejects it and returns None."""
        empty_path = f"workspaces/{self.workspace_a.id}/runs/{self.run_a.id}/documents/empty_doc/original.pdf"
        default_storage.save(empty_path, ContentFile(b""))

        Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="empty_doc",
            arxiv_id="2401.00000",
            title="Empty Document",
            original_pdf_path=empty_path
        )

        paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="empty_doc_b",
            arxiv_id="2401.00000",
            title="Empty Document (WS B)",
            original_pdf_path="https://arxiv.org/pdf/2401.00000.pdf"
        )

        target_path = f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/empty_doc_b/original.pdf"
        result = try_reuse_cached_pdf(paper_b, target_path)
        self.assertIsNone(result)
