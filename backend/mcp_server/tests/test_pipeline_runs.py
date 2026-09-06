from research_intelligence.models import PipelineRun, ComponentRun, Paper
from mcp_server.tools import (
    trigger_search_job_logic,
    start_pipeline_run_logic,
    trigger_pdf_download_job_logic,
    trigger_ocr_job_logic,
    trigger_screening_job_logic,
    trigger_extraction_job_logic,
    send_pipeline_run_digest_email_logic,
    list_pipeline_runs_logic,
    get_pipeline_run_status_logic,
    get_component_run_status_logic,
    pause_pipeline_run_logic,
    resume_pipeline_run_logic,
    tick_pipeline_run_logic,
    abort_job_logic,
    delete_pipeline_run_logic,
    rerun_pipeline_from_step_logic,
    reexecute_component_run_logic,
)
from datetime import timedelta
from django.utils import timezone
from .base import BaseMCPTestCase
from unittest.mock import patch, MagicMock


class MCPPipelineRunsTestCase(BaseMCPTestCase):
    def test_pipeline_run_scraping_job_lifecycle(self):
        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            reprocess_existing=True,
            status_message="Initial ingestion pending"
        )
        status_res = self.parse_res(get_pipeline_run_status_logic(self.admin, pipeline_run_id=str(pr.id)))
        self.assertEqual(status_res["status"], "pending")
        self.assertTrue(status_res["reprocess_existing"])
        self.assertEqual(status_res["status_message"], "Initial ingestion pending")
        self.assertIsNone(status_res["schedule_id"])

        list_res = self.parse_res(list_pipeline_runs_logic(self.admin, workspace_id=str(self.workspace.id)))
        self.assertEqual(len(list_res), 1)
        self.assertTrue(list_res[0]["reprocess_existing"])
        self.assertEqual(list_res[0]["status_message"], "Initial ingestion pending")

    def test_abort_job(self):
        pr = PipelineRun.objects.create(workspace=self.workspace, status="running")
        cr = ComponentRun.objects.create(pipeline_run=pr, component_name="screening", status="running")

        abort_res = self.parse_res(abort_job_logic(self.admin, component_run_id=str(cr.id)))
        self.assertEqual(abort_res["status"], "success")
        cr.refresh_from_db()
        self.assertEqual(cr.status, "aborted")

    def test_delete_pipeline_run_mcp_tool(self):
        pr = PipelineRun.objects.create(workspace=self.workspace)
        p = Paper.objects.create(workspace=self.workspace, pipeline_run=pr, hash_id="del_hash_01", title="To Delete")

        del_res = self.parse_res(delete_pipeline_run_logic(self.admin, pipeline_run_id=str(pr.id)))
        self.assertEqual(del_res["status"], "success")
        self.assertFalse(PipelineRun.objects.filter(id=pr.id).exists())
        self.assertFalse(Paper.objects.filter(id=p.id).exists())

    @patch("mcp_server.tools.pipeline_runs.triggers.execute_screening_job.delay")
    @patch("mcp_server.tools.pipeline_runs.triggers.execute_full_text_screening_job.delay")
    def test_trigger_screening_job_stages(self, mock_full_text, mock_abstract):
        mock_abstract.return_value = MagicMock(id="celery_task_abs_01")
        mock_full_text.return_value = MagicMock(id="celery_task_ft_01")

        pr = PipelineRun.objects.create(workspace=self.workspace)
        Paper.objects.create(workspace=self.workspace, pipeline_run=pr, hash_id="hash_scr_01", title="Screening Paper 1")

        # 1. Abstract Stage (default)
        abs_res = self.parse_res(trigger_screening_job_logic(self.admin, pipeline_run_id=str(pr.id), stage="abstract"))
        self.assertTrue(abs_res["success"])
        self.assertEqual(abs_res["stage"], "abstract")
        self.assertEqual(abs_res["celery_task_id"], "celery_task_abs_01")
        mock_abstract.assert_called_once()

        # 2. Full-Text Stage
        ft_res = self.parse_res(trigger_screening_job_logic(self.admin, pipeline_run_id=str(pr.id), stage="full_text"))
        self.assertTrue(ft_res["success"])
        self.assertEqual(ft_res["stage"], "full_text")
        self.assertEqual(ft_res["celery_task_id"], "celery_task_ft_01")
        mock_full_text.assert_called_once()

    def test_list_pipeline_runs_with_limit(self):
        pr1 = PipelineRun.objects.create(workspace=self.workspace)
        pr2 = PipelineRun.objects.create(workspace=self.workspace)
        pr3 = PipelineRun.objects.create(workspace=self.workspace)

        list_res = self.parse_res(list_pipeline_runs_logic(self.admin, workspace_id=str(self.workspace.id), limit=2))
        self.assertEqual(len(list_res), 2)

    @patch("mcp_server.tools.pipeline_runs.triggers.execute_scraper_run_job.delay")
    def test_trigger_search_job_with_date_range_and_prefix(self, mock_scrape_task):
        mock_scrape_task.return_value = MagicMock(id="celery_scrape_01")
        from research_intelligence.models import Scraper
        scraper = Scraper.objects.create(workspace=self.workspace, provider="arxiv", search_query="transformer attention", is_active=True)

        res = self.parse_res(trigger_search_job_logic(
            self.admin,
            workspace_id=str(self.workspace.id),
            scraper_id=str(scraper.id),
            limit=25,
            n_last_days=30,
            query_prefix="quantum"
        ))
        self.assertTrue(res["success"])
        pr_id = res["pipeline_run_id"]
        pr = PipelineRun.objects.get(id=pr_id)
        comp_run = pr.component_runs.first()
        self.assertEqual(comp_run.input_params["query_prefix"], "quantum")
        self.assertEqual(comp_run.input_params["n_last_days"], 30)
        self.assertEqual(comp_run.input_params["search_query"], "quantum transformer attention")

    @patch("research_intelligence.tasks.auxiliary.email_digest.dispatch_pipeline_subscriber_digest")
    def test_trigger_reporting_job(self, mock_digest):
        mock_digest.return_value = {"status": "success", "emails_sent": 3, "subscribers_count": 3}
        from mcp_server.tools.pipeline_runs.triggers import trigger_reporting_job_logic

        pr = PipelineRun.objects.create(workspace=self.workspace, status="running")
        res = self.parse_res(trigger_reporting_job_logic(self.admin, pipeline_run_id=str(pr.id)))
        self.assertTrue(res["success"])
        mock_digest.assert_called_once()
        pr.refresh_from_db()
        self.assertEqual(pr.status, "completed")

    def test_status_sync_preserves_running_when_agent_process_active(self):
        """get_pipeline_run_status must not mark a run as completed when an active agent process is driving it."""
        from research_intelligence.models import ResearchAgentProcess
        pr = PipelineRun.objects.create(workspace=self.workspace, status="running")
        ComponentRun.objects.create(pipeline_run=pr, step_type="search", status="completed")
        agent_proc = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=pr,
            status="running",
            current_step="download"
        )

        status_res = self.parse_res(get_pipeline_run_status_logic(self.admin, pipeline_run_id=str(pr.id)))
        pr.refresh_from_db()
        self.assertEqual(pr.status, "running")
        self.assertEqual(status_res["status"], "running")

    def test_delete_pipeline_run_with_storage_and_cascade(self):
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        from research_intelligence.models import Extraction, PaperMetric, NarrativeReport

        pr = PipelineRun.objects.create(workspace=self.workspace, status="completed")
        p = Paper.objects.create(workspace=self.workspace, pipeline_run=pr, hash_id="hash_del_test", title="Delete Target Paper")
        file_path = f"workspaces/{self.workspace.id}/runs/{pr.id}/test_doc.pdf"
        default_storage.save(file_path, ContentFile(b"%PDF-1.4 test binary"))
        self.assertTrue(default_storage.exists(file_path))

        cr = ComponentRun.objects.create(pipeline_run=pr, step_type="search", status="completed")
        ext = Extraction.objects.create(workspace=self.workspace, paper=p, category="test", fields_data={"val": 1})
        pm = PaperMetric.objects.create(workspace=self.workspace, paper=p, pipeline_run=pr, signal_score=9.5)
        nr = NarrativeReport.objects.create(workspace=self.workspace, pipeline_run=pr, title="Report", content_markdown="Summary")

        del_res = self.parse_res(delete_pipeline_run_logic(self.admin, pipeline_run_id=str(pr.id)))
        self.assertTrue(del_res["success"])
        self.assertEqual(del_res["status"], "success")
        self.assertFalse(PipelineRun.objects.filter(id=pr.id).exists())
        self.assertFalse(Paper.objects.filter(id=p.id).exists())
        self.assertFalse(ComponentRun.objects.filter(id=cr.id).exists())
        self.assertFalse(Extraction.objects.filter(id=ext.id).exists())
        self.assertFalse(PaperMetric.objects.filter(id=pm.id).exists())
        self.assertFalse(NarrativeReport.objects.filter(id=nr.id).exists())
        self.assertFalse(default_storage.exists(file_path))

    def test_pipeline_run_status_and_agent_status_duplicates_reporting(self):
        from research_intelligence.models import ResearchAgentProcess
        from mcp_server.tools.agents.processes import check_run_status_logic
        from api.serializers.pipeline_runs import PipelineRunDetailSerializer

        pr = PipelineRun.objects.create(workspace=self.workspace, status="running", current_stage="download", total_papers_fetched=5)
        ComponentRun.objects.create(
            pipeline_run=pr,
            step_type="search",
            component_name="arxiv_scraper",
            status="completed",
            metrics={"total_fetched": 15, "total_created": 5, "duplicates_count": 10}
        )

        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=pr,
            name="Duplicates Test Agent",
            status="running",
            current_step="download"
        )

        # 1. Test get_pipeline_run_status_logic
        status_res = self.parse_res(get_pipeline_run_status_logic(self.admin, pipeline_run_id=str(pr.id)))
        self.assertEqual(status_res["total_papers_fetched"], 5)
        self.assertEqual(status_res["duplicates_count"], 10)

        # 2. Test check_run_status_logic (MCP summary card & timeline)
        agent_status_res = self.parse_res(check_run_status_logic(self.admin, process_id=str(agent.id)))
        self.assertEqual(agent_status_res["paper_metrics"]["total_papers_fetched"], 5)
        self.assertEqual(agent_status_res["paper_metrics"]["duplicates_count"], 10)
        self.assertIn("Duplicates (Skipped)**: 10", agent_status_res["summary_markdown"])

        # 3. Test DRF API Serializer
        serializer = PipelineRunDetailSerializer(pr)
        self.assertEqual(serializer.data["duplicates_count"], 10)

    def test_pipeline_run_linked_to_schedule_mcp_representation(self):
        from research_intelligence.models import WorkflowSchedule
        schedule = WorkflowSchedule.objects.create(
            workspace=self.workspace,
            name="Weekly Ingestion Schedule",
            frequency="weekly",
            is_active=True
        )
        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            schedule=schedule,
            status="running",
            current_stage="search"
        )
        status_res = self.parse_res(get_pipeline_run_status_logic(self.admin, pipeline_run_id=str(pr.id)))
        self.assertEqual(status_res["schedule_id"], str(schedule.id))
        self.assertEqual(status_res["schedule_name"], "Weekly Ingestion Schedule")

        list_res = self.parse_res(list_pipeline_runs_logic(self.admin, workspace_id=str(self.workspace.id)))
        matched = next(r for r in list_res if r["pipeline_run_id"] == str(pr.id))
        self.assertEqual(matched["schedule_id"], str(schedule.id))
        self.assertEqual(matched["schedule_name"], "Weekly Ingestion Schedule")

    @patch("mcp_server.tools.pipeline_runs.triggers.execute_pdf_download_job.delay")
    def test_trigger_pdf_download_job(self, mock_dl_task):
        mock_dl_task.return_value = MagicMock(id="celery_dl_task_01")
        pr = PipelineRun.objects.create(workspace=self.workspace, status="running")
        Paper.objects.create(workspace=self.workspace, pipeline_run=pr, hash_id="h_dl_1", title="DL Paper", original_pdf_path="https://example.com/p.pdf")

        res = self.parse_res(trigger_pdf_download_job_logic(self.admin, pipeline_run_id=str(pr.id), limit=10))
        self.assertTrue(res["success"])
        self.assertEqual(res["celery_task_id"], "celery_dl_task_01")
        mock_dl_task.assert_called_once()

    @patch("mcp_server.tools.pipeline_runs.triggers.execute_ocr_job.delay")
    def test_trigger_ocr_job(self, mock_ocr_task):
        mock_ocr_task.return_value = MagicMock(id="celery_ocr_task_01")
        pr = PipelineRun.objects.create(workspace=self.workspace, status="running")
        Paper.objects.create(workspace=self.workspace, pipeline_run=pr, hash_id="h_ocr_1", title="OCR Paper", original_pdf_path="workspaces/1/runs/1/doc.pdf")

        res = self.parse_res(trigger_ocr_job_logic(self.admin, pipeline_run_id=str(pr.id), limit=5))
        self.assertTrue(res["success"])
        self.assertEqual(res["celery_task_id"], "celery_ocr_task_01")
        mock_ocr_task.assert_called_once()

    @patch("mcp_server.tools.pipeline_runs.triggers.execute_extraction_job.delay")
    def test_trigger_extraction_job(self, mock_ext_task):
        from research_intelligence.models import ExtractionDefinition
        mock_ext_task.return_value = MagicMock(id="celery_ext_task_01")
        ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Test Extraction Def",
            system_prompt="Extract parameters",
            user_prompt_template="{paper_text}",
            response_schema={"type": "object"},
            is_active=True
        )
        pr = PipelineRun.objects.create(workspace=self.workspace, status="running")
        Paper.objects.create(workspace=self.workspace, pipeline_run=pr, hash_id="h_ext_1", title="Extraction Paper")

        res = self.parse_res(trigger_extraction_job_logic(self.admin, pipeline_run_id=str(pr.id), limit=15))
        self.assertTrue(res["success"])
        self.assertEqual(res["celery_task_id"], "celery_ext_task_01")
        mock_ext_task.assert_called_once()

    @patch("mcp_server.tools.diagnostics.email.send_pipeline_subscriber_digest_task.delay")
    def test_send_pipeline_run_digest_email_with_recipient_override(self, mock_email_task):
        mock_email_task.return_value = MagicMock(id="celery_email_task_01")
        pr = PipelineRun.objects.create(workspace=self.workspace, status="completed")

        res = self.parse_res(send_pipeline_run_digest_email_logic(
            self.admin,
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(pr.id),
            recipient_override=["lead@corp.com", "analyst@corp.com"],
            async_dispatch=True
        ))
        self.assertEqual(res["status"], "queued")
        self.assertEqual(res["celery_task_id"], "celery_email_task_01")
        mock_email_task.assert_called_once_with(
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(pr.id),
            recipient_override=["lead@corp.com", "analyst@corp.com"]
        )

    def test_get_pipeline_run_status_active_progressing_guidance(self):
        """
        Verifies that when a component run is actively progressing (recent heartbeat),
        is_progressing is True, is_stalled is False, and AI guidance instructs
        not to modify source code.
        """
        from datetime import timedelta
        from django.utils import timezone
        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="extraction"
        )
        ComponentRun.objects.create(
            pipeline_run=pr,
            step_type="extraction",
            component_name="extraction",
            status="running",
            metrics={
                "total_work_items": 130,
                "completed_extractions": 55,
                "failed_extractions": 0,
                "percent_complete": 42.3,
                "latest_processed": "[PASSED] TRL Assessment: Quantum Paper",
                "last_progress_at": (timezone.now() - timedelta(seconds=15)).isoformat()
            }
        )

        res = self.parse_res(get_pipeline_run_status_logic(self.admin, pipeline_run_id=str(pr.id)))
        self.assertTrue(res["is_in_progress"])
        self.assertTrue(res["is_progressing"])
        self.assertFalse(res["is_stalled"])
        self.assertEqual(res["active_progress"]["items_completed"], 55)
        self.assertEqual(res["active_progress"]["items_total"], 130)
        self.assertEqual(res["active_progress"]["percent_complete"], 42.3)
        self.assertIn("DO NOT MODIFY SOURCE CODE", res["guidance_for_ai"])
        self.assertIn("55/130 items (42.3%)", res["active_progress"]["progress_summary"])

    def test_get_pipeline_run_status_stalled_guidance(self):
        """
        Verifies that when a component run has had no progress for > 3 minutes,
        is_stalled is True, is_progressing is False, and AI guidance warns about
        the stall without telling the AI to touch code.
        """
        from datetime import timedelta
        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="extraction"
        )
        ComponentRun.objects.create(
            pipeline_run=pr,
            step_type="extraction",
            component_name="extraction",
            status="running",
            metrics={
                "total_work_items": 130,
                "completed_extractions": 55,
                "failed_extractions": 0,
                "percent_complete": 42.3,
                "latest_processed": "[PASSED] TRL Assessment: Quantum Paper",
                "last_progress_at": (timezone.now() - timedelta(minutes=12)).isoformat()
            }
        )

        res = self.parse_res(get_pipeline_run_status_logic(self.admin, pipeline_run_id=str(pr.id)))
        self.assertTrue(res["is_in_progress"])
        self.assertFalse(res["is_progressing"])
        self.assertTrue(res["is_stalled"])
        self.assertGreaterEqual(res["active_progress"]["stalled_minutes"], 11.9)
        self.assertIn("STALLED WARNING", res["guidance_for_ai"])
        self.assertIn("DO NOT EDIT OR MODIFY SOURCE CODE", res["guidance_for_ai"])

    @patch("research_intelligence.tasks.orchestrator.runner.PipelineRunner.tick")
    def test_start_pipeline_run_mcp_tool(self, mock_tick):
        mock_tick.return_value = {"success": True, "status": "running", "current_stage": "search"}
        res = self.parse_res(start_pipeline_run_logic(
            self.admin,
            workspace_id=str(self.workspace.id),
            name="Quantum Autonomous Run",
            limit=20,
            n_last_days=14,
            query_prefix="qubit",
            reprocess_existing=True
        ))
        self.assertEqual(res["status"], "success")
        self.assertIn("pipeline_run_id", res)
        pr_id = res["pipeline_run_id"]
        pr = PipelineRun.objects.get(id=pr_id)
        self.assertEqual(pr.name, "Quantum Autonomous Run")
        self.assertEqual(pr.status, "running")
        self.assertTrue(pr.configuration_override.get("autonomous"))
        self.assertEqual(pr.configuration_override.get("limit"), 20)
        self.assertTrue(pr.configuration_override.get("reprocess_existing"))

    @patch("research_intelligence.tasks.orchestrator.runner.PipelineRunner.tick")
    def test_start_pipeline_run_mcp_tool_with_date_range(self, mock_tick):
        mock_tick.return_value = {"success": True, "status": "running", "current_stage": "search"}
        res = self.parse_res(start_pipeline_run_logic(
            self.admin,
            workspace_id=str(self.workspace.id),
            name="Date Range Run",
            start_date="2026-08-01",
            end_date="2026-08-15",
            n_last_days=10
        ))
        self.assertEqual(res["status"], "success")
        pr_id = res["pipeline_run_id"]
        pr = PipelineRun.objects.get(id=pr_id)
        self.assertEqual(pr.configuration_override.get("start_date"), "2026-08-01")
        self.assertEqual(pr.configuration_override.get("end_date"), "2026-08-15")
        self.assertEqual(pr.configuration_override.get("n_last_days"), 10)

    @patch("research_intelligence.tasks.step_1_search.search.execute_scraper_run_job.delay")
    def test_trigger_search_job_mcp_tool_with_date_range(self, mock_delay):
        from research_intelligence.models import Scraper
        mock_delay.return_value = MagicMock(id="task_123")
        Scraper.objects.get_or_create(
            workspace=self.workspace,
            provider="arxiv",
            defaults={"search_query": "machine learning", "is_active": True}
        )
        res = self.parse_res(trigger_search_job_logic(
            self.admin,
            workspace_id=str(self.workspace.id),
            start_date="2026-07-01",
            end_date="2026-07-10",
            n_last_days=5
        ))
        self.assertTrue(res["success"])
        pr_id = res["pipeline_run_id"]
        pr = PipelineRun.objects.get(id=pr_id)
        self.assertEqual(pr.configuration_override.get("start_date"), "2026-07-01")
        self.assertEqual(pr.configuration_override.get("end_date"), "2026-07-10")
        self.assertEqual(pr.configuration_override.get("n_last_days"), 5)
        cr = ComponentRun.objects.filter(pipeline_run=pr, step_type="search").first()
        self.assertIsNotNone(cr)
        self.assertEqual(cr.input_params.get("start_date"), "2026-07-01")
        self.assertEqual(cr.input_params.get("end_date"), "2026-07-10")
        self.assertEqual(cr.input_params.get("n_last_days"), 5)

    def test_pause_resume_tick_pipeline_run_mcp_tools(self):
        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="download"
        )
        # 1. Pause
        pause_res = self.parse_res(pause_pipeline_run_logic(self.admin, pipeline_run_id=str(pr.id), reason="Paused via test"))
        self.assertEqual(pause_res["status"], "success")
        pr.refresh_from_db()
        self.assertEqual(pr.status, "paused")

        # 2. Resume
        with patch("research_intelligence.tasks.orchestrator.agent_engine.notify_pipeline_orchestrator_tick") as mock_notify:
            resume_res = self.parse_res(resume_pipeline_run_logic(self.admin, pipeline_run_id=str(pr.id)))
            self.assertEqual(resume_res["status"], "success")
            pr.refresh_from_db()
            self.assertEqual(pr.status, "running")
            mock_notify.assert_called_once()

        # 3. Tick
        with patch("research_intelligence.tasks.orchestrator.runner.PipelineRunner.tick") as mock_tick:
            mock_tick.return_value = {"success": True, "status": "running", "current_stage": "download"}
            tick_res = self.parse_res(tick_pipeline_run_logic(self.admin, pipeline_run_id=str(pr.id)))
            self.assertEqual(tick_res["status"], "success")
            mock_tick.assert_called_once_with(pr.id)

    @patch("research_intelligence.tasks.orchestrator.agent_engine.notify_pipeline_orchestrator_tick")
    def test_rerun_pipeline_from_step_explicit(self, mock_notify):
        """Validates that rerun_pipeline_from_step resets downstream nodes from an explicitly specified step."""
        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            current_stage="reporting"
        )
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pr,
            hash_id="p_test_rerun_explicit",
            title="Quantum Paper",
            authors="Test Author",
            abstract="Test Abstract",
            source_database="arxiv",
            screening_status="accepted"
        )
        # Create completed components for search, screening, download, ocr
        c_search = ComponentRun.objects.create(pipeline_run=pr, step_type="search", component_name="search", status="completed")
        c_screen = ComponentRun.objects.create(pipeline_run=pr, step_type="screening", component_name="abstract_screening", status="completed")
        c_download = ComponentRun.objects.create(pipeline_run=pr, step_type="download", component_name="download", status="completed")
        c_ocr = ComponentRun.objects.create(pipeline_run=pr, step_type="ocr", component_name="ocr", status="completed")

        res = self.parse_res(rerun_pipeline_from_step_logic(self.admin, pipeline_run_id=str(pr.id), step_name="download"))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["resumed_from_step"], "download")

        pr.refresh_from_db()
        self.assertEqual(pr.status, "running")
        self.assertEqual(pr.current_stage, "download")

        # Upstream components (search, screening) must remain intact
        self.assertTrue(ComponentRun.objects.filter(id=c_search.id).exists())
        self.assertTrue(ComponentRun.objects.filter(id=c_screen.id).exists())

        # Target node and downstream nodes (download, ocr) must be reset/deleted for fresh execution
        self.assertFalse(ComponentRun.objects.filter(id=c_download.id).exists())
        self.assertFalse(ComponentRun.objects.filter(id=c_ocr.id).exists())
        mock_notify.assert_called()

    @patch("research_intelligence.tasks.orchestrator.agent_engine.notify_pipeline_orchestrator_tick")
    def test_rerun_pipeline_auto_detect_failed_step(self, mock_notify):
        """Validates that rerun_pipeline_from_step automatically detects and resumes from the failed stage when step_name is omitted."""
        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            status="failed",
            current_stage="download",
            stopped_at_stage="download"
        )
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pr,
            hash_id="p_test_rerun_auto",
            title="Quantum Paper Auto",
            authors="Test Author",
            abstract="Test Abstract",
            source_database="arxiv",
            screening_status="accepted"
        )
        c_search = ComponentRun.objects.create(pipeline_run=pr, step_type="search", component_name="search", status="completed")
        c_screen = ComponentRun.objects.create(pipeline_run=pr, step_type="screening", component_name="abstract_screening", status="completed")
        c_failed_download = ComponentRun.objects.create(pipeline_run=pr, step_type="download", component_name="download", status="failed", error_message="Network timeout")

        # Call with step_name=None -> should auto-detect 'download'
        res = self.parse_res(rerun_pipeline_from_step_logic(self.admin, pipeline_run_id=str(pr.id), step_name=None))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["resumed_from_step"], "download")

        pr.refresh_from_db()
        self.assertEqual(pr.status, "running")
        self.assertEqual(pr.current_stage, "download")
        self.assertIsNone(pr.stopped_at_stage)
        mock_notify.assert_called()

    @patch("research_intelligence.tasks.orchestrator.dag.DownloadNode.execute")
    def test_reexecute_component_run_mcp_tool(self, mock_execute):
        """Validates that reexecute_component_run re-dispatches an isolated failed component without touching others."""
        pr = PipelineRun.objects.create(
            workspace=self.workspace,
            status="failed",
            current_stage="download"
        )
        cr = ComponentRun.objects.create(
            pipeline_run=pr,
            step_type="download",
            component_name="download",
            status="failed",
            error_message="Simulated worker SIGKILL"
        )

        res = self.parse_res(reexecute_component_run_logic(self.admin, component_run_id=str(cr.id)))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["component_run_id"], str(cr.id))

        cr.refresh_from_db()
        self.assertEqual(cr.status, "running")
        self.assertEqual(cr.error_message, "")
        mock_execute.assert_called_once()





