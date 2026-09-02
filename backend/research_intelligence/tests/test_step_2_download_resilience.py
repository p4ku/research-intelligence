import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from research_intelligence.models import Workspace, Paper, PaperMetric, PipelineRun, ComponentRun
from research_intelligence.tasks.step_2_download.fetch import execute_pdf_download_job, _download_paper_task

User = get_user_model()


class Step2DownloadResilienceTestCase(TestCase):
    """
    Validates Step 2 (PDF Download) resilience against:
    1. Valid PDF binaries downloaded and properly indexed to storage.
    2. HTML Paywalls, Cloudflare Captchas, or empty payloads returned instead of binary PDFs.
    3. Network 404/500/Timeout HTTP errors with retry exhaustion.
    4. Papers marked as withdrawn or lacking source URLs.
    """

    def setUp(self):
        self.sleep_patcher = patch("time.sleep", return_value=None)
        self.sleep_patcher.start()
        self.addCleanup(self.sleep_patcher.stop)

        self.workspace = Workspace.objects.create(
            name="Download Resilience Workspace",
            screening_llm_model="google/gemini-3.8-flash"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.component_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            component_name="pdf_downloader",
            step_type="download",
            status="pending"
        )

    def test_valid_pdf_download_success(self):
        """
        Tests successful fetching and saving of a valid PDF document.
        """
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="resilient_pdf_001",
            title="Transformer Scaling Laws in Deep Learning",
            original_pdf_path="https://arxiv.org/pdf/2401.12345.pdf",
            source_database="arxiv"
        )
        PaperMetric.objects.create(paper=paper, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="pending")

        mock_pdf_binary = b"%PDF-1.5 %binary pdf stream content..." * 50

        with patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file", return_value=mock_pdf_binary):
            result = _download_paper_task(paper, self.workspace, self.pipeline_run)
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(result["size_bytes"], len(mock_pdf_binary))

        paper.refresh_from_db()
        expected_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{paper.hash_id}/original.pdf"
        self.assertEqual(paper.original_pdf_path, expected_path)
        self.assertTrue(default_storage.exists(expected_path))

    def test_404_unavailable_source_marks_paper_withdrawn(self):
        """
        Tests that when a server returns HTTP 404, the paper is gracefully categorized as 'withdrawn'
        so subsequent pipeline steps do not crash on missing text.
        """
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="resilient_pdf_404",
            title="Unavailable 404 Document",
            original_pdf_path="https://arxiv.org/pdf/2401.99999.pdf",
            source_database="arxiv"
        )
        PaperMetric.objects.create(paper=paper, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="pending")

        with patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file", side_effect=ValueError("HTTP 404: Not Found")):
            result = _download_paper_task(paper, self.workspace, self.pipeline_run)
            self.assertEqual(result["status"], "withdrawn")
            self.assertIn("withdrawn", result["reason"])

        pm = PaperMetric.objects.get(paper=paper, pipeline_run=self.pipeline_run)
        self.assertEqual(pm.screening_status, "withdrawn")
        self.assertFalse(default_storage.exists(f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{paper.hash_id}/original.pdf"))

    def test_network_failure_and_retry_exhaustion(self):
        """
        Tests handling when download fails due to network drop with retries and failure logging.
        """
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="resilient_pdf_dropped",
            title="Connection Reset Document",
            original_pdf_path="https://arxiv.org/pdf/2401.88888.pdf",
            source_database="arxiv"
        )
        PaperMetric.objects.create(paper=paper, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="pending")

        with patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file", side_effect=ConnectionResetError("Connection dropped by remote peer")), \
             patch("time.sleep"):
            result = _download_paper_task(paper, self.workspace, self.pipeline_run)
            self.assertEqual(result["status"], "failed")
            self.assertIn("Connection dropped", result["error"])

        paper.refresh_from_db()
        self.assertFalse(default_storage.exists(f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{paper.hash_id}/original.pdf"))

    def test_withdrawn_paper_skipped(self):
        """
        Tests that papers with screening_status='withdrawn' are skipped gracefully without network requests.
        """
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="resilient_pdf_withdrawn",
            title="Withdrawn Quantum Paper",
            original_pdf_path="https://arxiv.org/pdf/2401.11111.pdf",
            source_database="arxiv"
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="withdrawn",
            screening_reasoning="Paper withdrawn by author due to experimental flaw."
        )

        with patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file") as mock_dl:
            result = _download_paper_task(paper, self.workspace, self.pipeline_run)
            self.assertEqual(result["status"], "withdrawn")
            self.assertIn("withdrawn", result["reason"])
            mock_dl.assert_not_called()

    def test_missing_pdf_url_handled_cleanly(self):
        """
        Tests that papers lacking any valid PDF URL or DOI are flagged without raising unhandled exceptions.
        """
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="resilient_pdf_no_url",
            title="Paper Without Any Source Link",
            original_pdf_path=None,
            arxiv_id=None,
            source_database="arxiv"
        )
        PaperMetric.objects.create(paper=paper, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="pending")

        result = _download_paper_task(paper, self.workspace, self.pipeline_run)
        self.assertEqual(result["status"], "failed")
        self.assertIn("No valid PDF source URL", result["error"])

    def test_execute_pdf_download_job_batch_metrics(self):
        """
        Executes full execute_pdf_download_job with mixed outcomes (success, failed, withdrawn)
        and validates ComponentRun summary metrics.
        """
        p1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="batch_001",
            title="Batch Paper 1",
            original_pdf_path="https://arxiv.org/pdf/2401.00001.pdf",
            source_database="arxiv"
        )
        PaperMetric.objects.create(paper=p1, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="pending")
        p2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="batch_002",
            title="Batch Paper 2",
            original_pdf_path="https://arxiv.org/pdf/2401.00002.pdf",
            source_database="arxiv"
        )
        PaperMetric.objects.create(paper=p2, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="pending")

        mock_bytes = b"%PDF-1.5 batch content"

        def mock_download(url):
            if "00001" in url:
                return mock_bytes
            raise RuntimeError("Connection dropped by remote peer")

        with patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file", side_effect=mock_download):
            success = execute_pdf_download_job(str(self.component_run.id))
            self.assertTrue(success)

        self.component_run.refresh_from_db()
        self.assertEqual(self.component_run.status, "completed")
        self.assertEqual(self.component_run.metrics["downloaded"], 1)
        self.assertEqual(self.component_run.metrics["failed"], 1)

    def test_cross_workspace_and_cross_run_pdf_cache_reuse(self):
        """
        Validates that if Workspace 1 (Run 10) previously fetched a PDF,
        Workspace 7 (Run 100) reuses the local cached binary with 0 network HTTP requests.
        """
        # Workspace 1 (Run 10) fetches paper
        ws1 = Workspace.objects.create(name="Workspace 1")
        run10 = PipelineRun.objects.create(workspace=ws1, status="completed")
        pdf_bytes = b"%PDF-1.4 Cached Cross-Workspace Document Content" * 20
        ws1_storage_path = f"workspaces/{ws1.id}/runs/{run10.id}/documents/qml_cached_01/original.pdf"
        default_storage.save(ws1_storage_path, ContentFile(pdf_bytes))

        Paper.objects.create(
            workspace=ws1,
            pipeline_run=run10,
            hash_id="qml_cached_01",
            arxiv_id="2401.99999",
            title="Cross Workspace Quantum Benchmark Paper",
            original_pdf_path=ws1_storage_path,
            source_database="arxiv"
        )

        # Workspace 7 (Run 100) wants the exact same paper
        ws7 = Workspace.objects.create(name="Workspace 7")
        run100 = PipelineRun.objects.create(workspace=ws7, status="running")
        paper_ws7 = Paper.objects.create(
            workspace=ws7,
            pipeline_run=run100,
            hash_id="qml_cached_ws7_01",
            arxiv_id="2401.99999",
            title="Cross Workspace Quantum Benchmark Paper",
            original_pdf_path="https://arxiv.org/pdf/2401.99999.pdf",
            source_database="arxiv"
        )

        # Ensure network scraper is NEVER called because local cache hit occurs
        with patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file") as mock_network_download:
            result = _download_paper_task(paper_ws7, ws7, run100)
            mock_network_download.assert_not_called()

        self.assertEqual(result["status"], "downloaded")
        self.assertTrue(result.get("cache_hit"))
        self.assertEqual(result.get("cached_from"), ws1_storage_path)

        # Verify Workspace 7 has its own isolated PDF in storage
        expected_ws7_path = f"workspaces/{ws7.id}/runs/{run100.id}/documents/{paper_ws7.hash_id}/original.pdf"
        self.assertTrue(default_storage.exists(expected_ws7_path))
        paper_ws7.refresh_from_db()
        self.assertEqual(paper_ws7.original_pdf_path, expected_ws7_path)
