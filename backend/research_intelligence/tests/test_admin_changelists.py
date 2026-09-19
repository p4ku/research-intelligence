from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from research_intelligence.models import (
    Workspace,
    PipelineRun,
    ComponentRun,
    ResearchAgentProcess,
    DocumentRegistry,
    Paper,
    PaperMetric,
    ExtractionDefinition,
    Extraction,
    UserActivityLog,
    APIKey
)

User = get_user_model()


class AdminChangelistViewsTestCase(TestCase):
    """
    Validates that all Django Admin changelist and detail change forms render
    flawlessly with status code 200 and without any template formatting or SafeString errors.
    """

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="test_admin_reviewer",
            email="reviewer@example.com",
            password="adminpassword123!"
        )
        self.client.force_login(self.user)

        self.workspace = Workspace.objects.create(
            name="Quantum Computing Intelligence",
            screening_llm_model="google/gemini-3.8-flash",
            abstract_acceptance_criteria="Quantum processors",
            abstract_rejection_criteria="Classical only"
        )

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            current_stage="completed",
            usd_cost=Decimal("0.0452"),
            tokens_in=35000,
            tokens_out=4500,
            tokens_consumed=39500,
            started_at=timezone.now() - timezone.timedelta(minutes=5),
            completed_at=timezone.now()
        )

        self.comp_run_search = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            component_name="arxiv_scraper",
            step_type="search",
            status="completed",
            metrics={"total_fetched": 24, "total_duplicates_skipped": 3},
            started_at=timezone.now() - timezone.timedelta(minutes=5),
            completed_at=timezone.now() - timezone.timedelta(minutes=4)
        )

        self.comp_run_download = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            component_name="pdf_downloader",
            step_type="download",
            status="completed",
            metrics={"downloaded": 21, "failed": 0, "cached_hits": 5},
            started_at=timezone.now() - timezone.timedelta(minutes=4),
            completed_at=timezone.now() - timezone.timedelta(minutes=3)
        )

        self.comp_run_screening = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            component_name="abstract_screening",
            step_type="screening",
            status="completed",
            metrics={
                "total_screened": 21,
                "passed": 13,
                "rejected": 8,
                "tokens_in": 16000,
                "tokens_out": 2100,
                "total_tokens": 18100,
                "usd_cost": 0.0183
            },
            started_at=timezone.now() - timezone.timedelta(minutes=3),
            completed_at=timezone.now() - timezone.timedelta(minutes=2)
        )

        self.comp_run_extraction = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            component_name="parameter_extraction",
            step_type="extraction",
            status="completed",
            metrics={
                "extractions_created": 65,
                "total_papers": 13,
                "total_definitions": 5,
                "tokens_in": 19000,
                "tokens_out": 2400,
                "total_tokens": 21400,
                "usd_cost": 0.0269
            },
            started_at=timezone.now() - timezone.timedelta(minutes=2),
            completed_at=timezone.now() - timezone.timedelta(minutes=1)
        )

        self.comp_run_signal_score = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            component_name="signal_score_evaluation",
            step_type="signal_score",
            status="completed",
            metrics={
                "total_papers": 13,
                "scored_count": 13,
                "avg_signal_score": 35.04615384615385,
                "max_signal_score": 71.2,
                "min_signal_score": 0.0,
                "errors_count": 0,
                "errors": []
            },
            started_at=timezone.now() - timezone.timedelta(minutes=1),
            completed_at=timezone.now()
        )

        self.agent_process = ResearchAgentProcess.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            name="Autonomous Agent Process 1",
            status="completed",
            current_step="reporting",
            started_at=timezone.now() - timezone.timedelta(minutes=5),
            completed_at=timezone.now()
        )

        self.doc_registry = DocumentRegistry.objects.create(
            sha256_hash="abc123def45678901234567890abcdef1234567890abcdef1234567890abcdef",
            canonical_pdf_path="documents/abc123/original.pdf",
            canonical_ocr_md_path="documents/abc123/layout.md",
            title="Superconducting Qubits Scalability",
            doi="10.1038/s41586-024-00001",
            arxiv_id="2401.00001",
            pdf_file_size_bytes=1024 * 512,
            primary_source="arxiv",
            ocr_provider="gemini",
            access_count=5
        )

        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_hash_001",
            title="Quantum Circuit Synthesis",
            abstract="We present optimal synthesis for Clifford+T circuits."
        )

        self.paper_metric = PaperMetric.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            paper=self.paper,
            screening_status="accepted",
            signal_score=71.20
        )

        self.ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Qubit Count Extraction",
            exit_metrics="physical_qubits",
            system_prompt="Extract physical qubits.",
            user_prompt_template="Paper: {paper_text}",
            response_schema={"type": "object", "properties": {"qubits": {"type": "integer"}}}
        )

        self.extraction = Extraction.objects.create(
            workspace=self.workspace,
            paper=self.paper,
            extraction_definition=self.ext_def,
            category="performance_metric",
            fields_data={"qubits": 127},
            confidence_score=0.98,
            validation_status="pass"
        )

        self.activity_log = UserActivityLog.objects.create(
            user=self.user,
            workspace=self.workspace,
            interface="mcp",
            action_name="get_paper_extractions_matrix",
            execution_time_ms=145.0,
            status="success"
        )

    def test_pipelinerun_changelist_renders(self):
        url = reverse('admin:research_intelligence_pipelinerun_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "$0.0452")
        self.assertContains(response, "Quantum Computing Intelligence")
        self.assertContains(response, "Papers (In ➔ Out)")

    def test_pipelinerun_changeform_renders(self):
        url = reverse('admin:research_intelligence_pipelinerun_change', args=[self.pipeline_run.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Component runs")

    def test_componentrun_changelist_renders(self):
        url = reverse('admin:research_intelligence_componentrun_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "$0.0183")
        self.assertContains(response, "$0.0269")
        self.assertContains(response, "13 passed")
        self.assertContains(response, "8 rejected")
        self.assertContains(response, "65 extractions")

    def test_researchagentprocess_changelist_renders(self):
        # Legacy ResearchAgentProcess URL seamlessly redirects to unified PipelineRun changelist
        url = '/admin/research_intelligence/researchagentprocess/'
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quantum Computing Intelligence")
        self.assertContains(response, "$0.0452")

    def test_documentregistry_changelist_renders(self):
        url = reverse('admin:research_intelligence_documentregistry_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Superconducting Qubits Scalability")
        self.assertContains(response, "⚡ 5 hits")
        self.assertContains(response, "gemini")
        self.assertContains(response, "Total Documents")
        self.assertContains(response, "Total Storage Size")
        self.assertContains(response, "Cache Reused")
        self.assertContains(response, "OCR Layout Cached")
        self.assertContains(response, "512.0 KB")

    def test_format_human_readable_bytes_across_all_units(self):
        from research_intelligence.admin import format_human_readable_bytes
        self.assertEqual(format_human_readable_bytes(0), "0 B")
        self.assertEqual(format_human_readable_bytes(512), "512 B")
        self.assertEqual(format_human_readable_bytes(1024), "1.0 KB")
        self.assertEqual(format_human_readable_bytes(1024 * 1024 * 5), "5.00 MB")
        self.assertEqual(format_human_readable_bytes(1024 * 1024 * 1024 * 3), "3.00 GB")
        self.assertEqual(format_human_readable_bytes(1024 * 1024 * 1024 * 1024 * 2), "2.00 TB")
        self.assertEqual(format_human_readable_bytes(1024 * 1024 * 1024 * 1024 * 1024 * 4), "4.00 PB")

    def test_workspace_changelist_renders(self):
        url = reverse('admin:research_intelligence_workspace_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quantum Computing Intelligence")
        self.assertContains(response, "Tokens Consumed (Total / Month)")
        self.assertContains(response, "USD Spent (Total / Month)")


    def test_workspace_changeform_renders_dynamic_screening_fieldsets(self):
        url = reverse('admin:research_intelligence_workspace_change', args=[self.workspace.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Abstract Screening Engine")
        self.assertContains(response, "Full-Text Screening Engine")
        self.assertContains(response, "abstract_screening_system_prompt")
        self.assertContains(response, "full_text_screening_system_prompt")
        self.assertContains(response, "Switch View (Editor / Readonly)")
        self.assertContains(response, "Copy JSON")
        self.assertContains(response, "Copy Python Code")
        self.assertContains(response, "Python AST Sandboxed")




    def test_paper_changelist_renders(self):
        url = reverse('admin:research_intelligence_paper_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quantum Circuit Synthesis")
        self.assertContains(response, "1 run")
        self.assertNotContains(response, "⚡ 71.20")

    def test_paper_and_documentregistry_markdown_previews(self):
        """Validates that Markdown files are exposed with preview links in Paper and DocumentRegistry Admin."""
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile

        md_path = "workspaces/test_ws/documents/test_hash/document.md"
        default_storage.save(md_path, ContentFile(b"# Test Patent Document\n\nAbstract here."))

        patent_paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="patent_test_md",
            title="Quantum Patent Document",
            source_database="google_patents",
            converted_md_path=md_path,
            document_registry=self.doc_registry
        )

        # 1. Paper list_display has clickable MD badge
        url = reverse('admin:research_intelligence_paper_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quantum Patent Document")
        self.assertContains(response, "📝 MD ↗")
        self.assertContains(response, "action=preview")

        # 2. Paper changeform has preview & download buttons
        change_url = reverse('admin:research_intelligence_paper_change', args=[patent_paper.id])
        change_resp = self.client.get(change_url)
        self.assertEqual(change_resp.status_code, 200)
        self.assertContains(change_resp, "👁️ Preview Markdown")
        self.assertContains(change_resp, "⬇️ Download")
        self.assertContains(change_resp, "⚡ DocumentRegistry #")

        # 3. DocumentRegistry changeform has preview & download buttons
        doc_change_url = reverse('admin:research_intelligence_documentregistry_change', args=[self.doc_registry.id])
        doc_resp = self.client.get(doc_change_url)
        self.assertEqual(doc_resp.status_code, 200)
        self.assertContains(doc_resp, "👁️ Preview Markdown")
        self.assertContains(doc_resp, "⬇️ Download")

    def test_paper_changeform_renders_with_metrics_inline(self):
        url = reverse('admin:research_intelligence_paper_change', args=[self.paper.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quantum Circuit Synthesis")
        self.assertContains(response, "Paper metrics")

    def test_sync_document_registry_admin_action(self):
        """Validates that sync_document_registry action registers unlinked papers into DocumentRegistry."""
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile

        md_path = "workspaces/test_ws/documents/unlinked_hash/document.md"
        default_storage.save(md_path, ContentFile(b"# Unlinked Patent\n\nFull text."))

        unlinked_paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="unlinked_patent_001",
            title="Unlinked Patent 1",
            source_database="google_patents",
            converted_md_path=md_path,
            source_url="https://patents.google.com/patent/US9999999B1/en"
        )
        self.assertIsNone(unlinked_paper.document_registry)

        url = reverse('admin:research_intelligence_paper_changelist')
        post_data = {
            'action': 'sync_document_registry',
            '_selected_action': [str(unlinked_paper.id)],
        }
        resp = self.client.post(url, post_data, follow=True)
        self.assertEqual(resp.status_code, 200)

        unlinked_paper.refresh_from_db()
        self.assertIsNotNone(unlinked_paper.document_registry)
        self.assertEqual(unlinked_paper.document_registry.primary_source, "google_patents")
        self.assertEqual(unlinked_paper.document_registry.ocr_provider, "google_patents_html")
        self.assertTrue(unlinked_paper.document_registry.canonical_ocr_md_path)


    def test_papermetric_changelist_renders(self):
        url = reverse('admin:research_intelligence_papermetric_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quantum Circuit Synthesis")
        self.assertContains(response, "71.20")
        pr_change_url = reverse('admin:research_intelligence_pipelinerun_change', args=[self.pipeline_run.id])
        self.assertContains(response, pr_change_url)

    def test_papermetric_changeform_renders(self):
        url = reverse('admin:research_intelligence_papermetric_change', args=[self.paper_metric.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review &amp; Ingestion Context")
        self.assertContains(response, "Screening Decision &amp; Verification")
        self.assertContains(response, "Composite Signal Score Evaluation")

    def test_extraction_changelist_renders(self):
        url = reverse('admin:research_intelligence_extraction_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Qubit Count Extraction")
        # Pipeline Run link
        pr_change_url = reverse('admin:research_intelligence_pipelinerun_change', args=[self.pipeline_run.id])
        self.assertContains(response, pr_change_url)
        # Component Run link
        cr_change_url = reverse('admin:research_intelligence_componentrun_change', args=[self.comp_run_extraction.id])
        self.assertContains(response, cr_change_url)
        # Verify Category is not in the column headers
        self.assertNotContains(response, '<div class="text"><span>Category</span></div>')

    def test_useractivitylog_changelist_renders(self):
        url = reverse('admin:research_intelligence_useractivitylog_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "get_paper_extractions_matrix")

    def test_componentrun_filter_by_pipeline_run_id(self):
        url = reverse('admin:research_intelligence_componentrun_changelist') + f"?pipeline_run_id={self.pipeline_run.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "abstract_screening")
        self.assertContains(response, "parameter_extraction")
        self.assertContains(response, "signal_score_evaluation")
        self.assertContains(response, "Avg: 35.05")
        self.assertContains(response, "Max: 71.20")

    def test_componentrun_filter_by_workspace_id(self):
        url = reverse('admin:research_intelligence_componentrun_changelist') + f"?workspace_id={self.workspace.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "arxiv_scraper")

    def test_componentrun_search_by_workspace_or_pipeline(self):
        # Search by workspace name
        url_search_ws = reverse('admin:research_intelligence_componentrun_changelist') + "?q=Quantum"
        resp_ws = self.client.get(url_search_ws)
        self.assertEqual(resp_ws.status_code, 200)
        self.assertContains(resp_ws, "arxiv_scraper")

        # Search by short pipeline UUID
        url_search_id = reverse('admin:research_intelligence_componentrun_changelist') + f"?q={str(self.pipeline_run.id)[:8]}"
        resp_id = self.client.get(url_search_id)
        self.assertEqual(resp_id.status_code, 200)
        self.assertContains(resp_id, "arxiv_scraper")

    def test_llmusagerecord_changelist_and_dashboard_renders(self):
        from research_intelligence.models import LLMUsageRecord

        # Create sample records
        LLMUsageRecord.record_usage(
            tokens_in=12500,
            tokens_out=3200,
            llm_model="google/gemini-3.8-flash",
            operation_type="full_text_screening",
            workspace=self.workspace,
            user=self.user,
            pipeline_run_id=str(self.pipeline_run.id)
        )

        url = reverse('admin:research_intelligence_llmusagerecord_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Check KPI cards rendered
        self.assertContains(response, "Prompt Tokens (In)")
        self.assertContains(response, "Output Tokens (Out)")
        self.assertContains(response, "Total Tokens Consumed")
        self.assertContains(response, "Total Platform Spend")
        self.assertContains(response, "12,500")
        self.assertContains(response, "3,200")
        self.assertContains(response, "15,700")

        # Check badges have nowrap
        self.assertContains(response, "white-space: nowrap;")
        self.assertContains(response, "gemini-3.8-flash")

        # Check User filter is rendered in the sidebar
        self.assertContains(response, "By User")
        self.assertContains(response, "⚙️ System / Automated")
        self.assertContains(response, self.user.username)

        # Create a second record by another user and a third record by system
        other_user = User.objects.create_user(username="other_researcher", password="password123")
        LLMUsageRecord.record_usage(
            tokens_in=5000,
            tokens_out=1000,
            llm_model="google/gemini-3.8-flash",
            operation_type="extraction",
            workspace=self.workspace,
            user=other_user,
        )
        LLMUsageRecord.record_usage(
            tokens_in=2000,
            tokens_out=500,
            llm_model="google/gemini-3.8-flash",
            operation_type="reporting",
            workspace=self.workspace,
            user=None,  # System
        )

        # 1. Filter by specific user
        user_url = f"{url}?user={self.user.username}"
        user_resp = self.client.get(user_url)
        self.assertEqual(user_resp.status_code, 200)
        self.assertContains(user_resp, "15,700")  # filtered total for self.user (12500 + 3200)
        self.assertContains(user_resp, "full_text_screening")

        # 2. Filter by system / automated
        sys_url = f"{url}?user=system"
        sys_resp = self.client.get(sys_url)
        self.assertEqual(sys_resp.status_code, 200)
        self.assertContains(sys_resp, "2,500")  # filtered total for system (2000 + 500)
        self.assertContains(sys_resp, "reporting")

    def test_documentregistry_changeform_renders_meta_field(self):
        self.doc_registry.meta = {
            "id": "http://arxiv.org/abs/2608.01939v2",
            "title": "Oraqle: An Empirical Analysis",
            "primary_category": "quant-ph",
            "authors": [{"name": "Emmanouil Giortamis"}]
        }
        self.doc_registry.save(update_fields=['meta'])

        url = reverse('admin:research_intelligence_documentregistry_change', args=[self.doc_registry.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Source Metadata (meta)")
        self.assertContains(response, "http://arxiv.org/abs/2608.01939v2")

