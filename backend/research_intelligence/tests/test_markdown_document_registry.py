import hashlib
import importlib
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.urls import reverse
from django.apps import apps

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    Paper,
    PaperMetric,
    DocumentRegistry,
)
from research_intelligence.tasks.step_2_download.pdf_cache import (
    register_document_markdown,
    try_reuse_cached_markdown,
    find_in_document_registry,
    register_document_pdf,
)
from research_intelligence.tasks.step_2_download.fetch import _download_paper_task
from research_intelligence.tasks.step_3_ocr.convert import run_ocr_conversion
from research_intelligence.admin import PaperAdmin, DocumentRegistryAdmin

User = get_user_model()


class MarkdownDocumentRegistryCoreTests(TestCase):
    """
    Unit tests for core DocumentRegistry registration, lookup, and zero-network
    cache reuse of full-text Markdown documents (e.g. Google Patents without PDF scans).
    """

    def setUp(self):
        self.workspace_a = Workspace.objects.create(name="Workspace Quantum A")
        self.run_a = PipelineRun.objects.create(workspace=self.workspace_a, status="completed")

        self.workspace_b = Workspace.objects.create(name="Workspace Quantum B")
        self.run_b = PipelineRun.objects.create(workspace=self.workspace_b, status="running")

        self.sample_md = (
            b"# US11888999B2: Superconducting Quantum Processor Calibration\n\n"
            b"## Abstract\nA method for automated flux bias point optimization in tunable qubits.\n\n"
            b"## Claims\n1. A calibration system comprising a cryogenic microwave controller..."
        )
        self.sample_md_hash = hashlib.sha256(self.sample_md).hexdigest()

    def test_register_document_markdown_basic_attributes(self):
        """Validates that a newly fetched Markdown document creates a canonical cache and DocumentRegistry entry."""
        paper = Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="patent_test_001",
            title="Superconducting Quantum Processor Calibration",
            source_url="https://patents.google.com/patent/US11888999B2/en",
            source_database="google_patents",
            meta={"patent_id": "US11888999B2", "assignee": "Quantum Corp"}
        )

        doc_reg = register_document_markdown(
            paper=paper,
            file_bytes=self.sample_md,
            ocr_provider="google_patents_html"
        )

        self.assertIsNotNone(doc_reg)
        self.assertEqual(doc_reg.sha256_hash, self.sample_md_hash)
        self.assertEqual(doc_reg.title, "Superconducting Quantum Processor Calibration")
        self.assertEqual(doc_reg.source_url, "https://patents.google.com/patent/US11888999B2/en")
        self.assertEqual(doc_reg.primary_source, "google_patents")
        self.assertEqual(doc_reg.ocr_provider, "google_patents_html")
        self.assertEqual(doc_reg.canonical_ocr_md_path, f"cache/documents/{self.sample_md_hash}/document.md")
        self.assertEqual(doc_reg.pdf_file_size_bytes, 0)
        self.assertEqual(doc_reg.access_count, 1)
        self.assertEqual(doc_reg.meta.get("patent_id"), "US11888999B2")

        # Canonical storage file exists and matches original bytes
        self.assertTrue(default_storage.exists(doc_reg.canonical_ocr_md_path))
        with default_storage.open(doc_reg.canonical_ocr_md_path, 'rb') as f:
            stored_bytes = f.read()
        self.assertEqual(stored_bytes, self.sample_md)

        # Paper relation is updated
        paper.refresh_from_db()
        self.assertEqual(paper.document_registry, doc_reg)

    def test_register_document_markdown_deduplication_same_hash(self):
        """Registering two papers with identical markdown bytes reuses the single DocumentRegistry record and increments access_count."""
        paper_1 = Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="patent_hash_p1",
            title="Patent 1",
            source_url="https://patents.google.com/patent/US11888999B2/en",
            source_database="google_patents"
        )
        doc_reg_1 = register_document_markdown(paper_1, self.sample_md)
        self.assertEqual(doc_reg_1.access_count, 1)

        paper_2 = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="patent_hash_p2",
            title="Patent 2 (Different Workspace)",
            source_url="https://patents.google.com/patent/US11888999B2/en",
            source_database="google_patents"
        )
        doc_reg_2 = register_document_markdown(paper_2, self.sample_md)

        # Exactly same registry object
        self.assertEqual(doc_reg_1.id, doc_reg_2.id)
        doc_reg_1.refresh_from_db()
        self.assertEqual(doc_reg_1.access_count, 2)
        paper_2.refresh_from_db()
        self.assertEqual(paper_2.document_registry, doc_reg_1)

    def test_register_document_markdown_deduplication_by_source_url(self):
        """Registering by matching source_url updates the existing DocumentRegistry record instead of duplicating."""
        url = "https://patents.google.com/patent/EP3334445A1/en"
        paper_1 = Paper.objects.create(
            workspace=self.workspace_a,
            source_url=url,
            title="Initial Patent Draft",
            source_database="google_patents"
        )
        doc_reg = register_document_markdown(paper_1, b"# Initial Markdown")
        self.assertEqual(doc_reg.source_url, url)

        paper_2 = Paper.objects.create(
            workspace=self.workspace_b,
            source_url=url,
            title="Updated Patent Draft",
            source_database="google_patents"
        )
        updated_md = b"# Updated Markdown with more claims"
        doc_reg_2 = register_document_markdown(paper_2, updated_md)

        self.assertEqual(doc_reg.id, doc_reg_2.id)
        self.assertEqual(DocumentRegistry.objects.filter(source_url=url).count(), 1)

    def test_find_in_document_registry_with_markdown_only(self):
        """find_in_document_registry finds markdown documents by source_url or hash even when canonical_pdf_path is empty."""
        url = "https://patents.google.com/patent/WO2026123456A1/en"
        paper = Paper.objects.create(
            workspace=self.workspace_a,
            source_url=url,
            hash_id="wo_patent_hash",
            title="Global Patent",
            source_database="google_patents"
        )
        doc_reg = register_document_markdown(paper, self.sample_md)

        # Lookup by source_url
        found_by_url = find_in_document_registry(paper)
        self.assertIsNotNone(found_by_url)
        self.assertEqual(found_by_url.id, doc_reg.id)

        # Lookup by hash_id when source_url is absent
        paper_lookup_hash = Paper(workspace=self.workspace_b, hash_id=self.sample_md_hash)
        found_by_hash = find_in_document_registry(paper_lookup_hash)
        self.assertIsNotNone(found_by_hash)
        self.assertEqual(found_by_hash.id, doc_reg.id)

    def test_try_reuse_cached_markdown_fastpath_hit(self):
        """try_reuse_cached_markdown copies canonical markdown to target, updates paper, and increments access_count."""
        paper_a = Paper.objects.create(
            workspace=self.workspace_a,
            pipeline_run=self.run_a,
            hash_id="reuse_hash_a",
            source_url="https://patents.google.com/patent/US99887766B2/en",
            title="Reusable Patent",
            source_database="google_patents"
        )
        doc_reg = register_document_markdown(paper_a, self.sample_md)
        initial_access_count = doc_reg.access_count

        paper_b = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            hash_id="reuse_hash_b",
            source_url="https://patents.google.com/patent/US99887766B2/en",
            title="Reusable Patent (WS B)",
            source_database="google_patents"
        )
        target_path = f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/reuse_hash_b/document.md"

        result = try_reuse_cached_markdown(paper_b, target_path, title_snippet="Reusable Patent")

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "downloaded")
        self.assertEqual(result["format"], "markdown")
        self.assertTrue(result["cache_hit"])
        self.assertTrue(result["from_cache"])
        self.assertEqual(result["cached_from"], doc_reg.canonical_ocr_md_path)
        self.assertEqual(result["registry_id"], str(doc_reg.id))
        self.assertTrue(default_storage.exists(target_path))

        with default_storage.open(target_path, 'rb') as f:
            copied_bytes = f.read()
        self.assertEqual(copied_bytes, self.sample_md)

        doc_reg.refresh_from_db()
        self.assertEqual(doc_reg.access_count, initial_access_count + 1)

        paper_b.refresh_from_db()
        self.assertEqual(paper_b.document_registry, doc_reg)
        self.assertEqual(paper_b.converted_md_path, target_path)

    def test_try_reuse_cached_markdown_fallback_to_other_paper(self):
        """When DocumentRegistry entry was somehow omitted, fallback looks for other Paper.converted_md_path and auto-registers."""
        url = "https://patents.google.com/patent/JP2026001002A/en"
        existing_path = "workspaces/test_ws/documents/jp_hash/document.md"
        default_storage.save(existing_path, ContentFile(self.sample_md))

        paper_existing = Paper.objects.create(
            workspace=self.workspace_a,
            source_url=url,
            hash_id="jp_hash",
            title="Japanese Patent",
            source_database="google_patents",
            converted_md_path=existing_path,
            document_registry=None  # intentionally unlinked
        )

        paper_new = Paper.objects.create(
            workspace=self.workspace_b,
            pipeline_run=self.run_b,
            source_url=url,
            hash_id="jp_hash_new",
            title="Japanese Patent (New Run)",
            source_database="google_patents"
        )
        target_path = f"workspaces/{self.workspace_b.id}/runs/{self.run_b.id}/documents/jp_hash_new/document.md"

        result = try_reuse_cached_markdown(paper_new, target_path, title_snippet="Japanese Patent")

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "downloaded")
        self.assertEqual(result["format"], "markdown")
        self.assertTrue(result["cache_hit"])
        self.assertTrue(default_storage.exists(target_path))

        paper_new.refresh_from_db()
        self.assertIsNotNone(paper_new.document_registry)
        self.assertEqual(paper_new.document_registry.source_url, url)

    def test_try_reuse_cached_markdown_missing_file_falls_back(self):
        """If DocumentRegistry points to a deleted canonical file on storage, falls back gracefully to None."""
        doc_reg = DocumentRegistry.objects.create(
            sha256_hash="ghost_md_hash_001",
            source_url="https://patents.google.com/patent/US9999000B1/en",
            title="Ghost Patent Document",
            canonical_ocr_md_path="cache/documents/ghost_md_hash_001/document.md"
            # File intentionally not saved to storage
        )
        paper = Paper.objects.create(
            workspace=self.workspace_a,
            source_url="https://patents.google.com/patent/US9999000B1/en",
            hash_id="ghost_md_hash_001",
            title="Ghost Patent Document"
        )
        target = f"workspaces/{self.workspace_a.id}/documents/ghost/document.md"
        result = try_reuse_cached_markdown(paper, target)
        self.assertIsNone(result)


class MarkdownPaperSignalsAndLifecycleTests(TestCase):
    """
    Tests ensuring access_count in DocumentRegistry is properly maintained
    upon Paper deletion and cascading PipelineRun deletion for Markdown documents.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(name="Signal Workspace")
        self.run = PipelineRun.objects.create(workspace=self.workspace, status="completed")
        self.md_bytes = b"# Patent Lifecycle Test\n\nBody content."

    def test_paper_delete_decrements_markdown_access_count(self):
        paper_1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="signal_p1",
            title="Signal Patent 1",
            source_url="https://patents.google.com/patent/US888777B1/en",
            source_database="google_patents"
        )
        doc_reg = register_document_markdown(paper_1, self.md_bytes)
        self.assertEqual(doc_reg.access_count, 1)

        paper_2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="signal_p2",
            title="Signal Patent 2",
            source_url="https://patents.google.com/patent/US888777B1/en",
            source_database="google_patents"
        )
        register_document_markdown(paper_2, self.md_bytes)
        doc_reg.refresh_from_db()
        self.assertEqual(doc_reg.access_count, 2)

        # Deleting paper_2 drops access_count from 2 to 1
        paper_2.delete()
        doc_reg.refresh_from_db()
        self.assertEqual(doc_reg.access_count, 1)

        # Deleting paper_1 drops access_count from 1 to 0
        paper_1.delete()
        doc_reg.refresh_from_db()
        self.assertEqual(doc_reg.access_count, 0)

    def test_cascading_pipeline_run_delete_decrements_markdown_access_count(self):
        """Deleting a PipelineRun cascade-deletes papers and decrements DocumentRegistry access_count."""
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.run,
            hash_id="cascade_p1",
            title="Cascade Patent",
            source_database="google_patents"
        )
        doc_reg = register_document_markdown(paper, self.md_bytes)
        self.assertEqual(doc_reg.access_count, 1)

        self.run.delete()
        doc_reg.refresh_from_db()
        self.assertEqual(doc_reg.access_count, 0)


class FetchStepMarkdownPipelineTests(TestCase):
    """
    Tests integrating step 2 (fetch.py) when downloading Google Patents
    without PDF scans.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(name="Fetch Workspace")
        self.pipeline_run = PipelineRun.objects.create(workspace=self.workspace, status="running")

    @patch("research_intelligence.tasks.step_2_download.fetch.get_scraper_provider")
    def test_fetch_patent_markdown_creates_document_registry(self, mock_get_provider):
        """Full-text Markdown returned by Google Patents provider is saved, linked, and registered in DocumentRegistry."""
        mock_provider = MagicMock()
        patent_md = b"# Patent US2026112233A1: Quantum Annealing Annealer\n\nFull text."
        patent_meta = {
            "title": "Quantum Annealing Annealer",
            "current_assignee": "D-Wave Innovations",
            "status": "Active",
            "claims_count": 42
        }
        mock_provider.fetch_patent_document.return_value = (patent_md, "markdown", patent_meta)
        mock_get_provider.return_value = mock_provider

        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="fetch_test_hash_001",
            title="Quantum Annealing Annealer",
            source_database="google_patents",
            original_pdf_path="https://patents.google.com/patent/US2026112233A1/en",
            source_url="https://patents.google.com/patent/US2026112233A1/en"
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            screening_status="abstract_passed"
        )

        res = _download_paper_task(
            paper=paper,
            workspace_obj=self.workspace,
            pipeline_run_obj=self.pipeline_run
        )

        self.assertEqual(res["status"], "downloaded")
        self.assertEqual(res["format"], "markdown")
        self.assertIsNotNone(res.get("registry_id"))

        paper.refresh_from_db()
        self.assertIsNotNone(paper.converted_md_path)
        self.assertTrue(default_storage.exists(paper.converted_md_path))
        self.assertIsNotNone(paper.document_registry)
        self.assertEqual(str(paper.document_registry.id), res.get("registry_id"))
        self.assertEqual(paper.document_registry.primary_source, "google_patents")
        self.assertEqual(paper.document_registry.ocr_provider, "google_patents_html")
        self.assertTrue(default_storage.exists(paper.document_registry.canonical_ocr_md_path))

    def test_fetch_already_stored_markdown_auto_registers(self):
        """If paper already has converted_md_path on disk without document_registry, fetch step auto-registers it."""
        stored_path = f"workspaces/{self.workspace.id}/documents/prestored_hash/document.md"
        default_storage.save(stored_path, ContentFile(b"# Pre-stored Patent\n\nText."))

        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="prestored_hash",
            title="Prestored Patent",
            source_database="google_patents",
            source_url="https://patents.google.com/patent/US5555555B1/en",
            converted_md_path=stored_path,
            document_registry=None
        )

        res = _download_paper_task(
            paper=paper,
            workspace_obj=self.workspace,
            pipeline_run_obj=self.pipeline_run
        )

        self.assertEqual(res["status"], "already_stored")
        self.assertEqual(res["format"], "markdown")
        self.assertIsNotNone(res.get("registry_id"))

        paper.refresh_from_db()
        self.assertIsNotNone(paper.document_registry)
        self.assertEqual(str(paper.document_registry.id), res.get("registry_id"))

    @patch("research_intelligence.tasks.step_2_download.fetch.get_scraper_provider")
    def test_fetch_zero_network_cache_reuse_for_markdown(self, mock_get_provider):
        """When an identical patent is already in DocumentRegistry, fetch step reuses it without invoking scraper network."""
        canonical_md = b"# Cached Patent in Registry\n\nCanonical text."
        md_hash = hashlib.sha256(canonical_md).hexdigest()
        canonical_path = f"cache/documents/{md_hash}/document.md"
        default_storage.save(canonical_path, ContentFile(canonical_md))

        doc_reg = DocumentRegistry.objects.create(
            sha256_hash=md_hash,
            source_url="https://patents.google.com/patent/US4444444B1/en",
            title="Cached Patent in Registry",
            primary_source="google_patents",
            ocr_provider="google_patents_html",
            canonical_ocr_md_path=canonical_path,
            access_count=1
        )

        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="new_paper_hash_444",
            title="Cached Patent in Registry",
            source_database="google_patents",
            original_pdf_path="https://patents.google.com/patent/US4444444B1/en",
            source_url="https://patents.google.com/patent/US4444444B1/en"
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            screening_status="abstract_passed"
        )

        res = _download_paper_task(
            paper=paper,
            workspace_obj=self.workspace,
            pipeline_run_obj=self.pipeline_run
        )

        mock_get_provider.assert_not_called()
        self.assertEqual(res["status"], "downloaded")
        self.assertTrue(res.get("cache_hit"))
        self.assertEqual(res.get("registry_id"), str(doc_reg.id))


class ConvertStepMarkdownBypassTests(TestCase):
    """
    Tests ensuring step 3 (OCR/convert.py) bypasses OCR computation
    for papers that already have Markdown full-text from Google Patents.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(name="OCR Test Workspace", ocr_provider="pypdf")
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            title="Patent Ready For OCR Bypass",
            source_database="google_patents"
        )
        self.md_path = f"workspaces/{self.workspace.id}/documents/{self.paper.id}/document.md"
        default_storage.save(self.md_path, ContentFile(b"# Ready Markdown\n\nNo OCR needed."))
        self.paper.converted_md_path = self.md_path
        self.paper.save(update_fields=['converted_md_path'])

    @patch("research_intelligence.tasks.step_3_ocr.convert.get_ocr_provider")
    def test_run_ocr_conversion_skips_when_markdown_exists(self, mock_get_ocr):
        """When paper.converted_md_path already exists, run_ocr_conversion returns immediately without calling OCR engine."""
        res = run_ocr_conversion(self.paper.id, paper_obj=self.paper)
        mock_get_ocr.assert_not_called()
        self.assertTrue(res["success"])
        self.assertTrue(res["already_exists"])
        self.assertEqual(res["storage_path"], self.md_path)

    def test_run_ocr_conversion_auto_registers_unlinked_markdown(self):
        """If paper had converted_md_path but no document_registry, run_ocr_conversion registers it."""
        self.assertIsNone(self.paper.document_registry)
        res = run_ocr_conversion(self.paper.id, paper_obj=self.paper)
        self.assertTrue(res["success"])

        self.paper.refresh_from_db()
        self.assertIsNotNone(self.paper.document_registry)
        self.assertEqual(self.paper.document_registry.canonical_ocr_md_path, f"cache/documents/{hashlib.sha256(b'# Ready Markdown\n\nNo OCR needed.').hexdigest()}/document.md")


class AdminMarkdownInterfaceAndActionsTests(TestCase):
    """
    Tests ensuring Django Admin properly exposes clickable Markdown badges,
    preview buttons, download links, and sync actions.
    """

    def setUp(self):
        self.admin_site = AdminSite()
        self.paper_admin = PaperAdmin(Paper, self.admin_site)
        self.doc_admin = DocumentRegistryAdmin(DocumentRegistry, self.admin_site)

        self.workspace = Workspace.objects.create(name="Admin WS")
        self.user = User.objects.create_superuser("adminuser", "admin@test.com", "password123")

    def test_paper_admin_document_files_badge_variants(self):
        """Tests all permutations of PaperAdmin.document_files_badge (MD only, PDF only, both, none)."""
        # 1. MD only
        p_md = Paper(converted_md_path="workspaces/ws1/runs/r1/documents/h1/document.md")
        badge_md = self.paper_admin.document_files_badge(p_md)
        self.assertIn("📝 MD ↗", str(badge_md))
        self.assertIn("action=preview", str(badge_md))
        self.assertNotIn("📄 PDF ↗", str(badge_md))

        # 2. Local PDF only
        p_pdf = Paper(original_pdf_path="workspaces/ws1/runs/r1/documents/h1/original.pdf")
        badge_pdf = self.paper_admin.document_files_badge(p_pdf)
        self.assertIn("📄 PDF ↗", str(badge_pdf))
        self.assertIn("action=preview", str(badge_pdf))
        self.assertNotIn("📝 MD ↗", str(badge_pdf))

        # 3. Both MD and PDF
        p_both = Paper(
            converted_md_path="workspaces/ws1/document.md",
            original_pdf_path="workspaces/ws1/original.pdf"
        )
        badge_both = self.paper_admin.document_files_badge(p_both)
        self.assertIn("📝 MD ↗", str(badge_both))
        self.assertIn("📄 PDF ↗", str(badge_both))

        # 4. Neither
        p_none = Paper()
        badge_none = self.paper_admin.document_files_badge(p_none)
        self.assertIn("-", str(badge_none))

    def test_paper_admin_converted_md_display(self):
        """converted_md_display renders clickable preview and download buttons."""
        p = Paper(converted_md_path="workspaces/ws1/document.md")
        display_html = self.paper_admin.converted_md_display(p)
        self.assertIn("👁️ Preview Markdown", str(display_html))
        self.assertIn("⬇️ Download", str(display_html))
        self.assertIn("action=preview", str(display_html))
        self.assertIn("action=download", str(display_html))

    def test_document_registry_admin_file_size_formatted_native_md(self):
        """When document has no PDF scan but has Markdown, file_size_formatted returns 'Native MD'."""
        doc_native_md = DocumentRegistry(
            canonical_pdf_path="",
            canonical_ocr_md_path="cache/documents/h1/document.md"
        )
        formatted = self.doc_admin.file_size_formatted(doc_native_md)
        self.assertIn("Native MD", str(formatted))

    def test_document_registry_admin_ocr_status_badge_clickable(self):
        """ocr_status_badge returns a clickable badge linking to Storage Browser preview."""
        doc = DocumentRegistry(
            ocr_provider="google_patents_html",
            canonical_ocr_md_path="cache/documents/h1/document.md"
        )
        badge = self.doc_admin.ocr_status_badge(doc)
        self.assertIn("GOOGLE_PATENTS_HTML", str(badge))
        self.assertIn("action=preview", str(badge))
        self.assertIn("target=\"_blank\"", str(badge))

    def test_document_registry_admin_canonical_ocr_md_display(self):
        """canonical_ocr_md_display renders preview and download buttons."""
        doc = DocumentRegistry(canonical_ocr_md_path="cache/documents/h1/document.md")
        display_html = self.doc_admin.canonical_ocr_md_display(doc)
        self.assertIn("👁️ Preview Markdown", str(display_html))
        self.assertIn("⬇️ Download", str(display_html))

    def test_sync_document_registry_action_mixed_papers(self):
        """Admin action sync_document_registry processes unlinked papers and registers valid ones."""
        # Paper 1: Unlinked with existing MD file
        md_file_1 = "workspaces/sync_test/documents/h1/document.md"
        default_storage.save(md_file_1, ContentFile(b"# Sync Patent 1"))
        p1 = Paper.objects.create(
            workspace=self.workspace,
            hash_id="sync_h1",
            title="Sync Patent 1",
            source_database="google_patents",
            converted_md_path=md_file_1,
            document_registry=None
        )

        # Paper 2: Unlinked with existing PDF file
        pdf_file_2 = "workspaces/sync_test/documents/h2/original.pdf"
        default_storage.save(pdf_file_2, ContentFile(b"%PDF-1.4 Mock"))
        p2 = Paper.objects.create(
            workspace=self.workspace,
            hash_id="sync_h2",
            title="Sync Paper 2",
            source_database="arxiv",
            original_pdf_path=pdf_file_2,
            document_registry=None
        )

        # Paper 3: Already linked (should be skipped)
        doc_reg_3 = DocumentRegistry.objects.create(
            sha256_hash="already_reg_hash",
            title="Already Registered"
        )
        p3 = Paper.objects.create(
            workspace=self.workspace,
            hash_id="sync_h3",
            title="Already Linked",
            document_registry=doc_reg_3
        )

        # Paper 4: Unlinked but file missing on disk (should not crash)
        p4 = Paper.objects.create(
            workspace=self.workspace,
            hash_id="sync_h4",
            title="Missing File Paper",
            converted_md_path="workspaces/sync_test/ghost/document.md",
            document_registry=None
        )

        request = MagicMock()
        queryset = Paper.objects.filter(id__in=[p1.id, p2.id, p3.id, p4.id])
        self.paper_admin.sync_document_registry(request, queryset)

        p1.refresh_from_db()
        self.assertIsNotNone(p1.document_registry)
        self.assertEqual(p1.document_registry.primary_source, "google_patents")

        p2.refresh_from_db()
        self.assertIsNotNone(p2.document_registry)
        self.assertEqual(p2.document_registry.primary_source, "arxiv")

        p3.refresh_from_db()
        self.assertEqual(p3.document_registry.id, doc_reg_3.id)

        p4.refresh_from_db()
        self.assertIsNone(p4.document_registry)


class Migration0078BackfillTests(TestCase):
    """
    Tests ensuring data migration 0078 correctly backfills all legacy unlinked
    Markdown papers into DocumentRegistry.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(name="Migration WS")
        mig_module = importlib.import_module("research_intelligence.migrations.0078_backfill_markdown_document_registry")
        self.backfill_fn = getattr(mig_module, "backfill_markdown_document_registry")

    def test_migration_backfills_unlinked_markdown_papers(self):
        # Setup 2 papers with distinct files
        f1 = "workspaces/mig/p1/document.md"
        f2 = "workspaces/mig/p2/document.md"
        default_storage.save(f1, ContentFile(b"# Legacy Patent 1"))
        default_storage.save(f2, ContentFile(b"# Legacy Patent 2"))

        p1 = Paper.objects.create(
            workspace=self.workspace,
            hash_id="legacy_h1",
            title="Legacy Patent 1",
            source_database="google_patents",
            converted_md_path=f1,
            document_registry=None
        )
        p2 = Paper.objects.create(
            workspace=self.workspace,
            hash_id="legacy_h2",
            title="Legacy Patent 2",
            source_database="google_patents",
            converted_md_path=f2,
            document_registry=None
        )

        # Run migration function
        self.backfill_fn(apps, None)

        p1.refresh_from_db()
        p2.refresh_from_db()

        self.assertIsNotNone(p1.document_registry)
        self.assertIsNotNone(p2.document_registry)
        self.assertNotEqual(p1.document_registry.id, p2.document_registry.id)
        self.assertTrue(default_storage.exists(p1.document_registry.canonical_ocr_md_path))
        self.assertTrue(default_storage.exists(p2.document_registry.canonical_ocr_md_path))

    def test_migration_backfill_deduplicates_identical_content(self):
        """Two legacy papers with identical markdown content share a single DocumentRegistry entry after migration."""
        f1 = "workspaces/mig_dup/p1/document.md"
        f2 = "workspaces/mig_dup/p2/document.md"
        identical_content = b"# Identical Patent Content Across Workspaces"
        default_storage.save(f1, ContentFile(identical_content))
        default_storage.save(f2, ContentFile(identical_content))

        p1 = Paper.objects.create(
            workspace=self.workspace,
            hash_id="dup_h1",
            title="Duplicate Patent 1",
            source_database="google_patents",
            converted_md_path=f1
        )
        p2 = Paper.objects.create(
            workspace=self.workspace,
            hash_id="dup_h2",
            title="Duplicate Patent 2",
            source_database="google_patents",
            converted_md_path=f2
        )

        self.backfill_fn(apps, None)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.document_registry.id, p2.document_registry.id)
        self.assertEqual(DocumentRegistry.objects.filter(sha256_hash=hashlib.sha256(identical_content).hexdigest()).count(), 1)
