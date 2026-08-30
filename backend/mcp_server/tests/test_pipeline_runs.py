from research_intelligence.models import PipelineRun, ComponentRun, Paper
from mcp_server.tools import (
    trigger_search_job_logic,
    trigger_pdf_download_job_logic,
    trigger_ocr_job_logic,
    trigger_screening_job_logic,
    trigger_extraction_job_logic,
    list_pipeline_runs_logic,
    get_pipeline_run_status_logic,
    get_component_run_status_logic,
    abort_job_logic,
    delete_pipeline_run_logic,
)
from .base import BaseMCPTestCase
from unittest.mock import patch, MagicMock


class MCPPipelineRunsTestCase(BaseMCPTestCase):
    def test_pipeline_run_scraping_job_lifecycle(self):
        pr = PipelineRun.objects.create(workspace=self.workspace)
        status_res = self.parse_res(get_pipeline_run_status_logic(self.admin, pipeline_run_id=str(pr.id)))
        self.assertEqual(status_res["status"], "pending")

        list_res = self.parse_res(list_pipeline_runs_logic(self.admin, workspace_id=str(self.workspace.id)))
        self.assertEqual(len(list_res), 1)

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
            date_range_days=30,
            query_prefix="quantum"
        ))
        self.assertTrue(res["success"])
        pr_id = res["pipeline_run_id"]
        pr = PipelineRun.objects.get(id=pr_id)
        comp_run = pr.component_runs.first()
        self.assertEqual(comp_run.input_params["query_prefix"], "quantum")
        self.assertEqual(comp_run.input_params["date_range_days"], 30)
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
            metrics={"total_fetched": 15, "total_created": 5, "duplicates_count": 10, "total_duplicates": 10}
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



