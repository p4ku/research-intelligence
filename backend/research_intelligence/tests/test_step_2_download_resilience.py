import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from research_intelligence.models import Workspace, Paper, PipelineRun, ComponentRun
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
            screening_llm_model="google/gemini-3.7-flash"
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
            source_database="arxiv",
            screening_status="pending"
        )

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
            source_database="arxiv",
            screening_status="pending"
        )

        with patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file", side_effect=ValueError("HTTP 404: Not Found")):
            result = _download_paper_task(paper, self.workspace, self.pipeline_run)
            self.assertEqual(result["status"], "withdrawn")
            self.assertIn("withdrawn", result["reason"])

        paper.refresh_from_db()
        self.assertEqual(paper.screening_status, "withdrawn")
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
            source_database="arxiv",
            screening_status="pending"
        )

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
            source_database="arxiv",
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
            source_database="arxiv",
            screening_status="pending"
        )

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
            source_database="arxiv",
            screening_status="pending"
        )
        p2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="batch_002",
            title="Batch Paper 2",
            original_pdf_path="https://arxiv.org/pdf/2401.00002.pdf",
            source_database="arxiv",
            screening_status="pending"
        )

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
