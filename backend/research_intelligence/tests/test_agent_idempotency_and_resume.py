import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    Paper,
    PaperMetric,
    PipelineRun,
    ComponentRun,
    ResearchAgentProcess
)
from mcp_server.tools.agents import (
    start_research_agent_logic,
    get_research_agent_status_logic,
    pause_research_agent_logic,
    resume_research_agent_logic,
    abort_research_agent_logic,
)
from research_intelligence.tasks.orchestrator.agent_engine import notify_pipeline_orchestrator_tick
from research_intelligence.tasks.step_2_download.fetch import _download_paper_task
from research_intelligence.tasks.step_3_ocr.convert import run_ocr_conversion

User = get_user_model()


class AgentIdempotencyAndResumeTestCase(TestCase):
    """
    Tests state engine transitions, idempotency, and task resumption:
    1. Pause / Resume / Abort state machine transitions for ResearchAgentProcess.
    2. Idempotent Step 2 PDF download (skips downloading if file already exists in storage).
    3. Idempotent Step 3 OCR conversion (skips conversion if markdown already exists).
    4. Resumption from active step without duplicating existing files or database records.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="lead_scientist", email="lead@example.com", password="password123")
        self.workspace = Workspace.objects.create(
            name="Idempotency Workspace",
            ocr_provider="pypdf",
            screening_llm_model="google/gemini-3.8-flash"
        )
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            triggered_by=self.user,
            status="running"
        )
        self.agent_process = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            triggered_by=self.user,
            name="Autonomous Review Agent",
            status="running",
            current_step="search"
        )

        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="search",
            component_name="arxiv_scraper",
            status="completed"
        )

        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_idem_001",
            title="Idempotent State Machines in Autonomous Agents",
            abstract="We explore fault recovery in distributed agent state engines.",
            original_pdf_path="https://arxiv.org/pdf/2401.00001.pdf"
        )
        PaperMetric.objects.create(paper=self.paper, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="pending")

    def test_pause_resume_abort_state_engine_transitions(self):
        """
        Validates state transitions: running -> paused -> running -> aborted.
        """
        # 1. Pause running agent
        pause_res = json.loads(pause_research_agent_logic(self.user, str(self.agent_process.id)))
        self.assertEqual(pause_res["status"], "success")
        self.assertEqual(pause_res["agent_status"], "paused")

        self.agent_process.refresh_from_db()
        self.assertEqual(self.agent_process.status, "paused")

        # 2. Status inspection shows paused state
        status_res = json.loads(get_research_agent_status_logic(self.user, str(self.agent_process.id)))
        self.assertEqual(status_res["status"], "paused")
        self.assertEqual(status_res["current_step"], "search")

        # 3. Resume paused agent
        with patch("research_intelligence.tasks.step_4_screening.abstract.execute_screening_job.delay") as mock_screening:
            mock_screening.return_value.id = "mock_task_id_123"
            resume_res = json.loads(resume_research_agent_logic(self.user, str(self.agent_process.id)))
            self.assertEqual(resume_res["status"], "success")
            self.assertEqual(resume_res["agent_status"], "running")

            self.agent_process.refresh_from_db()
            self.assertEqual(self.agent_process.status, "running")
            # Resuming at completed search triggers transition to 'abstract_screening' and launches screening job
            mock_screening.assert_called_once()

        # 4. Abort agent process
        abort_res = json.loads(abort_research_agent_logic(self.user, str(self.agent_process.id)))
        self.assertEqual(abort_res["status"], "success")
        self.assertEqual(abort_res["agent_status"], "aborted")

        self.agent_process.refresh_from_db()
        self.assertEqual(self.agent_process.status, "aborted")

    def test_idempotent_step_2_pdf_download_skips_existing(self):
        """
        Ensures that if a paper PDF already exists in storage, the download task
        skips downloading from network and returns already_exists=True.
        """
        doc_folder = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{self.paper.hash_id}"
        expected_pdf_path = f"{doc_folder}/original.pdf"
        default_storage.save(expected_pdf_path, ContentFile(b"%PDF-1.4 mock pdf data"))

        with patch("requests.get") as mock_http_get:
            result = _download_paper_task(self.paper, self.workspace, self.pipeline_run)
            self.assertEqual(result["status"], "already_exists")
            self.assertEqual(result["storage_path"], expected_pdf_path)
            mock_http_get.assert_not_called()

        self.paper.refresh_from_db()
        self.assertEqual(self.paper.original_pdf_path, expected_pdf_path)

    def test_idempotent_step_3_ocr_conversion_skips_existing(self):
        """
        Ensures that if an OCR Markdown file already exists in storage, OCR task
        skips conversion and immediately returns already_exists=True.
        """
        doc_folder = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{self.paper.hash_id}"
        expected_pdf_path = f"{doc_folder}/original.pdf"
        expected_md_path = f"{doc_folder}/ocr.md"

        default_storage.save(expected_pdf_path, ContentFile(b"%PDF-1.4 mock binary"))
        default_storage.save(expected_md_path, ContentFile(b"# Cached OCR Document Content"))

        self.paper.original_pdf_path = expected_pdf_path
        self.paper.save(update_fields=['original_pdf_path'])

        with patch("research_intelligence.tasks.step_3_ocr.convert.get_ocr_provider") as mock_get_ocr:
            result = run_ocr_conversion(self.paper.id, paper_obj=self.paper)
            self.assertTrue(result["success"])
            self.assertTrue(result.get("already_exists"))
            self.assertEqual(result["storage_path"], expected_md_path)
            # OCR engine was not instantiated because cached markdown was discovered
            mock_get_ocr.assert_not_called()

        self.paper.refresh_from_db()
        self.assertEqual(self.paper.converted_md_path, expected_md_path)
