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

    @override_settings(SERPAPI_API_KEY="")
    def test_resolve_api_key_from_workspace_scraper_model(self):
        with patch.dict("os.environ", {}, clear=True):
            Scraper.objects.create(
                workspace=self.workspace,
                provider="google_patents",
                search_query="test query",
                api_key="db-serpapi-ws-key",
                is_active=True,
            )
            provider = GooglePatentsScraperProvider(api_key="", workspace=self.workspace)
            self.assertEqual(provider.api_key, "db-serpapi-ws-key")

    @override_settings(SERPAPI_API_KEY="")
    def test_resolve_api_key_from_global_active_scraper_model(self):
        with patch.dict("os.environ", {}, clear=True):
            Scraper.objects.create(
                workspace=self.workspace,
                provider="google_patents",
                search_query="test query",
                api_key="db-serpapi-global-key",
                is_active=True,
            )
            provider = GooglePatentsScraperProvider(api_key="")
            self.assertEqual(provider.api_key, "db-serpapi-global-key")

    @override_settings(SERPAPI_API_KEY="")
    @patch("research_intelligence.scrapers.google_patents.urllib.request.urlopen")
    def test_search_uses_api_key_from_model_fallback(self, mock_urlopen):
        with patch.dict("os.environ", {}, clear=True):
            Scraper.objects.create(
                workspace=self.workspace,
                provider="google_patents",
                search_query="test query",
                api_key="db-serpapi-active-key",
                is_active=True,
            )
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({"organic_results": []}).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_response

            provider = GooglePatentsScraperProvider(api_key="")
            provider.search("solid state battery", limit=5)

            self.assertTrue(mock_urlopen.called)
            called_req = mock_urlopen.call_args[0][0]
            url = called_req.full_url
            self.assertIn("api_key=db-serpapi-active-key", url)

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

    @patch("research_intelligence.scrapers.google_patents.urllib.request.urlopen")
    def test_search_omits_sort_parameter_for_relevance(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"organic_results": []}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = GooglePatentsScraperProvider(api_key="mock-key")
        provider.search(query="quantum error correction", sort_by="relevance")

        req = mock_urlopen.call_args[0][0]
        parsed = urllib.parse.urlparse(req.full_url)
        params = dict(urllib.parse.parse_qsl(parsed.query))

        # Crucial: SerpApi raises 400 if sort='relevance' is passed; it MUST be omitted
        self.assertNotIn("sort", params)

    @patch("research_intelligence.scrapers.google_patents.urllib.request.urlopen")
    def test_search_sort_asc_uses_old(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"organic_results": []}).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = GooglePatentsScraperProvider(api_key="mock-key")
        provider.search(query="quantum error correction", sort_by="date", sort_order="asc")

        req = mock_urlopen.call_args[0][0]
        parsed = urllib.parse.urlparse(req.full_url)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        self.assertEqual(params.get("sort"), "old")

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

    def test_scraper_admin_has_api_key_field(self):
        from django.contrib.admin.sites import site
        from research_intelligence.admin import ScraperAdmin

        scraper_admin = ScraperAdmin(Scraper, site)
        self.assertIn("api_key", scraper_admin.fields)
        self.assertIn("api_key_badge", scraper_admin.list_display)

        # Test badge rendering
        scraper_with_key = Scraper(api_key="1234567890abcdef")
        badge_html = scraper_admin.api_key_badge(scraper_with_key)
        self.assertIn("CUSTOM", badge_html)

        scraper_no_key = Scraper(api_key="")
        badge_no_key = scraper_admin.api_key_badge(scraper_no_key)
        self.assertIn("ENV DEFAULT", badge_no_key)


class RealWorldSerpApiPayloadTests(TestCase):
    @patch("research_intelligence.scrapers.google_patents.urllib.request.urlopen")
    def test_real_world_serpapi_payload_parsing(self, mock_urlopen):
        """
        Verify that the exact organic_results payload from SerpApi Google Patents documentation
        is faithfully mapped to Paper fields and metadata.
        """
        raw_doc_item = {
            "position": 1,
            "rank": 0,
            "patent_id": "patent/US8110241B2/en",
            "patent_link": "https://patents.google.com/patent/US8110241B2/en",
            "serpapi_link": "https://serpapi.com/search.json?engine=google_patents_details&patent_id=patent%2FUS8110241B2%2Fen",
            "title": "Foaming soluble coffee powder containing pressurized gas",
            "snippet": "An instant coffee powder has dried soluble coffee in the form of particles or granules having internal voids filled with entrapped pressurized gas.",
            "priority_date": "2004-08-17",
            "filing_date": "2010-04-27",
            "grant_date": "2012-02-07",
            "publication_date": "2012-02-07",
            "inventor": "Bary Lyn Zeller",
            "assignee": "Kraft Foods Global Brands Llc",
            "publication_number": "US8110241B2",
            "language": "en",
            "thumbnail": "https://patentimages.storage.googleapis.com/25/a4/3c/08a69758ca974c/US08110241-20120207-D00000.png",
            "pdf": "https://patentimages.storage.googleapis.com/86/1c/bd/89a41d9faca215/US8110241.pdf",
            "figures": [
                {
                    "thumbnail": "https://patentimages.storage.googleapis.com/bc/43/8a/befe307de64c7c/US08110241-20120207-D00000.png",
                    "full": "https://patentimages.storage.googleapis.com/e0/9e/10/d0a025032833eb/US08110241-20120207-D00000.png",
                }
            ],
            "country_status": {
                "EP": "ACTIVE",
                "US": "ACTIVE",
            },
        }

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"organic_results": [raw_doc_item]}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        provider = GooglePatentsScraperProvider(api_key="real-world-test-key")
        results = provider.search(query="foaming coffee", limit=1)

        self.assertEqual(len(results), 1)
        res = results[0]

        # Top-level paper attributes
        self.assertEqual(res["title"], "Foaming soluble coffee powder containing pressurized gas")
        self.assertEqual(res["authors"], "Bary Lyn Zeller (Assignee: Kraft Foods Global Brands Llc)")
        self.assertIn("An instant coffee powder has dried soluble coffee", res["abstract"])
        self.assertEqual(res["hash_id"], "US8110241B2")
        self.assertEqual(res["pdf_url"], "https://patentimages.storage.googleapis.com/86/1c/bd/89a41d9faca215/US8110241.pdf")
        self.assertEqual(res["other_url"], "https://patents.google.com/patent/US8110241B2/en")
        self.assertEqual(res["source_database"], "google_patents")
        self.assertEqual(res["published_date"], "2012-02-07")

        # Metadata dictionary
        meta = res["meta"]
        self.assertEqual(meta["patent_id"], "patent/US8110241B2/en")
        self.assertEqual(meta["publication_number"], "US8110241B2")
        self.assertEqual(meta["priority_date"], "2004-08-17")
        self.assertEqual(meta["filing_date"], "2010-04-27")
        self.assertEqual(meta["grant_date"], "2012-02-07")
        self.assertEqual(meta["country"], "US")
        self.assertEqual(meta["country_status"], {"EP": "ACTIVE", "US": "ACTIVE"})
        self.assertEqual(len(meta["figures"]), 1)
        self.assertEqual(meta["thumbnail"], "https://patentimages.storage.googleapis.com/25/a4/3c/08a69758ca974c/US08110241-20120207-D00000.png")
        self.assertEqual(meta["source"], "SerpApi Google Patents API")

    @patch("research_intelligence.scrapers.google_patents.urllib.request.urlopen")
    def test_pagination_follows_next_cursor(self, mock_urlopen):
        """
        Verify that search() follows serpapi_pagination.next, keeps the api_key,
        and collects results up to the target limit across multiple pages.
        """
        page1_payload = {
            "organic_results": [
                {
                    "title": "Patent Page 1",
                    "publication_number": "US0000001B1",
                    "patent_id": "patent/US0000001B1/en",
                    "pdf": "https://patentimages.storage.googleapis.com/p1.pdf",
                }
            ],
            "serpapi_pagination": {
                "next": "https://serpapi.com/search.json?engine=google_patents&page=2&q=coffee"
            },
        }
        page2_payload = {
            "organic_results": [
                {
                    "title": "Patent Page 2",
                    "publication_number": "US0000002B1",
                    "patent_id": "patent/US0000002B1/en",
                    "pdf": "https://patentimages.storage.googleapis.com/p2.pdf",
                }
            ],
            # No next link on last page
        }

        mock_resp1 = MagicMock()
        mock_resp1.read.return_value = json.dumps(page1_payload).encode("utf-8")
        mock_resp1.__enter__.return_value = mock_resp1

        mock_resp2 = MagicMock()
        mock_resp2.read.return_value = json.dumps(page2_payload).encode("utf-8")
        mock_resp2.__enter__.return_value = mock_resp2

        mock_urlopen.side_effect = [mock_resp1, mock_resp2]

        provider = GooglePatentsScraperProvider(api_key="pagination-test-key")
        results = provider.search(query="coffee", limit=2)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["title"], "Patent Page 1")
        self.assertEqual(results[1]["title"], "Patent Page 2")
        self.assertEqual(mock_urlopen.call_count, 2)

        # Verify page 2 request had the api_key attached
        req2 = mock_urlopen.call_args_list[1][0][0]
        parsed2 = urllib.parse.urlparse(req2.full_url)
        params2 = dict(urllib.parse.parse_qsl(parsed2.query))
        self.assertEqual(params2.get("api_key"), "pagination-test-key")
        self.assertEqual(params2.get("page"), "2")

    @patch("research_intelligence.scrapers.google_patents.urllib.request.urlopen")
    def test_author_formatting_variants(self, mock_urlopen):
        """
        Verify author combinations: inventor only, assignee only, both, and deduplication.
        """
        test_cases = [
            ({"inventor": "Nikola Tesla"}, "Nikola Tesla"),
            ({"assignee": "Westinghouse Electric Corp"}, "Westinghouse Electric Corp"),
            (
                {"inventor": "Ada Lovelace", "assignee": "Babbage Analytical Engines Ltd"},
                "Ada Lovelace (Assignee: Babbage Analytical Engines Ltd)",
            ),
            (
                {"inventor": "John Doe (Nestle Corp)", "assignee": "Nestle Corp"},
                "John Doe (Nestle Corp)",
            ),
        ]

        for raw_fields, expected_authors in test_cases:
            payload = {
                "organic_results": [
                    {
                        "title": "Invention",
                        "publication_number": f"US{hash(expected_authors) % 10000000}A",
                        **raw_fields,
                    }
                ]
            }
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            provider = GooglePatentsScraperProvider(api_key="test-key")
            results = provider.search("query", limit=1)
            self.assertEqual(results[0]["authors"], expected_authors)

    @patch("research_intelligence.scrapers.google_patents.urllib.request.urlopen")
    def test_date_resolution_fallbacks(self, mock_urlopen):
        """
        Verify fallback hierarchy for publication date:
        publication_date -> filing_date -> priority_date -> ""
        """
        cases = [
            ({"publication_date": "2026-05-01", "filing_date": "2025-01-01"}, "2026-05-01"),
            ({"filing_date": "2025-01-01", "priority_date": "2024-01-01"}, "2025-01-01"),
            ({"priority_date": "2024-01-01"}, "2024-01-01"),
            ({}, ""),
        ]

        for date_fields, expected_date in cases:
            payload = {
                "organic_results": [
                    {
                        "title": "Date Test Patent",
                        "publication_number": f"US{abs(hash(str(date_fields))) % 10000000}A",
                        **date_fields,
                    }
                ]
            }
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            provider = GooglePatentsScraperProvider(api_key="test-key")
            results = provider.search("date query", limit=1)
            self.assertEqual(results[0]["published_date"], expected_date)

    @patch("research_intelligence.scrapers.google_patents.urllib.request.urlopen")
    def test_search_handles_http_error_gracefully(self, mock_urlopen):
        """
        Verify that search() logs and returns gracefully on HTTP errors (e.g. 429 Too Many Requests).
        """
        import urllib.error

        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://serpapi.com/search.json",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=None,
        )

        provider = GooglePatentsScraperProvider(api_key="test-key")
        results = provider.search("failing query", limit=5)
        self.assertEqual(results, [])

    @patch("research_intelligence.scrapers.google_patents.safe_download_url")
    @patch("research_intelligence.scrapers.google_patents.is_safe_external_url")
    def test_download_file_landing_page_without_pdf_link(self, mock_is_safe, mock_safe_download):
        """
        Verify that if the landing page does not contain a PDF link, download_file parses the page
        and returns structured Markdown encoded in UTF-8 bytes for downstream screening.
        """
        mock_is_safe.return_value = True
        mock_safe_download.return_value = (
            b'<html><body>'
            b'<span itemprop="publicationNumber">US12345</span>'
            b'<span itemprop="title">No PDF Patent</span>'
            b'<section itemprop="abstract"><p>Abstract text for no PDF patent.</p></section>'
            b'</body></html>'
        )

        provider = GooglePatentsScraperProvider(api_key="key")
        content = provider.download_file("https://patents.google.com/patent/US12345/en")
        self.assertIn(b"# US12345: No PDF Patent", content)
        self.assertIn(b"## Abstract", content)
        self.assertIn(b"Abstract text for no PDF patent.", content)
        self.assertEqual(mock_safe_download.call_count, 1)


class GooglePatentsCeleryTaskIntegrationTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(name="Integration Workspace")
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="pending",
        )
        self.scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="google_patents",
            search_query="solid state battery",
            api_key="integration-serpapi-key",
            limit=5,
            is_active=True,
        )
        self.component_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            scraper=self.scraper,
            step_type="search",
            component_name="Scraper [Google Patents]",
            status="pending",
        )

    @patch("research_intelligence.scrapers.google_patents.urllib.request.urlopen")
    def test_execute_scraper_run_job_with_google_patents(self, mock_urlopen):
        """
        End-to-end test of Celery worker task execute_scraper_run_job with Google Patents:
        - passes scraper.api_key to GooglePatentsScraperProvider
        - records Paper with source_database='google_patents'
        - records PaperMetric
        - sets component_run.status='completed'
        """
        from research_intelligence.tasks.step_1_search.search import execute_scraper_run_job

        mock_payload = {
            "organic_results": [
                {
                    "title": "Solid-State Battery with Sulfide Solid Electrolyte",
                    "snippet": "A solid-state lithium battery comprising a cathode layer...",
                    "patent_id": "patent/US11999999B2/en",
                    "publication_number": "US11999999B2",
                    "patent_link": "https://patents.google.com/patent/US11999999B2/en",
                    "pdf": "https://patentimages.storage.googleapis.com/test_battery.pdf",
                    "publication_date": "2026-08-15",
                    "inventor": "Kenji Sato",
                    "assignee": "Solid State Tech Corp",
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        success = execute_scraper_run_job(str(self.component_run.id))
        self.assertTrue(success)

        self.component_run.refresh_from_db()
        self.assertEqual(self.component_run.status, "completed")
        self.assertEqual(self.component_run.metrics.get("total_fetched"), 1)
        self.assertEqual(self.component_run.metrics.get("total_created"), 1)

        papers = Paper.objects.filter(workspace=self.workspace)
        self.assertEqual(papers.count(), 1)
        paper = papers.first()
        self.assertEqual(paper.title, "Solid-State Battery with Sulfide Solid Electrolyte")
        self.assertEqual(paper.source_database, "google_patents")
        self.assertEqual(paper.original_pdf_path, "https://patentimages.storage.googleapis.com/test_battery.pdf")
        self.assertEqual(paper.meta.get("publication_number"), "US11999999B2")

        # Verify PaperMetric was linked to the pipeline run
        self.assertTrue(PaperMetric.objects.filter(paper=paper, pipeline_run=self.pipeline_run).exists())


class GooglePatentPageParserAndExtractionTests(TestCase):
    """
    Tests for extracting PDF URL, structured JSON metadata, and Markdown generation
    from real Google Patents HTML pages (CN110549905B with PDF and US20260098257A1 without PDF).
    """

    def setUp(self):
        import os
        self.fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures", "patents")

    def test_parse_cn_patent_with_pdf(self):
        """
        Verify CN110549905B: extracts exact PDF URL on Google Storage,
        Current Assignee (GM Global Technology Operations LLC), 9 inventors,
        active status, timeline events, and claims.
        """
        import os
        from research_intelligence.scrapers.google_patents import GooglePatentPageParser

        fixture_path = os.path.join(self.fixtures_dir, "CN110549905B.html")
        with open(fixture_path, "r", encoding="utf-8") as f:
            html = f.read()

        data = GooglePatentPageParser.parse(html, "https://patents.google.com/patent/CN110549905B/en")

        self.assertEqual(data.publication_number, "CN110549905B")
        self.assertEqual(data.country_code, "CN")
        self.assertIn("Energy sharing system and method for vehicle", data.title)
        self.assertTrue(data.has_pdf)
        self.assertEqual(
            data.pdf_url,
            "https://patentimages.storage.googleapis.com/95/72/73/d47f564213fea2/CN110549905B.pdf",
        )
        self.assertEqual(data.current_assignee, "GM Global Technology Operations LLC")
        self.assertEqual(len(data.inventors), 9)
        self.assertIn("李伟", data.inventors)
        self.assertEqual(data.status, "Active")
        self.assertEqual(data.anticipated_expiration, "2039-05-08")
        self.assertEqual(len(data.events), 6)
        self.assertGreater(len(data.claims), 0)

        # JSON dictionary validation
        meta_dict = data.to_dict()
        self.assertEqual(meta_dict["current_assignee"], "GM Global Technology Operations LLC")
        self.assertEqual(meta_dict["pdf_url"], "https://patentimages.storage.googleapis.com/95/72/73/d47f564213fea2/CN110549905B.pdf")
        self.assertEqual(meta_dict["has_pdf"], True)
        self.assertEqual(meta_dict["anticipated_expiration"], "2039-05-08")

        # Markdown representation validation
        md = data.to_markdown()
        self.assertIn("# CN110549905B: Energy sharing system and method for vehicle", md)
        self.assertIn("**Current Assignee:** GM Global Technology Operations LLC", md)
        self.assertIn("**Anticipated Expiration:** 2039-05-08", md)
        self.assertIn("## Timeline Events", md)
        self.assertIn("## Claims", md)

    def test_parse_us_patent_without_pdf(self):
        """
        Verify US20260098257A1: confirms pdf_url is None, extracts Current Assignee
        (Bruker Spatial Biology Inc), 5 inventors, Pending status, timeline events,
        and generates full Markdown text for screening.
        """
        import os
        from research_intelligence.scrapers.google_patents import GooglePatentPageParser

        fixture_path = os.path.join(self.fixtures_dir, "US20260098257A1.html")
        with open(fixture_path, "r", encoding="utf-8") as f:
            html = f.read()

        data = GooglePatentPageParser.parse(html, "https://patents.google.com/patent/US20260098257A1/en")

        self.assertEqual(data.publication_number, "US20260098257A1")
        self.assertFalse(data.has_pdf)
        self.assertIsNone(data.pdf_url)
        self.assertEqual(data.current_assignee, "Bruker Spatial Biology Inc")
        self.assertEqual(len(data.inventors), 5)
        self.assertIn("Jason M. McEwen", data.inventors)
        self.assertEqual(data.status, "Pending")
        self.assertEqual(len(data.events), 8)
        self.assertEqual(len(data.claims), 87)
        self.assertGreater(len(data.description), 10000)

        # Markdown text contains all essential screening sections
        md = data.to_markdown()
        self.assertIn("# US20260098257A1: Systems and methods for identification of optimized protein production", md)
        self.assertIn("**Current Assignee:** Bruker Spatial Biology Inc", md)
        self.assertIn("**Status:** Pending", md)
        self.assertIn("## Timeline Events", md)
        self.assertIn("## Claims", md)
        self.assertIn("## Detailed Description", md)


class GooglePatentPipelineDownloadAndScreeningTests(TestCase):
    """
    Tests ensuring papers with or without PDF scans seamlessly integrate into
    the Download step, OCR step, and Full-Text screening step.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Patent Screening Workspace",
            screening_llm_model="google/gemini-3.8-flash",
            ocr_provider="pypdf",
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
        )

    @patch("research_intelligence.scrapers.google_patents.safe_download_url")
    @patch("research_intelligence.scrapers.google_patents.is_safe_external_url")
    def test_download_patent_without_pdf_saves_markdown_and_metadata(self, mock_is_safe, mock_safe_download):
        """
        When downloading a patent that lacks a scanned PDF (e.g. US20260098257A1):
        - fetch.py saves the structured Markdown to paper.converted_md_path
        - stores google_patents_details in paper.meta
        - returns status='downloaded'
        - allows OCR step to immediately skip (already converted)
        """
        import os
        from django.core.files.storage import default_storage
        from research_intelligence.tasks.step_2_download.fetch import _download_paper_task
        from research_intelligence.tasks.step_3_ocr.convert import run_ocr_conversion

        mock_is_safe.return_value = True
        fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "patents", "US20260098257A1.html")
        with open(fixture_path, "rb") as f:
            html_bytes = f.read()
        mock_safe_download.return_value = html_bytes

        paper = Paper.objects.create(
            workspace=self.workspace,
            title="Optimized Protein Production",
            hash_id="US20260098257A1HASH",
            source_database="google_patents",
            original_pdf_path="https://patents.google.com/patent/US20260098257A1/en",
            meta={"publication_number": "US20260098257A1"},
        )
        pm = PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            screening_status="abstract_passed",
        )

        res = _download_paper_task(
            paper=paper,
            workspace_obj=self.workspace,
            pipeline_run_obj=self.pipeline_run,
        )

        self.assertEqual(res["status"], "downloaded")
        self.assertEqual(res.get("format"), "markdown")

        paper.refresh_from_db()
        self.assertIsNotNone(paper.converted_md_path)
        self.assertTrue(default_storage.exists(paper.converted_md_path))
        with default_storage.open(paper.converted_md_path, "r") as f:
            md_content = f.read()
        self.assertIn("# US20260098257A1", md_content)
        self.assertIn("Bruker Spatial Biology Inc", md_content)

        # Verify paper.meta contains rich Google Patents details
        details = paper.meta.get("google_patents_details")
        self.assertIsNotNone(details)
        self.assertEqual(details.get("current_assignee"), "Bruker Spatial Biology Inc")
        self.assertEqual(details.get("status"), "Pending")
        self.assertEqual(details.get("claims_count"), 87)

        # Verify OCR step recognizes that document is already converted and succeeds
        ocr_res = run_ocr_conversion(paper.id, paper_obj=paper)
        self.assertTrue(ocr_res["success"])
        self.assertTrue(ocr_res["already_exists"])
        self.assertEqual(ocr_res["storage_path"], paper.converted_md_path)

    @patch("research_intelligence.scrapers.google_patents.safe_download_url")
    @patch("research_intelligence.scrapers.google_patents.is_safe_external_url")
    def test_download_patent_with_pdf_saves_pdf_and_metadata(self, mock_is_safe, mock_safe_download):
        """
        When downloading a patent that has a scanned PDF (e.g. CN110549905B):
        - fetch.py extracts the PDF URL from the page
        - downloads the PDF binary and saves to paper.original_pdf_path
        - stores google_patents_details in paper.meta
        - returns status='downloaded'
        """
        import os
        from django.core.files.storage import default_storage
        from research_intelligence.tasks.step_2_download.fetch import _download_paper_task

        mock_is_safe.return_value = True
        fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "patents", "CN110549905B.html")
        with open(fixture_path, "rb") as f:
            html_bytes = f.read()

        def fake_download(url, **kwargs):
            if "patentimages.storage.googleapis.com" in url:
                return b"%PDF-1.5 fake patent binary scan"
            return html_bytes

        mock_safe_download.side_effect = fake_download

        paper = Paper.objects.create(
            workspace=self.workspace,
            title="Energy Sharing System",
            hash_id="CN110549905BHASH",
            source_database="google_patents",
            original_pdf_path="https://patents.google.com/patent/CN110549905B/en",
            meta={"publication_number": "CN110549905B"},
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            screening_status="abstract_passed",
        )

        res = _download_paper_task(
            paper=paper,
            workspace_obj=self.workspace,
            pipeline_run_obj=self.pipeline_run,
        )

        self.assertEqual(res["status"], "downloaded")
        paper.refresh_from_db()

        self.assertIsNotNone(paper.original_pdf_path)
        self.assertTrue(default_storage.exists(paper.original_pdf_path))
        with default_storage.open(paper.original_pdf_path, "rb") as f:
            content = f.read()
        self.assertTrue(content.startswith(b"%PDF-1.5"))

        # Verify metadata
        details = paper.meta.get("google_patents_details")
        self.assertIsNotNone(details)
        self.assertEqual(details.get("current_assignee"), "GM Global Technology Operations LLC")
        self.assertEqual(details.get("status"), "Active")
        self.assertEqual(details.get("pdf_url"), "https://patentimages.storage.googleapis.com/95/72/73/d47f564213fea2/CN110549905B.pdf")
        self.assertTrue(details.get("has_pdf"))

    @patch("research_intelligence.tasks.step_4_screening.full_text.get_llm_provider")
    def test_screen_full_text_uses_markdown_document_for_patent(self, mock_get_llm):
        """
        Verify that full-text screening uses converted_md_path (markdown_ocr)
        when screening a patent that was stored as Markdown.
        """
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        from research_intelligence.tasks.step_4_screening.full_text import screen_full_text

        # Mock LLM provider response
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            {
                "passed": True,
                "decision_category": "ACCEPTED",
                "reasoning": "Directly matches quantum computing criteria.",
                "evidence_quotes": ["Quantum patent claims"],
            },
            {"prompt_tokens": 100, "candidates_tokens": 30, "total_tokens": 130},
        )
        mock_get_llm.return_value = mock_provider

        md_path = "workspaces/test/runs/test/documents/test_hash/document.md"
        default_storage.save(md_path, ContentFile("# US20260098257A1\n\n**Claims:** Quantum patent claims...".encode("utf-8")))

        paper = Paper.objects.create(
            workspace=self.workspace,
            title="Quantum Patent Screening Test",
            hash_id="SCREENINGPATENTHASH",
            source_database="google_patents",
            converted_md_path=md_path,
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            screening_status="pending",
        )

        res = screen_full_text(
            paper_id=paper.id,
            workspace_id=self.workspace.id,
            workspace_obj=self.workspace,
            paper_obj=paper,
            pipeline_run_id=str(self.pipeline_run.id),
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["input_source"], "markdown_ocr")
        self.assertEqual(res["decision_category"], "ACCEPTED")
        self.assertEqual(res["screening_status"], "full_text_passed")



