import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    ComponentRun,
    Paper,
    ExtractionDefinition,
    Extraction,
    PaperMetric,
    NarrativeReport,
    ResearchAgentProcess
)
from research_intelligence.mcp.tools.pipeline_runs import delete_pipeline_run_logic
from research_intelligence.mcp.tools.agent_processes import delete_research_agent_logic

User = get_user_model()


class StoragePurgeAndDeleteLifecycleTestCase(TestCase):
    """
    Validates complete and cascaded purge lifecycle:
    1. delete_pipeline_run: removes DB records (PipelineRun, ComponentRun, Paper, Extraction, PaperMetric, NarrativeReport)
       AND recursively deletes all physical storage files (.pdf, .md, .json).
    2. delete_research_agent: purges the ResearchAgentProcess, underlying PipelineRun, and storage footprint.
    """

    def setUp(self):
        self.admin_user = User.objects.create_user(username="admin_cleaner", email="cleaner@example.com", password="password123")
        self.workspace = Workspace.objects.create(name="Storage Lifecycle Workspace")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.admin_user, role="admin")

    def test_delete_pipeline_run_cascading_purge(self):
        """
        Creates a full hierarchy of DB records and physical files, invokes delete_pipeline_run_logic,
        and verifies total DB and physical storage cleanup.
        """
        pr = PipelineRun.objects.create(workspace=self.workspace, triggered_by=self.admin_user, status="completed")
        comp = ComponentRun.objects.create(pipeline_run=pr, component_name="arxiv", step_type="search", status="completed")

        # Create physical storage files
        pdf_path = default_storage.save(f"workspaces/{self.workspace.id}/runs/{pr.id}/documents/hash_p1/original.pdf", ContentFile(b"%PDF-1.4 mock"))
        md_path = default_storage.save(f"workspaces/{self.workspace.id}/runs/{pr.id}/documents/hash_p1/ocr.md", ContentFile(b"# OCR text"))
        meta_path = default_storage.save(f"workspaces/{self.workspace.id}/runs/{pr.id}/documents/hash_p1/metadata.json", ContentFile(b"{}"))
        scrape_path = default_storage.save(f"workspaces/{self.workspace.id}/runs/{pr.id}/scrapes/arxiv/{comp.id}_raw.json", ContentFile(b"[]"))

        # Create database objects
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=pr,
            hash_id="hash_p1",
            title="Paper for Deletion",
            original_pdf_path=pdf_path,
            converted_md_path=md_path
        )
        ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Del Def",
            exit_metric="metric",
            system_prompt="Prompt",
            user_prompt_template="Template",
            response_schema={}
        )
        ext = Extraction.objects.create(
            workspace=self.workspace,
            paper=paper,
            extraction_definition=ext_def,
            category="metric",
            fields_data={"metric": "val"}
        )
        metric = PaperMetric.objects.create(
            workspace=self.workspace,
            paper=paper,
            trl_score=5
        )
        report = NarrativeReport.objects.create(
            workspace=self.workspace,
            pipeline_run=pr,
            title="Summary Report",
            content_markdown="# Weekly Summary"
        )

        pr_id_str = str(pr.id)
        res_str = delete_pipeline_run_logic(self.admin_user, pr_id_str)
        res = json.loads(res_str)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["pipeline_run_id"], pr_id_str)

        # Verify DB records deleted
        self.assertFalse(PipelineRun.objects.filter(id=pr.id).exists())
        self.assertFalse(ComponentRun.objects.filter(id=comp.id).exists())
        self.assertFalse(Paper.objects.filter(id=paper.id).exists())
        self.assertFalse(Extraction.objects.filter(id=ext.id).exists())
        self.assertFalse(PaperMetric.objects.filter(id=metric.id).exists())
        self.assertFalse(NarrativeReport.objects.filter(id=report.id).exists())

        # Verify physical files deleted from storage
        self.assertFalse(default_storage.exists(pdf_path))
        self.assertFalse(default_storage.exists(md_path))
        self.assertFalse(default_storage.exists(meta_path))
        self.assertFalse(default_storage.exists(scrape_path))

    def test_delete_research_agent_process_purge(self):
        """
        Creates a ResearchAgentProcess with an associated PipelineRun, triggers delete_research_agent_logic,
        and ensures both agent state and pipeline storage are purged.
        """
        pr = PipelineRun.objects.create(workspace=self.workspace, triggered_by=self.admin_user, status="completed")
        agent = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=pr,
            triggered_by=self.admin_user,
            name="Purge Agent",
            status="completed"
        )

        agent_file_path = default_storage.save(
            f"workspaces/{self.workspace.id}/runs/{pr.id}/documents/hash_agent/original.pdf",
            ContentFile(b"%PDF-binary")
        )

        agent_id_str = str(agent.id)
        res_str = delete_research_agent_logic(self.admin_user, agent_id_str)
        res = json.loads(res_str)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["process_id"], agent_id_str)

        # Verify DB records purged
        self.assertFalse(ResearchAgentProcess.objects.filter(id=agent.id).exists())
        self.assertFalse(PipelineRun.objects.filter(id=pr.id).exists())

        # Verify storage purged
        self.assertFalse(default_storage.exists(agent_file_path))
