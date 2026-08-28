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
