import os
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from research_intelligence.models import (
    Workspace,
    PipelineRun,
    Paper,
    PaperMetric,
    ComponentRun,
)
from research_intelligence.tasks.step_2_download.fetch import execute_pdf_download_job
from research_intelligence.tasks.step_4_screening.full_text import execute_full_text_screening_job


class DownloadFullTextFunnelConsistencyTestCase(TestCase):
    """
    Test suite verifying that:
    1. Failed PDF downloads are marked as rejected (retrieval failure) in PaperMetric.
    2. Full-text screening ONLY targets papers that have retrieved full-text documents (PDF or OCR MD).
    3. The number of papers screened in Full-Text screening matches the number of successfully
       downloaded papers, preventing phantom screenings via abstract fallback and ensuring strict PRISMA consistency.
    """

    def setUp(self):
        self.sleep_patcher = patch("time.sleep", return_value=None)
        self.sleep_patcher.start()
        self.addCleanup(self.sleep_patcher.stop)

        self.workspace = Workspace.objects.create(
            name="Funnel Consistency Workspace",
            full_text_acceptance_criteria="Autonomous robotics manipulation",
            full_text_rejection_criteria="Pure simulation without real-world tests",
            screening_llm_model="google/gemini-3.8-flash"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )

    def test_failed_downloads_excluded_from_full_text_screening_exact_count(self):
        """
        Mirror of run cfed739f-d1d4-4178-ad44-2b7219651f03:
        - 7 papers passed abstract screening.
        - Download: 3 succeed, 4 fail.
        - Full-text screening must screen EXACTLY 3 papers (not 7!).
        - Downstream metrics must be strictly consistent.
        """
        # 1. Setup prior Abstract Screening component run marked completed
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="abstract_screening",
            status="completed",
            metrics={"passed": 7, "screened": 84, "rejected": 77}
        )

        papers = []
        for i in range(1, 8):
            paper = Paper.objects.create(
                workspace=self.workspace,
                pipeline_run=self.pipeline_run,
                hash_id=f"paper_funnel_{i:03d}",
                title=f"Paper Title {i} on Robotics Manipulation",
                abstract=f"Abstract for paper {i} discussing robotic grasp and control.",
                original_pdf_path=f"https://arxiv.org/pdf/2401.0000{i}.pdf" if i != 7 else None,
                source_database="arxiv"
            )
            PaperMetric.objects.create(
                paper=paper,
                pipeline_run=self.pipeline_run,
                workspace=self.workspace,
                screening_status="abstract_passed",
                abstract_screening_reasoning="Passed abstract relevance check."
            )
            papers.append(paper)

        # Mock download provider: papers 1, 2, 3 succeed; papers 4, 5, 6 raise errors; paper 7 has no URL
        mock_pdf_binary = b"%PDF-1.5 Valid PDF document binary content"

        def mock_download_file(url):
            if any(k in url for k in ["00001", "00002", "00003"]):
                return mock_pdf_binary
            elif "00004" in url:
                return b""  # 0 bytes
            elif "00005" in url:
                return b"<!DOCTYPE html><html><body>Error 403 Forbidden</body></html>"  # Non-PDF
            raise RuntimeError("Connection dropped by remote server")

        # 2. Run Step 2: Download
        download_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="download",
            component_name="document_download",
            status="pending"
        )

        with patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.download_file", side_effect=mock_download_file):
            download_success = execute_pdf_download_job(str(download_comp_run.id), max_workers=1)
            self.assertTrue(download_success)

        download_comp_run.refresh_from_db()
        self.assertEqual(download_comp_run.status, "completed")
        self.assertEqual(download_comp_run.metrics["downloaded"], 3)
        self.assertEqual(download_comp_run.metrics["failed"], 4)

        # Verify PaperMetric status for all 7 papers after download
        for i in range(1, 4):
            papers[i - 1].refresh_from_db()
            pm = PaperMetric.objects.get(paper=papers[i - 1], pipeline_run=self.pipeline_run)
            self.assertEqual(pm.screening_status, "abstract_passed", f"Paper {i} should remain abstract_passed")
            self.assertTrue(default_storage.exists(papers[i - 1].original_pdf_path))

        for i in range(4, 8):
            pm = PaperMetric.objects.get(paper=papers[i - 1], pipeline_run=self.pipeline_run)
            self.assertEqual(pm.screening_status, "rejected", f"Paper {i} with failed download must be marked as rejected")
            self.assertIn("Full-text retrieval failed", pm.full_text_screening_reasoning)

        # 3. Run Step 4: Full-Text Screening
        fulltext_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="full_text_screening",
            status="pending"
        )

        mock_llm_response = {
            "passed": True,
            "reasoning": "Strong empirical robotic manipulation results on physical hardware.",
            "evidence_quotes": ["95% success rate on Franka Emika"],
            "decision_category": "ACCEPTED"
        }
        mock_usage = {"prompt_tokens": 1200, "candidates_tokens": 150, "total_tokens": 1350}

        with patch("research_intelligence.tasks.step_4_screening.full_text.get_llm_provider") as mock_provider_factory:
            mock_provider = MagicMock()
            mock_provider.generate.return_value = (mock_llm_response, mock_usage)
            mock_provider_factory.return_value = mock_provider

            ft_success = execute_full_text_screening_job(str(fulltext_comp_run.id), max_workers=1)
            self.assertTrue(ft_success)

            # Assert LLM was called EXACTLY 3 times (only for the 3 downloaded documents!)
            self.assertEqual(mock_provider.generate.call_count, 3)

        fulltext_comp_run.refresh_from_db()
        self.assertEqual(fulltext_comp_run.status, "completed")
        # CRITICAL ASSERTION: exactly 3 screened, 3 passed, 0 rejected in this full-text step
        self.assertEqual(fulltext_comp_run.metrics["total_screened"], 3)
        self.assertEqual(fulltext_comp_run.metrics["passed"], 3)
        self.assertEqual(fulltext_comp_run.metrics["rejected"], 0)

        # PipelineRun aggregate passed count should be 3
        self.pipeline_run.refresh_from_db()
        self.assertEqual(self.pipeline_run.total_papers_passed_screening, 3)

    def test_unretrieved_papers_cleanup_when_full_text_screening_runs(self):
        """
        Verify that even if PaperMetrics had not been marked as rejected earlier,
        execute_full_text_screening_job detects unretrieved papers, excludes them,
        and marks them as rejected rather than screening their abstracts.
        """
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="abstract_screening",
            status="completed"
        )
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="download",
            component_name="document_download",
            status="completed"
        )

        # Paper with downloaded PDF
        p1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="p1_downloaded",
            title="Downloaded Paper"
        )
        pdf_storage_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{p1.hash_id}/original.pdf"
        default_storage.save(pdf_storage_path, ContentFile(b"%PDF-1.4 content"))
        p1.original_pdf_path = pdf_storage_path
        p1.save(update_fields=['original_pdf_path'])
        PaperMetric.objects.create(
            paper=p1,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="abstract_passed"
        )

        # Paper without downloaded PDF (still has http url or None)
        p2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="p2_missing",
            title="Unretrieved Paper",
            original_pdf_path="https://example.com/unretrieved.pdf"
        )
        pm2 = PaperMetric.objects.create(
            paper=p2,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="abstract_passed"
        )

        fulltext_comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="full_text_screening",
            status="pending"
        )

        mock_llm_response = {
            "passed": True,
            "reasoning": "Passed.",
            "decision_category": "ACCEPTED"
        }
        with patch("research_intelligence.tasks.step_4_screening.full_text.get_llm_provider") as mock_provider_factory:
            mock_provider = MagicMock()
            mock_provider.generate.return_value = (mock_llm_response, {"total_tokens": 100})
            mock_provider_factory.return_value = mock_provider

            execute_full_text_screening_job(str(fulltext_comp_run.id), max_workers=1)
            # Only p1 should be screened with LLM
            self.assertEqual(mock_provider.generate.call_count, 1)

        fulltext_comp_run.refresh_from_db()
        self.assertEqual(fulltext_comp_run.metrics["total_screened"], 1)
        self.assertEqual(fulltext_comp_run.metrics["passed"], 1)

        pm2.refresh_from_db()
        self.assertEqual(pm2.screening_status, "rejected")
        self.assertIn("Full-text document could not be retrieved", pm2.full_text_screening_reasoning)
