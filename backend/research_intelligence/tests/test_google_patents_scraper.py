import json
import urllib.parse
from datetime import date, datetime
from unittest.mock import MagicMock, patch
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from research_intelligence.models import Workspace, Scraper, Paper, PaperMetric, PipelineRun, ComponentRun
from research_intelligence.scrapers.factory import get_scraper_provider
from research_intelligence.scrapers.google_patents import (
    GooglePatentsScraperProvider,
    clean_text,
    patent_country,
    canonical_patent_id,
)
from research_intelligence.tasks.step_4_screening.node import AbstractScreeningNode
from research_intelligence.tasks.step_4_screening.abstract import screen_abstract
from research_intelligence.tasks.step_2_download.node import DownloadNode
from api.serializers.workspaces import ScraperSerializer


class GooglePatentsScraperUnitTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(name="Patent Scouting Workspace")

    def test_factory_resolves_google_patents(self):
        for name in ("google_patents", "Google Patents", "google-patents", "patents"):
            provider = get_scraper_provider(name, n_last_days=5, api_key="test-key-123")
            self.assertIsInstance(provider, GooglePatentsScraperProvider)
            self.assertEqual(provider.n_last_days, 5)
            self.assertEqual(provider.api_key, "test-key-123")

    def test_clean_text_and_helpers(self):
        self.assertEqual(clean_text("<b>Quantum</b>  Circuit\n"), "Quantum Circuit")
        self.assertEqual(clean_text("&quot;decoder&quot;"), '"decoder"')
        self.assertEqual(patent_country("US-11234567-B2", "US11234567B2"), "US")
        self.assertEqual(patent_country("EP-998877", ""), "EP")
        self.assertEqual(patent_country("", "WO2026010203A1"), "WO")

        raw_item = {"publication_number": "US11234567B2", "patent_id": "US-11234567-B2"}
        self.assertEqual(canonical_patent_id(raw_item), "US11234567B2")

    @override_settings(SERPAPI_API_KEY="")
    def test_search_returns_empty_when_no_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            provider = GooglePatentsScraperProvider(api_key="")
            results = provider.search("quantum", limit=5)
            self.assertEqual(results, [])

    @patch("research_intelligence.scrapers.google_patents.urllib.request.urlopen")
    def test_search_formats_query_and_dates(self, mock_urlopen):
        mock_response = MagicMock()
        mock_payload = {
            "organic_results": [
                {
                    "position": 1,
                    "title": "Cryogenic Control Circuit for Quantum Computing",
                    "snippet": "A cryogenic control system for superconducting qubits...",
                    "patent_id": "US-12345678-B1",
                    "publication_number": "US12345678B1",
                    "patent_link": "https://patents.google.com/patent/US12345678B1/en",
                    "pdf": "https://patentimages.storage.googleapis.com/test.pdf",
                    "publication_date": "2026-09-05",
                    "filing_date": "2025-03-01",
                    "inventor": "Alice Smith, Bob Jones",
                    "assignee": "Quantum Corp",
                    "language": "en",
                }
            ]
        }
        mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = GooglePatentsScraperProvider(api_key="serpapi-mock-key")
        results = provider.search(
            query="cryogenic control",
            limit=1,
            start_date="2026-09-01",
            end_date="2026-09-07",
            sort_by="date",
        )

        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        url = req.full_url
        parsed = urllib.parse.urlparse(url)
        params = dict(urllib.parse.parse_qsl(parsed.query))

        self.assertEqual(params["engine"], "google_patents")
        self.assertEqual(params["q"], "cryogenic control")
        self.assertEqual(params["after"], "publication:20260901")
        self.assertEqual(params["before"], "publication:20260907")
        self.assertEqual(params["sort"], "new")
        self.assertEqual(params["dups"], "language")
        self.assertEqual(params["patents"], "true")
        self.assertEqual(params["scholar"], "false")
        self.assertEqual(params["api_key"], "serpapi-mock-key")

        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["title"], "Cryogenic Control Circuit for Quantum Computing")
        self.assertEqual(r["source_database"], "google_patents")
        self.assertEqual(r["hash_id"], "US12345678B1")
        self.assertEqual(r["pdf_url"], "https://patentimages.storage.googleapis.com/test.pdf")
        self.assertEqual(r["other_url"], "https://patents.google.com/patent/US12345678B1/en")
        self.assertEqual(r["published_date"], "2026-09-05")
        self.assertIn("Alice Smith", r["authors"])
        self.assertEqual(r["meta"]["country"], "US")
        self.assertEqual(r["meta"]["patent_id"], "US-12345678-B1")

    @patch("research_intelligence.scrapers.google_patents.safe_download_url")
    @patch("research_intelligence.scrapers.google_patents.is_safe_external_url")
    def test_download_file_calls_safe_download(self, mock_is_safe, mock_safe_download):
        mock_is_safe.return_value = True
        mock_safe_download.return_value = b"%PDF-1.5 test patent binary"

        provider = GooglePatentsScraperProvider(api_key="key")
        content = provider.download_file("https://patentimages.storage.googleapis.com/test.pdf")

        self.assertTrue(mock_safe_download.called)
        self.assertEqual(content, b"%PDF-1.5 test patent binary")

    @patch("research_intelligence.scrapers.google_patents.urllib.request.urlopen")
    def test_search_falls_back_to_patent_link_when_pdf_missing(self, mock_urlopen):
        mock_response = MagicMock()
        mock_payload = {
            "organic_results": [
                {
                    "position": 1,
                    "title": "Quantum Algorithm",
                    "snippet": "Snippet without direct PDF...",
                    "patent_id": "US-999999-A",
                    "publication_number": "US999999A",
                    "patent_link": "https://patents.google.com/patent/US999999A/en",
                    # "pdf" key is absent
                }
            ]
        }
        mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = GooglePatentsScraperProvider(api_key="key")
        results = provider.search(query="quantum", limit=1)

        self.assertEqual(len(results), 1)
        # pdf_url falls back to patent_link so downloader receives an active URL
        self.assertEqual(results[0]["pdf_url"], "https://patents.google.com/patent/US999999A/en")
        self.assertEqual(results[0]["other_url"], "https://patents.google.com/patent/US999999A/en")

    @patch("research_intelligence.scrapers.google_patents.safe_download_url")
    @patch("research_intelligence.scrapers.google_patents.is_safe_external_url")
    def test_download_file_resolves_landing_page_to_pdf(self, mock_is_safe, mock_safe_download):
        mock_is_safe.return_value = True

        def fake_download(url, **kwargs):
            if "patents.google.com" in url:
                html = (
                    '<html><body><a href="https://patentimages.storage.googleapis.com/12/34/US999999A.pdf">'
                    'Download PDF</a></body></html>'
                )
                return html.encode("utf-8")
            elif "patentimages.storage.googleapis.com" in url:
                return b"%PDF-1.5 resolved patent binary"
            return b""

        mock_safe_download.side_effect = fake_download

        provider = GooglePatentsScraperProvider(api_key="key")
        content = provider.download_file("https://patents.google.com/patent/US999999A/en")

        self.assertEqual(content, b"%PDF-1.5 resolved patent binary")
        # Ensure it requested the landing page first, then the extracted PDF
        self.assertEqual(mock_safe_download.call_count, 2)


class AbstractScreeningPatentBypassTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Patent Workspace",
            screening_llm_model="google/gemini-3.8-flash",
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
        )

    def test_abstract_screening_node_is_skippable_when_all_scrapers_are_patents(self):
        Scraper.objects.create(
            workspace=self.workspace,
            provider="google_patents",
            search_query="robotics",
            is_active=True,
        )
        node = AbstractScreeningNode()
        self.assertTrue(node.is_skippable(self.pipeline_run, self.workspace, {}))

    def test_abstract_screening_node_not_skippable_when_mixed_scrapers(self):
        Scraper.objects.create(
            workspace=self.workspace,
            provider="google_patents",
            search_query="robotics",
            is_active=True,
        )
        Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="robotics",
            is_active=True,
        )
        node = AbstractScreeningNode()
        self.assertFalse(node.is_skippable(self.pipeline_run, self.workspace, {}))

    def test_download_node_target_mode_all_ingested_when_patents(self):
        Scraper.objects.create(
            workspace=self.workspace,
            provider="google_patents",
            search_query="robotics",
            is_active=True,
        )
        download_node = DownloadNode()
        params = download_node.get_input_params(self.pipeline_run, self.workspace, {})
        self.assertEqual(params["target_mode"], "all_ingested")

    @patch("research_intelligence.tasks.step_4_screening.abstract.get_llm_provider")
    def test_screen_abstract_automatically_bypasses_patent(self, mock_llm):
        paper = Paper.objects.create(
            workspace=self.workspace,
            title="Fault-Tolerant Quantum Processor",
            abstract="Short patent snippet",
            source_database="google_patents",
            meta={"patent_id": "US-11223344-B2"},
        )
        pm = PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            screening_status="pending",
        )

        res = screen_abstract(
            paper_id=paper.id,
            workspace_id=self.workspace.id,
            workspace_obj=self.workspace,
            paper_obj=paper,
            pipeline_run_id=str(self.pipeline_run.id),
        )

        # Ensure LLM provider was NOT called!
        self.assertFalse(mock_llm.called)

        self.assertTrue(res["success"])
        self.assertTrue(res["passed"])
        self.assertEqual(res["screening_status"], "abstract_passed")
        self.assertEqual(res["decision_category"], "BYPASS_PATENT")
        self.assertIn("bypassed abstract screening", res["reasoning"])

        pm.refresh_from_db()
        self.assertEqual(pm.screening_status, "abstract_passed")
        self.assertIn("BYPASS_PATENT", pm.metrics_data["abstract_screening"]["decision_category"])


class ScraperModelAndSerializerTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(name="Model Test WS")

    def test_scraper_model_fields(self):
        scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="google_patents",
            search_query='"optical proximity correction"',
            api_key="secret-serpapi-key",
            is_active=True,
        )
        self.assertEqual(scraper.provider, "google_patents")
        self.assertEqual(scraper.api_key, "secret-serpapi-key")
        self.assertEqual(scraper.get_provider_display(), "Google Patents")

    def test_scraper_serializer_hides_api_key_on_read(self):
        scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="google_patents",
            search_query="chiplet packaging",
            api_key="secret-token-value",
            is_active=True,
        )
        serializer = ScraperSerializer(instance=scraper)
        data = serializer.data

        # api_key is write_only: it must NOT be present in read serialization
        self.assertNotIn("api_key", data)
        # has_api_key indicates whether an API key is configured
        self.assertTrue(data.get("has_api_key"))

    def test_scraper_serializer_accepts_api_key_on_write(self):
        serializer = ScraperSerializer(
            data={
                "workspace": str(self.workspace.id),
                "provider": "google_patents",
                "search_query": "high-level synthesis",
                "api_key": "user-supplied-key",
                "limit": 100,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save()
        self.assertEqual(instance.api_key, "user-supplied-key")
        self.assertEqual(instance.provider, "google_patents")
