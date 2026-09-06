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
from mcp_server.tools.pipeline_runs import delete_pipeline_run_logic
from mcp_server.tools.agents import delete_research_agent_logic

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
            exit_metrics="metric",
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
            pipeline_run=pr,
            paper=paper,
            signal_score=5.0,
            metrics_data={"trl_score": 5}
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

    def test_delete_run_preserves_document_registry_and_other_workspaces_files(self):
        """
        Validates that deleting Workspace 1's PipelineRun ONLY purges Workspace 1's folder.
        The global DocumentRegistry canonical files and Workspace 2's documents MUST REMAIN INTACT.
        """
        from research_intelligence.models import DocumentRegistry
        from research_intelligence.tasks.step_2_download.pdf_cache import register_document_pdf, try_reuse_cached_pdf

        pdf_binary = b"%PDF-1.4 Shared Quantum Review Document" * 40

        # 1. Workspace 1 (Run 10) downloads and registers paper
        ws1 = self.workspace
        run10 = PipelineRun.objects.create(workspace=ws1, triggered_by=self.admin_user, status="completed")
        ws1_file_path = default_storage.save(
            f"workspaces/{ws1.id}/runs/{run10.id}/documents/doc_shared_01/original.pdf",
            ContentFile(pdf_binary)
        )
        paper_ws1 = Paper.objects.create(
            workspace=ws1,
            pipeline_run=run10,
            hash_id="doc_shared_01",
            doi="10.1103/PhysRevLett.130.010401",
            arxiv_id="2401.33333",
            title="Shared Quantum Fault Tolerance Paper",
            original_pdf_path=ws1_file_path,
            source_database="arxiv"
        )
        doc_reg = register_document_pdf(paper_ws1, pdf_binary)
        canonical_cache_path = doc_reg.canonical_pdf_path

        # 2. Workspace 2 (Run 20) reuses the paper via DocumentRegistry fastpath
        ws2 = Workspace.objects.create(name="Second Independent Workspace")
        run20 = PipelineRun.objects.create(workspace=ws2, triggered_by=self.admin_user, status="running")
        paper_ws2 = Paper.objects.create(
            workspace=ws2,
            pipeline_run=run20,
            hash_id="doc_shared_ws2",
            arxiv_id="2401.33333",
            title="Shared Quantum Fault Tolerance Paper (WS2)",
            original_pdf_path="https://arxiv.org/pdf/2401.33333.pdf",
            source_database="arxiv"
        )
        ws2_target_path = f"workspaces/{ws2.id}/runs/{run20.id}/documents/doc_shared_ws2/original.pdf"
        reuse_res = try_reuse_cached_pdf(paper_ws2, ws2_target_path)
        self.assertIsNotNone(reuse_res)
        self.assertTrue(reuse_res["cache_hit"])
        self.assertTrue(default_storage.exists(ws2_target_path))

        # 3. Purge Workspace 1's PipelineRun
        res_str = delete_pipeline_run_logic(self.admin_user, str(run10.id))
        res = json.loads(res_str)
        self.assertEqual(res["status"], "success")

        # 4. Critical Isolation Verifications:
        # A. Workspace 1 run folder and paper records are deleted
        self.assertFalse(PipelineRun.objects.filter(id=run10.id).exists())
        self.assertFalse(Paper.objects.filter(id=paper_ws1.id).exists())
        self.assertFalse(default_storage.exists(ws1_file_path))

        # B. Global DocumentRegistry record and canonical storage file MUST STILL EXIST
        self.assertTrue(DocumentRegistry.objects.filter(id=doc_reg.id).exists())
        self.assertTrue(default_storage.exists(canonical_cache_path))

        # C. Workspace 2 storage file and Paper record MUST REMAIN FULLY INTACT
        self.assertTrue(Paper.objects.filter(id=paper_ws2.id).exists())
        self.assertTrue(default_storage.exists(ws2_target_path))
        paper_ws2.refresh_from_db()
        self.assertEqual(paper_ws2.original_pdf_path, ws2_target_path)

        # D. A NEW Workspace 3 can still reuse the document from DocumentRegistry with 0 network calls
        ws3 = Workspace.objects.create(name="Third Workspace")
        run30 = PipelineRun.objects.create(workspace=ws3, triggered_by=self.admin_user, status="running")
        paper_ws3 = Paper.objects.create(
            workspace=ws3,
            pipeline_run=run30,
            hash_id="doc_shared_ws3",
            arxiv_id="2401.33333",
            title="Shared Quantum Fault Tolerance Paper (WS3)",
            original_pdf_path="https://arxiv.org/pdf/2401.33333.pdf",
            source_database="arxiv"
        )
        ws3_target_path = f"workspaces/{ws3.id}/runs/{run30.id}/documents/doc_shared_ws3/original.pdf"
        ws3_reuse_res = try_reuse_cached_pdf(paper_ws3, ws3_target_path)
        self.assertIsNotNone(ws3_reuse_res)
        self.assertTrue(ws3_reuse_res["cache_hit"])
        self.assertTrue(default_storage.exists(ws3_target_path))

