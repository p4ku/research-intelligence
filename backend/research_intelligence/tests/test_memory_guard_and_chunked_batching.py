import os
from unittest.mock import patch, MagicMock
from django.test import TestCase

from research_intelligence.utils.memory_guard import reclaim_ram
from research_intelligence.models import (
    Workspace,
    PipelineRun,
    ComponentRun,
    Paper,
    PaperMetric,
)
from research_intelligence.tasks.step_2_download.fetch import execute_pdf_download_job
from research_intelligence.tasks.step_3_ocr.convert import execute_ocr_job
from research_intelligence.tasks.step_4_screening.full_text import execute_full_text_screening_job


class MemoryGuardAndChunkedBatchingTestCase(TestCase):
    """
    Unit test suite validating:
    1. Memory guard utility (reclaim_ram) behavior and cross-platform resilience.
    2. Glibc malloc_trim invocation when available on Linux.
    3. Chunked batching and periodic RAM reclamation in execute_pdf_download_job.
    4. Chunked batching and periodic RAM reclamation in execute_ocr_conversion_job.
    5. Chunked batching and periodic RAM reclamation in execute_full_text_screening_job.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="RAM Optimization Test Workspace",
            ocr_provider="marker"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            name="RAM Optimization Run",
            status="running"
        )

    def test_reclaim_ram_runs_without_exception(self):
        """reclaim_ram should run safely and trigger Python garbage collection."""
        with patch("gc.collect", wraps=None) as mock_gc:
            reclaim_ram("test_unit_context")
            mock_gc.assert_called_once()

    def test_reclaim_ram_invokes_malloc_trim_when_available(self):
        """When libc has malloc_trim, reclaim_ram should invoke malloc_trim(0)."""
        mock_libc = MagicMock()
        mock_libc.malloc_trim.return_value = 1

        with patch("ctypes.CDLL", return_value=mock_libc):
            reclaim_ram("test_malloc_trim_context")
            mock_libc.malloc_trim.assert_called_once_with(0)

    def test_reclaim_ram_handles_missing_malloc_trim_gracefully(self):
        """When libc lacks malloc_trim or ctypes fails, reclaim_ram should not crash."""
        with patch("ctypes.CDLL", side_effect=OSError("No such library")):
            # Must not raise an exception
            reclaim_ram("missing_libc_context")

    @patch.dict(os.environ, {"DOWNLOAD_CHUNK_SIZE": "2"})
    @patch("research_intelligence.tasks.step_2_download.fetch.reclaim_ram")
    @patch("research_intelligence.tasks.step_2_download.fetch._download_paper_task")
    def test_pdf_download_chunking_and_memory_reclamation(self, mock_download_task, mock_reclaim):
        """Verifies that 5 papers are partitioned into chunks of 2 and reclaim_ram is called per chunk."""
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="download",
            component_name="download",
            status="pending"
        )

        papers = []
        for i in range(5):
            p = Paper.objects.create(
                workspace=self.workspace,
                title=f"Paper {i}",
                hash_id=f"hash_{i}",
                pipeline_run=self.pipeline_run,
                screening_status="abstract_passed"
            )
            papers.append(p)

        mock_download_task.side_effect = lambda p, ws, pr: {
            "status": "downloaded",
            "paper_id": str(p.id),
            "title": p.title,
            "size_bytes": 1024,
            "size_kb": 1.0,
            "storage_path": f"workspaces/test/{p.id}/original.pdf"
        }

        success = execute_pdf_download_job(str(comp_run.id), max_workers=1)
        self.assertTrue(success)

        comp_run.refresh_from_db()
        self.assertEqual(comp_run.status, "completed")
        self.assertEqual(comp_run.metrics["downloaded"], 5)
        # 5 papers with chunk size 2 -> 3 chunks (2, 2, 1) -> reclaim_ram called 3 times
        self.assertEqual(mock_reclaim.call_count, 3)

    @patch.dict(os.environ, {"OCR_CHUNK_SIZE": "2"})
    @patch("research_intelligence.tasks.step_3_ocr.convert.reclaim_ram")
    @patch("research_intelligence.tasks.step_3_ocr.convert.run_ocr_conversion")
    def test_ocr_conversion_chunking_and_memory_reclamation(self, mock_ocr_convert, mock_reclaim):
        """Verifies that OCR processing chunks papers and invokes reclaim_ram after each batch."""
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="ocr",
            component_name="ocr",
            status="pending"
        )

        for i in range(5):
            p = Paper.objects.create(
                workspace=self.workspace,
                title=f"OCR Paper {i}",
                hash_id=f"ocr_hash_{i}",
                pipeline_run=self.pipeline_run,
                original_pdf_path=f"workspaces/test/{i}/original.pdf"
            )

        mock_ocr_convert.return_value = {
            "success": True,
            "storage_path": "workspaces/test/output.md",
            "already_exists": False
        }

        success = execute_ocr_job(str(comp_run.id), max_workers=1)
        self.assertTrue(success)

        comp_run.refresh_from_db()
        self.assertEqual(comp_run.status, "completed")
        self.assertEqual(comp_run.metrics["converted"], 5)
        # 5 papers with chunk size 2 -> 3 chunks -> 3 reclaim_ram invocations
        self.assertEqual(mock_reclaim.call_count, 3)

    @patch.dict(os.environ, {"FULL_TEXT_CHUNK_SIZE": "2"})
    @patch("research_intelligence.tasks.step_4_screening.full_text.reclaim_ram")
    @patch("research_intelligence.tasks.step_4_screening.full_text.screen_full_text")
    def test_full_text_screening_chunking_and_memory_reclamation(self, mock_screen, mock_reclaim):
        """Verifies that full-text screening chunks papers and invokes reclaim_ram after each batch."""
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="full_text_screening",
            component_name="full_text_screening",
            status="pending"
        )

        for i in range(5):
            p = Paper.objects.create(
                workspace=self.workspace,
                title=f"Full Text Paper {i}",
                hash_id=f"ft_hash_{i}",
                pipeline_run=self.pipeline_run,
                original_pdf_path=f"workspaces/test/{i}/original.pdf"
            )

        mock_screen.return_value = {
            "success": True,
            "screening_status": "full_text_passed",
            "passed": True,
            "reasoning": "Criteria matched",
            "evidence_quotes": ["Evidence quote 1"],
            "decision_category": "ACCEPTED",
            "input_source": "pdf",
            "duration_seconds": 0.2,
            "usage": {"tokens_in": 100, "tokens_out": 50}
        }

        success = execute_full_text_screening_job(str(comp_run.id), max_workers=1)
        self.assertTrue(success)

        comp_run.refresh_from_db()
        self.assertEqual(comp_run.status, "completed")
        self.assertEqual(comp_run.metrics["passed"], 5)
        # 5 papers with chunk size 2 -> 3 chunks -> 3 reclaim_ram invocations
        self.assertEqual(mock_reclaim.call_count, 3)
