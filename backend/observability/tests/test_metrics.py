from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from decimal import Decimal

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    Paper,
    PaperMetric,
    PipelineRun,
    ComponentRun,
    Extraction,
    ExtractionDefinition,
    DocumentRegistry,
    ResearchAgentProcess,
)
from chat.models import PaperChatSession, PaperChatMessage
from observability.metrics import collect_telemetry_snapshot, generate_prometheus_metrics_text


class ObservabilityTelemetryTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="observability_user", password="PassWord1234!")
        self.workspace = Workspace.objects.create(name="Telemetry Workspace")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")

        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="completed",
            tokens_in=5000,
            tokens_out=1200,
            tokens_consumed=6200,
            usd_cost=Decimal("0.0450")
        )

        # Ingested papers with different screening states
        self.paper_1 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            title="Accepted Quantum Paper",
            source_database="arxiv",
            hash_id="hash_telemetry_1"
        )
        PaperMetric.objects.create(paper=self.paper_1, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="accepted")
        self.paper_2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            title="Rejected Paper",
            source_database="openalex",
            hash_id="hash_telemetry_2"
        )
        PaperMetric.objects.create(paper=self.paper_2, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="rejected")
        self.paper_3 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            title="Abstract Passed Paper",
            source_database="lens",
            hash_id="hash_telemetry_3"
        )
        PaperMetric.objects.create(paper=self.paper_3, pipeline_run=self.pipeline_run, workspace=self.workspace, screening_status="abstract_passed")

        # Component run latency
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="search",
            component_name="workspace_search",
            status="completed",
            started_at=self.pipeline_run.started_at,
            completed_at=self.pipeline_run.started_at
        )

        # Document registry cache item
        DocumentRegistry.objects.create(
            title="Registered Document",
            sha256_hash="sha256_telemetry_doc",
            canonical_pdf_path="workspaces/test.pdf",
            pdf_file_size_bytes=2048576,
            access_count=5
        )

    def test_collect_telemetry_snapshot(self):
        """Verify atomic calculation of conversion yields, cost aggregates, and cache savings."""
        snapshot = collect_telemetry_snapshot()
        self.assertIn("funnel", snapshot)
        self.assertIn("economics", snapshot)
        self.assertIn("latencies", snapshot)
        self.assertIn("cache_efficiency", snapshot)
        self.assertIn("fleet_health", snapshot)

        self.assertEqual(snapshot["funnel"]["total_papers"], 3)
        self.assertEqual(snapshot["funnel"]["status_breakdown"]["accepted"], 1)
        self.assertEqual(snapshot["funnel"]["status_breakdown"]["rejected"], 1)
        self.assertEqual(snapshot["funnel"]["status_breakdown"]["abstract_passed"], 1)

        # Funnel yield calculation
        self.assertGreater(snapshot["funnel"]["conversion_rates"]["abstract_pass_pct"], 0.0)
        self.assertGreater(snapshot["funnel"]["conversion_rates"]["end_to_end_yield_pct"], 0.0)

        # Token and cost economics
        self.assertGreater(snapshot["economics"]["total_platform_usd"], 0.0)
        self.assertEqual(snapshot["economics"]["tokens"]["tokens_consumed_total"], 6200)

        # Cache efficiency
        self.assertEqual(snapshot["cache_efficiency"]["cached_documents_count"], 1)
        self.assertEqual(snapshot["cache_efficiency"]["cache_hits_total"], 4)
        self.assertGreater(snapshot["cache_efficiency"]["bandwidth_saved_bytes"], 0)

    def test_prometheus_metrics_text_format(self):
        """Verify Prometheus exposition format syntax and required metric tokens."""
        metrics_text = generate_prometheus_metrics_text()
        self.assertIn("# HELP sri_papers_total", metrics_text)
        self.assertIn("# TYPE sri_papers_total gauge", metrics_text)
        self.assertIn('sri_papers_total{status="accepted"} 1', metrics_text)
        self.assertIn('sri_papers_total{status="rejected"} 1', metrics_text)
        self.assertIn('sri_papers_ingested_total{provider="arxiv"} 1', metrics_text)
        self.assertIn("sri_llm_cost_usd_total", metrics_text)
        self.assertIn("sri_document_registry_cache_hits_total 4", metrics_text)
        self.assertIn("sri_workspaces_active_total", metrics_text)

    def test_prometheus_metrics_http_endpoint_auth(self):
        """Verify authentication protection on GET /metrics."""
        # 1. Unauthenticated request without key must be 401
        res_unauth = self.client.get("/metrics")
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("401 Unauthorized", res_unauth.content.decode("utf-8"))

        # 2. Authenticated with Django user / JWT session
        self.client.force_authenticate(user=self.user)
        res_user = self.client.get("/metrics")
        self.assertEqual(res_user.status_code, status.HTTP_200_OK)
        self.assertIn("text/plain", res_user["Content-Type"])
        self.assertIn("sri_papers_total", res_user.content.decode("utf-8"))

        # 3. Authenticated via dedicated scraper header (X-Metrics-Key)
        self.client.logout()
        with self.settings(METRICS_EXPORT_KEY="secret_scraper_token_123"):
            res_key = self.client.get("/metrics", HTTP_X_METRICS_KEY="secret_scraper_token_123")
            self.assertEqual(res_key.status_code, status.HTTP_200_OK)

            res_bearer = self.client.get("/metrics", HTTP_AUTHORIZATION="Bearer secret_scraper_token_123")
            self.assertEqual(res_bearer.status_code, status.HTTP_200_OK)

            res_wrong = self.client.get("/metrics", HTTP_X_METRICS_KEY="wrong_token")
            self.assertEqual(res_wrong.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_telemetry_analytics_api_endpoint(self):
        """Verify authenticated JSON dashboard access to GET /api/telemetry/."""
        # Unauthenticated access should be 401
        res_unauth = self.client.get("/api/telemetry/")
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)

        # Authenticated access returns 200 with JSON payload
        self.client.force_authenticate(user=self.user)
        res_auth = self.client.get("/api/telemetry/")
        self.assertEqual(res_auth.status_code, status.HTTP_200_OK)
        self.assertIn("funnel", res_auth.data)
        self.assertIn("economics", res_auth.data)
        self.assertIn("latencies", res_auth.data)
        self.assertEqual(res_auth.data["funnel"]["total_papers"], 3)
