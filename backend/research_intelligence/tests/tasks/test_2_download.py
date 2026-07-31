from django.test import TestCase
from unittest.mock import patch
from ...models import Workspace, PipelineRun, Paper
from ...tasks.step_2_download.fetch import download_pdf_to_s3

class DownloadTaskTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Download Test Project",
            abstract_acceptance_criteria="Accept active learning.",
            abstract_rejection_criteria="Reject rule-based systems."
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="test_hash_download",
            title="Download Target Paper",
            authors="Alice Cooper",
            abstract="Some abstract text.",
            original_pdf_path="https://arxiv.org/pdf/2103.00020.pdf",
            source_database="arxiv"
        )

    @patch("django.core.files.storage.default_storage.save")
    @patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file")
    def test_download_pdf_to_s3_success(self, mock_download, mock_save):
        mock_download.return_value = b"%PDF-1.4 mock pdf data"
        
        result = download_pdf_to_s3(self.paper.id)
        self.assertTrue(result)
        
        self.paper.refresh_from_db()
        expected_path = f"papers/{self.paper.id}.pdf"
        self.assertEqual(self.paper.original_pdf_path, expected_path)
        
        mock_download.assert_called_once_with("https://arxiv.org/pdf/2103.00020.pdf")
        mock_save.assert_called_once()
        saved_path, content_file = mock_save.call_args[0]
        self.assertEqual(saved_path, expected_path)
        self.assertEqual(content_file.read(), b"%PDF-1.4 mock pdf data")
