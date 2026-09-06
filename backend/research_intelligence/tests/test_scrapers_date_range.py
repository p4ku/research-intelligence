import json
import uuid
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from research_intelligence.models import (
    Workspace,
    WorkspaceMember,
    PipelineRun,
    ComponentRun,
    Scraper,
)
from research_intelligence.scrapers.base import BaseScraperProvider
from research_intelligence.scrapers.arxiv import ArxivScraperProvider
from research_intelligence.scrapers.openalex import OpenAlexScraperProvider
from research_intelligence.scrapers.lens import LensScraperProvider
from research_intelligence.scrapers.factory import get_scraper_provider
from research_intelligence.tasks.step_1_search.node import SearchNode
from research_intelligence.tasks.step_1_search.search import execute_scraper_run_job
from api.serializers.workspaces import ScraperSerializer
from mcp_server.tools.scrapers.crud import (
    create_scraper_logic,
    update_scraper_logic,
    list_scrapers_logic,
    get_scraper_logic,
)
from mcp_server.tools.agents.processes import start_research_agent_logic
from mcp_server.tools.pipeline_runs.triggers import (
    start_pipeline_run_logic,
    trigger_search_job_logic,
)


class DummyScraperProvider(BaseScraperProvider):
    def search(self, query: str, limit: int = 10, **kwargs) -> list[dict]:
        return []

    def download_file(self, url: str) -> bytes:
        return b""


class ScraperDateRangeResolutionTests(TestCase):
    def test_default_n_last_days_when_no_dates_given(self):
        provider = DummyScraperProvider()
        self.assertEqual(provider.n_last_days, 7)
        self.assertEqual(provider.DEFAULT_N_LAST_DAYS, 7)

        before = timezone.now()
        start_dt, end_dt = provider.resolve_date_range()
        after = timezone.now()

        diff = end_dt - start_dt
        self.assertAlmostEqual(diff.total_seconds(), timedelta(days=7).total_seconds(), delta=5)
        self.assertTrue(before - timedelta(seconds=2) <= end_dt <= after + timedelta(seconds=2))

    def test_custom_n_last_days_parameter(self):
        provider = DummyScraperProvider(n_last_days=14)
        self.assertEqual(provider.n_last_days, 14)

        start_dt, end_dt = provider.resolve_date_range()
        diff = end_dt - start_dt
        self.assertAlmostEqual(diff.total_seconds(), timedelta(days=14).total_seconds(), delta=5)

    def test_override_n_last_days_in_resolve_call(self):
        provider = DummyScraperProvider(n_last_days=7)
        start_dt, end_dt = provider.resolve_date_range(n_last_days=30)
        diff = end_dt - start_dt
        self.assertAlmostEqual(diff.total_seconds(), timedelta(days=30).total_seconds(), delta=5)

    def test_explicit_start_and_end_dates_as_strings(self):
        provider = DummyScraperProvider()
        start_dt, end_dt = provider.resolve_date_range(start_date="2026-08-01", end_date="2026-08-15")
        self.assertEqual(start_dt.year, 2026)
        self.assertEqual(start_dt.month, 8)
        self.assertEqual(start_dt.day, 1)
        self.assertEqual(end_dt.year, 2026)
        self.assertEqual(end_dt.month, 8)
        self.assertEqual(end_dt.day, 15)

    def test_inverted_start_and_end_dates_swapped(self):
        provider = DummyScraperProvider()
        start_dt, end_dt = provider.resolve_date_range(start_date="2026-08-20", end_date="2026-08-10")
        self.assertEqual(start_dt.day, 10)
        self.assertEqual(end_dt.day, 20)

    def test_only_start_date_provided_defaults_end_to_now(self):
        provider = DummyScraperProvider()
        before = timezone.now()
        start_dt, end_dt = provider.resolve_date_range(start_date="2026-08-01")
        after = timezone.now()
        self.assertEqual(start_dt.day, 1)
        self.assertTrue(before - timedelta(seconds=2) <= end_dt <= after + timedelta(seconds=2))

    def test_only_end_date_provided_defaults_start_to_end_minus_n_last_days(self):
        provider = DummyScraperProvider(n_last_days=5)
        start_dt, end_dt = provider.resolve_date_range(end_date="2026-08-20")
        self.assertEqual(end_dt.day, 20)
        self.assertEqual(start_dt.day, 15)

    def test_format_helpers(self):
        provider = DummyScraperProvider()
        s_dt = datetime(2026, 9, 1, 10, 0, 0)
        e_dt = datetime(2026, 9, 6, 18, 0, 0)
        s_iso, e_iso = provider.format_iso_date_range(s_dt, e_dt)
        self.assertEqual(s_iso, "2026-09-01")
        self.assertEqual(e_iso, "2026-09-06")

        arxiv_filter = provider.format_arxiv_date_filter(s_dt, e_dt)
        self.assertEqual(arxiv_filter, "submittedDate:[20260901000000 TO 20260906235959]")


class ScraperProvidersQueryModificationTests(TestCase):
    def test_factory_resolves_and_sets_n_last_days(self):
        arxiv = get_scraper_provider("arxiv", n_last_days=10)
        self.assertIsInstance(arxiv, ArxivScraperProvider)
        self.assertEqual(arxiv.n_last_days, 10)

        openalex = get_scraper_provider("openalex", n_last_days=12)
        self.assertIsInstance(openalex, OpenAlexScraperProvider)
        self.assertEqual(openalex.n_last_days, 12)

        lens = get_scraper_provider("lens", n_last_days=21)
        self.assertIsInstance(lens, LensScraperProvider)
        self.assertEqual(lens.n_last_days, 21)

    @patch("research_intelligence.scrapers.arxiv.urllib.request.urlopen")
    def test_arxiv_search_injects_submitted_date_filter(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = ArxivScraperProvider()
        provider.search("deep learning", limit=5, start_date="2026-08-01", end_date="2026-08-10")

        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        full_url = req.full_url
        self.assertIn("submittedDate", full_url)
        self.assertIn("20260801000000", full_url)
        self.assertIn("20260810235959", full_url)

    @patch("research_intelligence.scrapers.openalex.urllib.request.urlopen")
    def test_openalex_search_injects_publication_date_filter(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"results": []}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = OpenAlexScraperProvider()
        provider.search("quantum computing", limit=5, start_date="2026-08-01", end_date="2026-08-10")

        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        full_url = req.full_url
        self.assertIn("from_publication_date:2026-08-01", full_url)
        self.assertIn("to_publication_date:2026-08-10", full_url)

    @patch("research_intelligence.scrapers.lens.settings")
    @patch("research_intelligence.scrapers.lens.urllib.request.urlopen")
    def test_lens_search_injects_elastic_date_range(self, mock_urlopen, mock_settings):
        mock_settings.LENS_API_KEY = "test-lens-key"
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": []}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = LensScraperProvider()
        provider.search("crispr", limit=5, start_date="2026-08-01", end_date="2026-08-10")

        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        bool_query = payload["query"]["bool"]
        must_clauses = bool_query["must"]
        range_clause = next((c for c in must_clauses if "range" in c), None)
        self.assertIsNotNone(range_clause)
        self.assertEqual(range_clause["range"]["date_published"]["gte"], "2026-08-01")
        self.assertEqual(range_clause["range"]["date_published"]["lte"], "2026-08-10")


class SearchExecutionAndNodeTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(name="Test Date Range WS")
        self.scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="transformers",
            is_active=True
        )

    def test_search_node_extracts_date_parameters_into_input_params(self):
        node = SearchNode()
        pipeline_run = PipelineRun.objects.create(workspace=self.workspace, status="running")
        config = {
            "start_date": "2026-09-01",
            "end_date": "2026-09-06",
            "n_last_days": 10
        }
        params = node.get_input_params(pipeline_run, self.workspace, config)
        self.assertEqual(params["start_date"], "2026-09-01")
        self.assertEqual(params["end_date"], "2026-09-06")
        self.assertEqual(params["n_last_days"], 10)

    @patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider")
    def test_execute_scraper_run_job_forwards_dates_to_provider(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.search.return_value = []
        mock_get_provider.return_value = mock_provider

        pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            configuration_override={"start_date": "2026-08-01", "end_date": "2026-08-07", "n_last_days": 14}
        )
        comp_run = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type="search",
            component_name="arxiv_scraper",
            scraper=self.scraper,
            status="pending",
            input_params={"start_date": "2026-08-01", "end_date": "2026-08-07", "n_last_days": 14}
        )

        execute_scraper_run_job(str(comp_run.id))

        mock_get_provider.assert_called_once_with("arxiv", n_last_days=14)
        mock_provider.search.assert_called_once()
        kwargs = mock_provider.search.call_args[1]
        self.assertEqual(kwargs["start_date"], "2026-08-01")
        self.assertEqual(kwargs["end_date"], "2026-08-07")
        self.assertEqual(kwargs["n_last_days"], 14)


class MCPToolsAndAPIEndpointsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="lead_researcher", password="password123")
        self.workspace = Workspace.objects.create(name="MCP Date Range WS")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="manager")
        self.scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="openalex",
            search_query="nanomaterials",
            is_active=True
        )
        self.client.force_authenticate(user=self.user)

    @patch("research_intelligence.tasks.orchestrator.runner.PipelineRunner.tick")
    def test_start_pipeline_run_logic_mcp_captures_date_parameters(self, mock_tick):
        mock_tick.return_value = {"success": True, "status": "running"}
        res_raw = start_pipeline_run_logic(
            user=self.user,
            workspace_id=str(self.workspace.id),
            start_date="2026-08-10",
            end_date="2026-08-20",
            n_last_days=10
        )
        res = json.loads(res_raw)
        self.assertEqual(res["status"], "success")
        pr_id = res["pipeline_run_id"]
        pr = PipelineRun.objects.get(id=pr_id)
        self.assertEqual(pr.configuration_override["start_date"], "2026-08-10")
        self.assertEqual(pr.configuration_override["end_date"], "2026-08-20")
        self.assertEqual(pr.configuration_override["n_last_days"], 10)

    @patch("research_intelligence.tasks.step_1_search.search.execute_scraper_run_job.delay")
    def test_trigger_search_job_logic_mcp_captures_date_parameters(self, mock_delay):
        mock_delay.return_value = MagicMock(id="celery_task_123")
        res_raw = trigger_search_job_logic(
            user=self.user,
            workspace_id=str(self.workspace.id),
            start_date="2026-08-01",
            end_date="2026-08-08",
            n_last_days=7
        )
        res = json.loads(res_raw)
        self.assertTrue(res["success"])
        pr_id = res["pipeline_run_id"]
        pr = PipelineRun.objects.get(id=pr_id)
        self.assertEqual(pr.configuration_override["start_date"], "2026-08-01")
        self.assertEqual(pr.configuration_override["end_date"], "2026-08-08")
        self.assertEqual(pr.configuration_override["n_last_days"], 7)

        comp_run = ComponentRun.objects.filter(pipeline_run=pr).first()
        self.assertIsNotNone(comp_run)
        self.assertEqual(comp_run.input_params["start_date"], "2026-08-01")
        self.assertEqual(comp_run.input_params["end_date"], "2026-08-08")
        self.assertEqual(comp_run.input_params["n_last_days"], 7)

    @patch("research_intelligence.tasks.orchestrator.runner.PipelineRunner.tick")
    def test_api_pipeline_runs_start_endpoint(self, mock_tick):
        mock_tick.return_value = {"success": True, "status": "running"}
        url = "/api/pipeline-runs/start/"
        payload = {
            "workspace_id": str(self.workspace.id),
            "name": "API Date Range Run",
            "start_date": "2026-07-01",
            "end_date": "2026-07-15",
            "n_last_days": 14,
            "autonomous": True
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("pipeline_run_id", response.data)
        pr_id = response.data["pipeline_run_id"]
        pr = PipelineRun.objects.get(id=pr_id)
        self.assertEqual(pr.configuration_override["start_date"], "2026-07-01")
        self.assertEqual(pr.configuration_override["end_date"], "2026-07-15")
        self.assertEqual(pr.configuration_override["n_last_days"], 14)

    @patch("research_intelligence.tasks.orchestrator.runner.PipelineRunner.tick")
    def test_api_workspace_run_pipeline_endpoint(self, mock_tick):
        mock_tick.return_value = {"success": True, "status": "running"}
        url = f"/api/workspaces/{self.workspace.id}/run-pipeline/"
        payload = {
            "name": "Workspace Level Run",
            "start_date": "2026-06-01",
            "end_date": "2026-06-10",
            "n_last_days": 9
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("pipeline_run_id", response.data)
        pr_id = response.data["pipeline_run_id"]
        pr = PipelineRun.objects.get(id=pr_id)
        self.assertEqual(pr.configuration_override["start_date"], "2026-06-01")
        self.assertEqual(pr.configuration_override["end_date"], "2026-06-10")
        self.assertEqual(pr.configuration_override["n_last_days"], 9)


class ScraperModelPersistenceAndSerializerTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(name="Model Persistence WS")

    def test_default_n_last_days_in_database(self):
        scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="quantum",
        )
        scraper.refresh_from_db()
        self.assertEqual(scraper.n_last_days, 7)

    def test_custom_n_last_days_in_database(self):
        scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="openalex",
            search_query="materials",
            n_last_days=30
        )
        scraper.refresh_from_db()
        self.assertEqual(scraper.n_last_days, 30)

    def test_update_scraper_n_last_days_in_database(self):
        scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="lens",
            search_query="battery",
            n_last_days=7
        )
        scraper.n_last_days = 45
        scraper.save()
        scraper.refresh_from_db()
        self.assertEqual(scraper.n_last_days, 45)

    def test_scraper_serializer_serialization(self):
        scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="photovoltaics",
            n_last_days=14
        )
        serializer = ScraperSerializer(scraper)
        self.assertIn("n_last_days", serializer.data)
        self.assertEqual(serializer.data["n_last_days"], 14)

    def test_scraper_serializer_create_with_n_last_days(self):
        data = {
            "workspace": self.workspace.id,
            "provider": "openalex",
            "search_query": "solid state",
            "n_last_days": 21,
            "is_active": True
        }
        serializer = ScraperSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save()
        self.assertEqual(instance.n_last_days, 21)


class BaseScraperDateResolutionAdvancedEdgeCasesTests(TestCase):
    def setUp(self):
        self.provider = DummyScraperProvider()

    def test_resolve_date_range_with_datetime_objects(self):
        dt_start = timezone.now() - timedelta(days=3)
        dt_end = timezone.now()
        s, e = self.provider.resolve_date_range(start_date=dt_start, end_date=dt_end)
        self.assertEqual(s, dt_start)
        self.assertEqual(e, dt_end)

    def test_resolve_date_range_with_date_objects(self):
        d_start = date(2026, 8, 1)
        d_end = date(2026, 8, 10)
        s, e = self.provider.resolve_date_range(start_date=d_start, end_date=d_end)
        self.assertEqual(s.year, 2026)
        self.assertEqual(s.month, 8)
        self.assertEqual(s.day, 1)
        self.assertEqual(e.year, 2026)
        self.assertEqual(e.month, 8)
        self.assertEqual(e.day, 10)

    def test_resolve_date_range_with_invalid_date_strings_falls_back_to_n_last_days(self):
        before = timezone.now()
        s, e = self.provider.resolve_date_range(start_date="not-a-valid-date", end_date="corrupted-time", n_last_days=5)
        after = timezone.now()
        diff = e - s
        self.assertAlmostEqual(diff.total_seconds(), timedelta(days=5).total_seconds(), delta=5)
        self.assertTrue(before - timedelta(seconds=2) <= e <= after + timedelta(seconds=2))

    def test_resolve_date_range_with_empty_or_whitespace_strings(self):
        s, e = self.provider.resolve_date_range(start_date="", end_date="   ", n_last_days=7)
        diff = e - s
        self.assertAlmostEqual(diff.total_seconds(), timedelta(days=7).total_seconds(), delta=5)

    def test_resolve_date_range_non_positive_n_last_days_resets_to_default(self):
        s, e = self.provider.resolve_date_range(n_last_days=0)
        diff = e - s
        self.assertAlmostEqual(diff.total_seconds(), timedelta(days=7).total_seconds(), delta=5)

        s_neg, e_neg = self.provider.resolve_date_range(n_last_days=-10)
        diff_neg = e_neg - s_neg
        self.assertAlmostEqual(diff_neg.total_seconds(), timedelta(days=7).total_seconds(), delta=5)

    def test_resolve_date_range_string_n_last_days_coerced(self):
        s, e = self.provider.resolve_date_range(n_last_days="12")
        diff = e - s
        self.assertAlmostEqual(diff.total_seconds(), timedelta(days=12).total_seconds(), delta=5)


class ScraperProviderDateQueryAdvancedEdgeCasesTests(TestCase):
    @patch("research_intelligence.scrapers.arxiv.urllib.request.urlopen")
    def test_arxiv_preserves_existing_submitted_date_in_query(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = ArxivScraperProvider()
        provider.search("submittedDate:[20250101000000 TO 20250131235959] AND cat:cs.AI", limit=5)

        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url.count("submittedDate"), 1)

    @patch("research_intelligence.scrapers.arxiv.urllib.request.urlopen")
    def test_arxiv_empty_query_builds_valid_date_filter_url(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = ArxivScraperProvider()
        provider.search("", limit=5, start_date="2026-08-01", end_date="2026-08-05")

        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        self.assertIn("submittedDate%3A%5B20260801000000%20TO%2020260805235959%5D", req.full_url)
        self.assertNotIn("%28%29+AND", req.full_url)

    @patch("research_intelligence.scrapers.openalex.urllib.request.urlopen")
    def test_openalex_preserves_existing_from_publication_date(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"results": []}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = OpenAlexScraperProvider()
        provider.search("filter=from_publication_date:2025-01-01,to_publication_date:2025-01-31", limit=5)

        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url.count("from_publication_date"), 1)

    @patch("research_intelligence.scrapers.openalex.urllib.request.urlopen")
    def test_openalex_combines_with_existing_filter(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"results": []}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = OpenAlexScraperProvider()
        provider.search("solid state battery", limit=5, start_date="2026-07-01", end_date="2026-07-15")

        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        self.assertIn("from_publication_date:2026-07-01,to_publication_date:2026-07-15", req.full_url)


class SearchExecutionFallbackCascadeTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(name="Cascade Test WS")

    @patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider")
    def test_fallback_priority_1_input_params_used(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.search.return_value = []
        mock_get_provider.return_value = mock_provider

        scraper = Scraper.objects.create(workspace=self.workspace, provider="arxiv", search_query="ai", n_last_days=14)
        pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            configuration_override={"n_last_days": 10}
        )
        comp_run = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type="search",
            component_name="arxiv_scraper",
            scraper=scraper,
            status="pending",
            input_params={"n_last_days": 3}
        )
        execute_scraper_run_job(str(comp_run.id))
        mock_get_provider.assert_called_once_with("arxiv", n_last_days=3)

    @patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider")
    def test_fallback_priority_2_config_override_used_when_input_params_empty(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.search.return_value = []
        mock_get_provider.return_value = mock_provider

        scraper = Scraper.objects.create(workspace=self.workspace, provider="arxiv", search_query="ai", n_last_days=14)
        pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            configuration_override={"n_last_days": 10}
        )
        comp_run = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type="search",
            component_name="arxiv_scraper",
            scraper=scraper,
            status="pending",
            input_params={}
        )
        execute_scraper_run_job(str(comp_run.id))
        mock_get_provider.assert_called_once_with("arxiv", n_last_days=10)

    @patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider")
    def test_fallback_priority_3_scraper_model_used_when_override_empty(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.search.return_value = []
        mock_get_provider.return_value = mock_provider

        scraper = Scraper.objects.create(workspace=self.workspace, provider="arxiv", search_query="ai", n_last_days=25)
        pipeline_run = PipelineRun.objects.create(workspace=self.workspace, configuration_override={})
        comp_run = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type="search",
            component_name="arxiv_scraper",
            scraper=scraper,
            status="pending",
            input_params={}
        )
        execute_scraper_run_job(str(comp_run.id))
        mock_get_provider.assert_called_once_with("arxiv", n_last_days=25)

    @patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider")
    def test_fallback_priority_4_default_7_when_all_are_none(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.search.return_value = []
        mock_get_provider.return_value = mock_provider

        scraper = Scraper.objects.create(workspace=self.workspace, provider="arxiv", search_query="ai")
        pipeline_run = PipelineRun.objects.create(workspace=self.workspace, configuration_override={})
        comp_run = ComponentRun.objects.create(
            pipeline_run=pipeline_run,
            step_type="search",
            component_name="arxiv_scraper",
            scraper=scraper,
            status="pending",
            input_params={}
        )
        execute_scraper_run_job(str(comp_run.id))
        mock_get_provider.assert_called_once_with("arxiv", n_last_days=7)


class MCPScraperCrudToolsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="mcp_user", password="password123")
        self.workspace = Workspace.objects.create(name="MCP CRUD WS")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="manager")

    def test_create_scraper_mcp_persists_n_last_days(self):
        res_raw = create_scraper_logic(
            user=self.user,
            workspace_id=str(self.workspace.id),
            provider="arxiv",
            search_query="superconductors",
            n_last_days=21
        )
        res = json.loads(res_raw)
        self.assertTrue(res["success"])
        scraper_id = res["scraper_id"]
        scraper = Scraper.objects.get(id=scraper_id)
        self.assertEqual(scraper.n_last_days, 21)

    def test_update_scraper_mcp_updates_n_last_days(self):
        scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="openalex",
            search_query="semiconductors",
            n_last_days=7
        )
        res_raw = update_scraper_logic(
            user=self.user,
            scraper_id=str(scraper.id),
            n_last_days=30
        )
        res = json.loads(res_raw)
        self.assertTrue(res["success"])
        scraper.refresh_from_db()
        self.assertEqual(scraper.n_last_days, 30)

    def test_list_and_get_scrapers_mcp_include_n_last_days(self):
        scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="optics",
            n_last_days=18
        )
        list_raw = list_scrapers_logic(user=self.user, workspace_id=str(self.workspace.id))
        scrapers_list = json.loads(list_raw)
        self.assertTrue(len(scrapers_list) >= 1)
        found = next((s for s in scrapers_list if s["scraper_id"] == str(scraper.id)), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["n_last_days"], 18)

        get_raw = get_scraper_logic(user=self.user, scraper_id=str(scraper.id))
        details = json.loads(get_raw)
        self.assertEqual(details["n_last_days"], 18)

    @patch("research_intelligence.tasks.orchestrator.agent_engine.notify_pipeline_orchestrator_tick")
    def test_start_research_agent_mcp_captures_date_range_parameters(self, mock_notify):
        res_raw = start_research_agent_logic(
            user=self.user,
            workspace_id=str(self.workspace.id),
            start_date="2026-08-01",
            end_date="2026-08-15",
            n_last_days=14
        )
        res = json.loads(res_raw)
        self.assertEqual(res["status"], "success")
        proc_id = res["process_id"]
        from research_intelligence.models import ResearchAgentProcess
        proc = ResearchAgentProcess.objects.get(id=proc_id)
        self.assertEqual(proc.configuration_override["start_date"], "2026-08-01")
        self.assertEqual(proc.configuration_override["end_date"], "2026-08-15")
        self.assertEqual(proc.configuration_override["n_last_days"], 14)


class APIPermissionsAndDateValidationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="valid_manager", password="password123")
        self.other_user = User.objects.create_user(username="unauthorized_user", password="password123")
        self.workspace = Workspace.objects.create(name="API Perms WS")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="manager")

    def test_unauthenticated_user_cannot_start_pipeline_run(self):
        url = "/api/pipeline-runs/start/"
        payload = {
            "workspace_id": str(self.workspace.id),
            "start_date": "2026-08-01",
            "end_date": "2026-08-10"
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_workspace_member_cannot_start_pipeline_run(self):
        self.client.force_authenticate(user=self.other_user)
        url = "/api/pipeline-runs/start/"
        payload = {
            "workspace_id": str(self.workspace.id),
            "start_date": "2026-08-01",
            "end_date": "2026-08-10"
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_start_date_format_fails_serializer(self):
        self.client.force_authenticate(user=self.user)
        url = "/api/pipeline-runs/start/"
        payload = {
            "workspace_id": str(self.workspace.id),
            "start_date": "not-a-valid-date-format",
            "end_date": "2026-08-10"
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_date", response.data)

    def test_invalid_n_last_days_fails_serializer(self):
        self.client.force_authenticate(user=self.user)
        url = "/api/pipeline-runs/start/"
        payload = {
            "workspace_id": str(self.workspace.id),
            "n_last_days": 0
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("n_last_days", response.data)

    @patch("research_intelligence.tasks.orchestrator.agent_engine.notify_pipeline_orchestrator_tick")
    def test_research_agent_api_create_accepts_date_parameters(self, mock_notify):
        self.client.force_authenticate(user=self.user)
        url = "/api/agents/"
        payload = {
            "workspace_id": str(self.workspace.id),
            "name": "API Agent Run",
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
            "n_last_days": 10
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["configuration_override"]["start_date"], "2026-08-01")
        self.assertEqual(response.data["configuration_override"]["end_date"], "2026-08-10")
        self.assertEqual(response.data["configuration_override"]["n_last_days"], 10)

    def test_research_agent_api_permission_denied_returns_403(self):
        self.client.force_authenticate(user=self.other_user)
        url = "/api/agents/"
        payload = {
            "workspace_id": str(self.workspace.id),
            "start_date": "2026-08-01",
            "end_date": "2026-08-10"
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("research_intelligence.scrapers.factory.get_scraper_provider")
    def test_preview_search_query_with_dates(self, mock_get_provider):
        from research_intelligence.services.scraper_service import preview_search_query
        mock_provider = MagicMock()
        mock_provider.search.return_value = [{"title": "Quantum Paper"}]
        mock_get_provider.return_value = mock_provider

        res = preview_search_query(
            provider="arxiv",
            search_query="quantum",
            limit=5,
            start_date="2026-09-01",
            end_date="2026-09-06",
            n_last_days=14
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["start_date"], "2026-09-01")
        self.assertEqual(res["end_date"], "2026-09-06")
        self.assertEqual(res["n_last_days"], 14)
        mock_provider.search.assert_called_with(
            "quantum",
            max_results=5,
            start_date="2026-09-01",
            end_date="2026-09-06",
            n_last_days=14
        )

