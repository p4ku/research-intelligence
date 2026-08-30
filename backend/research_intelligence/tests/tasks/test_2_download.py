import os
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.core.files.storage import default_storage

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    Paper,
    ComponentRun,
    DocumentRegistry,
)
from research_intelligence.tasks.step_2_download.fetch import execute_pdf_download_job
from research_intelligence.tasks.step_2_download.node import DownloadNode


class DownloadTaskTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Download Test Project",
            abstract_acceptance_criteria="Active learning criteria",
            abstract_rejection_criteria="Heuristics rejection"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.paper_with_url = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="arxiv_test_101",
            title="Active Learning in Deep Architectures",
            authors="Alice Cooper, Bob Builder",
            abstract="We propose active learning models.",
            arxiv_id="2103.00001",
            source_database="arxiv"
        )
        self.paper_no_url = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="openalex_no_pdf_102",
            title="Theoretical Limits of Compute",
            authors="Charlie Chaplin",
            abstract="A purely theoretical treatise.",
            source_database="openalex"
        )
        self.component_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="download",
            component_name="pdf_downloader",
            status="pending"
        )

    @patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file")
    def test_execute_pdf_download_job_success(self, mock_download_file):
        fake_bytes = b"%PDF-1.4 Fake PDF Content for Active Learning Test"
        mock_download_file.return_value = fake_bytes

        result = execute_pdf_download_job(str(self.component_run.id))
        self.assertTrue(result)

        self.paper_with_url.refresh_from_db()
        self.assertIsNotNone(self.paper_with_url.original_pdf_path)
        self.assertTrue(default_storage.exists(self.paper_with_url.original_pdf_path))

        # Cleanup
        if default_storage.exists(self.paper_with_url.original_pdf_path):
            default_storage.delete(self.paper_with_url.original_pdf_path)

    def test_download_node_contract_and_summary(self):
        node = DownloadNode()
        self.assertEqual(node.name, "download")
        self.assertEqual(node.dependencies, ["abstract_screening"])
        self.assertIn("storage_artifacts", node.output_contract)

        self.component_run.metrics = {"downloaded": 5, "cached": 3, "failed": 1}
        summary = node.generate_stage_summary(self.component_run, status="completed")
        self.assertIn("5 downloaded", summary)
