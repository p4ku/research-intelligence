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
            screening_llm_model="google/gemini-3.7-flash",
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
            abstract="We present optimal synthesis for Clifford+T circuits.",
            screening_status="accepted",
            signal_score=Decimal("71.20")
        )

        self.ext_def = ExtractionDefinition.objects.create(
            workspace=self.workspace,
            name="Qubit Count Extraction",
            exit_metric="physical_qubits",
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
        url = reverse('admin:research_intelligence_researchagentprocess_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Autonomous Agent Process 1")
        self.assertContains(response, "$0.0452")

    def test_documentregistry_changelist_renders(self):
        url = reverse('admin:research_intelligence_documentregistry_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Superconducting Qubits Scalability")
        self.assertContains(response, "⚡ 5 hits")
        self.assertContains(response, "gemini")

    def test_workspace_changelist_renders(self):
        url = reverse('admin:research_intelligence_workspace_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quantum Computing Intelligence")

    def test_paper_changelist_renders(self):
        url = reverse('admin:research_intelligence_paper_changelist')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quantum Circuit Synthesis")
        self.assertContains(response, "⚡ 71.20")
        pr_change_url = reverse('admin:research_intelligence_pipelinerun_change', args=[self.pipeline_run.id])
        self.assertContains(response, pr_change_url)

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

