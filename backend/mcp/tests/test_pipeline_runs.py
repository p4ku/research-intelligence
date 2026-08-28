import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from research_intelligence.models import Workspace, WorkspaceMember, PipelineRun, ComponentRun, Paper, ExtractionDefinition
from mcp.tools import (
    trigger_search_job_logic,
    trigger_pdf_download_job_logic,
    trigger_ocr_job_logic,
    trigger_screening_job_logic,
    trigger_extraction_job_logic,
    get_pipeline_run_status_logic,
    get_component_run_status_logic,
    abort_job_logic,
    list_pipeline_runs_logic,
    delete_pipeline_run_logic,
)

User = get_user_model()


class MCPPipelineRunsTestCase(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(username="pipe_admin", email="admin@schwarz.de", password="password")
        self.workspace = Workspace.objects.create(
            name="Pipeline Test WS",
            abstract_acceptance_criteria=["Quantum hardware"],
            screening_llm_model="google/gemini-3.7-flash"
        )
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.admin_user, role="admin")

    def test_pipeline_run_scraping_job_lifecycle(self):
        pr = PipelineRun.objects.create(workspace=self.workspace)
        status_res = json.loads(get_pipeline_run_status_logic(self.admin_user, pipeline_run_id=str(pr.id)))
        self.assertEqual(status_res["status"], "pending")

        list_res = json.loads(list_pipeline_runs_logic(self.admin_user, workspace_id=str(self.workspace.id)))
        self.assertEqual(len(list_res), 1)

    def test_abort_job(self):
        pr = PipelineRun.objects.create(workspace=self.workspace, status="running")
        cr = ComponentRun.objects.create(pipeline_run=pr, component_name="screening", status="running")

        abort_res = json.loads(abort_job_logic(self.admin_user, component_run_id=str(cr.id)))
        self.assertEqual(abort_res["status"], "success")
        cr.refresh_from_db()
        self.assertEqual(cr.status, "aborted")

    def test_delete_pipeline_run_mcp_tool(self):
        pr = PipelineRun.objects.create(workspace=self.workspace)
        p = Paper.objects.create(workspace=self.workspace, pipeline_run=pr, hash_id="del_hash_01", title="To Delete")

        del_res = json.loads(delete_pipeline_run_logic(self.admin_user, pipeline_run_id=str(pr.id)))
        self.assertEqual(del_res["status"], "success")
        self.assertFalse(PipelineRun.objects.filter(id=pr.id).exists())
        self.assertFalse(Paper.objects.filter(id=p.id).exists())
