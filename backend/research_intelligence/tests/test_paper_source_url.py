import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory
from research_intelligence.models import Workspace, Paper, PipelineRun, PaperMetric, WorkspaceMember, DocumentRegistry
from api.serializers.papers import PaperSerializer
from api.views.papers import PaperViewSet
from research_intelligence.services.scraper_service import list_workspace_papers
from mcp_server.tools.scrapers.search import list_papers_logic

from research_intelligence.utils.source_url import resolve_paper_source_url

User = get_user_model()


class PaperSourceUrlTestCase(TestCase):
    """
    Test suite verifying canonical source_url resolution across academic providers
    (ArXiv, OpenAlex with DOI, OpenAlex without DOI, Lens.org), DRF API serialization,
    and MCP server tool payloads.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="testresearcher", password="password123")
        self.workspace = Workspace.objects.create(name="Source URL Test Workspace")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")
        self.pipeline_run = PipelineRun.objects.create(workspace=self.workspace, status="completed")

    def test_arxiv_paper_source_url(self):
        """Verify arXiv paper resolves to canonical https://arxiv.org/abs/{arxiv_id}."""
        url = resolve_paper_source_url(arxiv_id="2303.08774")
        self.assertEqual(url, "https://arxiv.org/abs/2303.08774")

        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="arxiv_2303_08774",
            arxiv_id="2303.08774",
            source_url=url,
            title="GPT-4 Technical Report",
            authors="OpenAI",
            source_database="arxiv"
        )
        self.assertEqual(paper.source_url, "https://arxiv.org/abs/2303.08774")

        # Also verify if arxiv_id has arxiv: prefix
        url_prefix = resolve_paper_source_url(arxiv_id="arxiv:1706.03762")
        self.assertEqual(url_prefix, "https://arxiv.org/abs/1706.03762")

        paper_prefix = Paper.objects.create(
            workspace=self.workspace,
            hash_id="arxiv_prefix_123",
            arxiv_id="arxiv:1706.03762",
            source_url=url_prefix,
            title="Attention Is All You Need",
            authors="Vaswani et al.",
            source_database="arxiv"
        )
        self.assertEqual(paper_prefix.source_url, "https://arxiv.org/abs/1706.03762")

    def test_openalex_paper_with_doi_source_url(self):
        """Verify OpenAlex paper with DOI resolves to https://doi.org/{doi} publisher landing."""
        url = resolve_paper_source_url(
            doi="10.1016/j.artint.2020.103328",
            meta={"id": "https://openalex.org/W2963403868"},
            source_database="openalex"
        )
        self.assertEqual(url, "https://doi.org/10.1016/j.artint.2020.103328")

        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="openalex_w123_doi",
            doi="10.1016/j.artint.2020.103328",
            source_url=url,
            title="Reasoning About Actions",
            authors="John McCarthy",
            source_database="openalex",
            meta={"id": "https://openalex.org/W2963403868"}
        )
        self.assertEqual(paper.source_url, "https://doi.org/10.1016/j.artint.2020.103328")

    def test_openalex_paper_without_doi_id_url(self):
        """Verify OpenAlex paper without DOI falls back to OpenAlex canonical URL from meta['id']."""
        raw_meta = {
            "id": "https://openalex.org/W4386266395",
            "open_access": {"is_oa": True}
        }
        url = resolve_paper_source_url(meta=raw_meta, source_database="openalex")
        self.assertEqual(url, "https://openalex.org/W4386266395")

        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="openalex_no_doi_1",
            title="Institutional Technical Report",
            authors="Jane Doe",
            source_database="openalex",
            source_url=url,
            meta=raw_meta
        )
        self.assertEqual(paper.source_url, "https://openalex.org/W4386266395")

    def test_openalex_paper_without_doi_landing_page_url(self):
        """Verify OpenAlex paper without DOI with primary_location.landing_page_url resolves properly."""
        raw_meta = {
            "primary_location": {
                "landing_page_url": "https://repository.tudelft.nl/islandora/object/uuid%3A1234"
            }
        }
        url = resolve_paper_source_url(meta=raw_meta, source_database="openalex")
        self.assertEqual(url, "https://repository.tudelft.nl/islandora/object/uuid%3A1234")

        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="openalex_no_doi_landing",
            title="TU Delft Repository Report",
            authors="Delft Team",
            source_database="openalex",
            source_url=url,
            meta=raw_meta
        )
        self.assertEqual(paper.source_url, "https://repository.tudelft.nl/islandora/object/uuid%3A1234")

    def test_openalex_fallback_work_id_hash(self):
        """Verify OpenAlex paper with W... hash_id generates https://openalex.org/{W_id} if no meta is available."""
        url = resolve_paper_source_url(hash_id="W1982736450", source_database="openalex")
        self.assertEqual(url, "https://openalex.org/W1982736450")

        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="W1982736450",
            source_url=url,
            title="Legacy OpenAlex Paper",
            authors="Author X",
            source_database="openalex"
        )
        self.assertEqual(paper.source_url, "https://openalex.org/W1982736450")

    def test_lens_paper_source_url(self):
        """Verify Lens paper with meta other_url resolves properly."""
        raw_meta = {
            "other_url": "https://www.lens.org/lens/scholar/article/012-345-678-901-234"
        }
        url = resolve_paper_source_url(meta=raw_meta, source_database="lens")
        self.assertEqual(url, "https://www.lens.org/lens/scholar/article/012-345-678-901-234")

        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="lens_doc_1",
            title="Solid-State Battery Breakthrough",
            authors="Battery Lab",
            source_database="lens",
            source_url=url,
            meta=raw_meta
        )
        self.assertEqual(paper.source_url, "https://www.lens.org/lens/scholar/article/012-345-678-901-234")

    def test_paper_serializer_exposes_source_url(self):
        """Verify PaperSerializer includes source_url in serialized output."""
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="arxiv_test_serializer",
            arxiv_id="2103.00020",
            source_url="https://arxiv.org/abs/2103.00020",
            title="Self-Supervised Learning",
            authors="Yann LeCun",
            source_database="arxiv"
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="accepted"
        )

        serializer = PaperSerializer(paper)
        data = serializer.data
        self.assertIn("source_url", data)
        self.assertEqual(data["source_url"], "https://arxiv.org/abs/2103.00020")

    def test_paper_viewset_scorecard_action_exposes_source_url(self):
        """Verify GET /api/papers/{id}/scorecard/ includes source_url."""
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="scorecard_test_paper",
            doi="10.1145/3318464.3389700",
            source_url="https://doi.org/10.1145/3318464.3389700",
            title="ACM Conference Paper",
            authors="ACM Authors",
            source_database="openalex"
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="accepted"
        )

        from rest_framework.test import force_authenticate
        factory = APIRequestFactory()
        request = factory.get(f"/api/papers/{paper.id}/scorecard/")
        force_authenticate(request, user=self.user)

        view = PaperViewSet.as_view({'get': 'scorecard'})
        response = view(request, pk=str(paper.id))
        self.assertEqual(response.status_code, 200)
        paper_result = response.data.get("paper", {})
        self.assertIn("source_url", paper_result)
        self.assertEqual(paper_result["source_url"], "https://doi.org/10.1145/3318464.3389700")

    def test_mcp_list_papers_logic_returns_source_url(self):
        """Verify MCP list_papers_logic tool returns source_url in JSON payload."""
        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="mcp_paper_test",
            arxiv_id="2401.99999",
            source_url="https://arxiv.org/abs/2401.99999",
            title="MCP Scientific Tool Ingestion",
            authors="Anthropic & SRI",
            source_database="arxiv"
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="pending"
        )

        raw_json = list_papers_logic(self.user, str(self.workspace.id))
        parsed = json.loads(raw_json)
        self.assertIsInstance(parsed, list)
        self.assertTrue(len(parsed) >= 1)
        found = next((p for p in parsed if p.get("paper_id") == str(paper.id)), None)
        self.assertIsNotNone(found)
        self.assertIn("source_url", found)
        self.assertEqual(found["source_url"], "https://arxiv.org/abs/2401.99999")

    def test_source_url_persisted_to_db_and_document_registry(self):
        """
        Verify that source_url is stored in the database table, filterable via SQL,
        and synced to DocumentRegistry upon PDF registration.
        """
        from research_intelligence.tasks.step_2_download.pdf_cache import register_document_pdf
        from research_intelligence.models import DocumentRegistry

        paper = Paper.objects.create(
            workspace=self.workspace,
            hash_id="db_persisted_url_test",
            arxiv_id="2402.11111",
            source_url="https://arxiv.org/abs/2402.11111",
            title="Database Persisted Source URL",
            authors="Author DB",
            source_database="arxiv"
        )
        # Verify it is persisted in database column
        paper.refresh_from_db()
        self.assertEqual(paper.source_url, "https://arxiv.org/abs/2402.11111")

        # Verify SQL filtering works
        matched = Paper.objects.filter(source_url__contains="2402.11111")
        self.assertEqual(matched.count(), 1)
        self.assertEqual(matched.first().id, paper.id)

        # Verify DocumentRegistry sync
        doc = register_document_pdf(
            paper=paper,
            file_bytes=b"%PDF-1.4 mock binary data for registry"
        )
        self.assertEqual(doc.source_url, "https://arxiv.org/abs/2402.11111")
        doc.refresh_from_db()
        self.assertEqual(doc.source_url, "https://arxiv.org/abs/2402.11111")

    def test_resolve_paper_source_url_helper(self):
        """
        Verify the standalone helper function works with dicts, model instances, and kwargs.
        """
        from research_intelligence.utils.source_url import resolve_paper_source_url

        # Direct kwargs
        self.assertEqual(
            resolve_paper_source_url(doi="10.1234/test.doi"),
            "https://doi.org/10.1234/test.doi"
        )
        self.assertEqual(
            resolve_paper_source_url(arxiv_id="2401.00001"),
            "https://arxiv.org/abs/2401.00001"
        )

        # Dict input
        self.assertEqual(
            resolve_paper_source_url({"doi": "10.5555/dict.doi"}),
            "https://doi.org/10.5555/dict.doi"
        )
        self.assertEqual(
            resolve_paper_source_url({"meta": {"primary_location": {"landing_page_url": "https://nature.com/articles/123"}}}),
            "https://nature.com/articles/123"
        )

        # Existing source_url has priority
        self.assertEqual(
            resolve_paper_source_url({"source_url": "https://custom.org/paper", "doi": "10.1234/other"}),
            "https://custom.org/paper"
        )

    def test_models_have_no_magical_save_override(self):
        """
        Ensure neither Paper nor DocumentRegistry overrides save().
        Data is explicitly persisted without hidden hooks or lifecycle magic.
        """
        self.assertNotIn("save", Paper.__dict__)
        self.assertNotIn("save", DocumentRegistry.__dict__)

        # Paper created without source_url retains None (no magic populating it behind the scenes)
        p_empty = Paper.objects.create(
            workspace=self.workspace,
            hash_id="no_magic_empty_url",
            arxiv_id="2401.55555",
            source_url=None,
            title="Clean Paper",
            authors="Clean Author",
            source_database="arxiv"
        )
        p_empty.refresh_from_db()
        self.assertIsNone(p_empty.source_url)

        # Paper created with explicit source_url persists cleanly
        p_explicit = Paper.objects.create(
            workspace=self.workspace,
            hash_id="explicit_url_paper",
            arxiv_id="2401.66666",
            source_url="https://arxiv.org/abs/2401.66666",
            title="Explicit URL Paper",
            authors="Explicit Author",
            source_database="arxiv"
        )
        p_explicit.refresh_from_db()
        self.assertEqual(p_explicit.source_url, "https://arxiv.org/abs/2401.66666")

    def test_arxiv_atom_xml_parses_source_url(self):
        """
        Verify ArxivScraperProvider parses canonical source_url from arXiv Atom XML directly.
        """
        from research_intelligence.scrapers.arxiv import ArxivScraperProvider
        provider = ArxivScraperProvider()

        sample_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2303.08774v1</id>
    <title>GPT-4 Technical Report</title>
    <summary>We report the development of GPT-4...</summary>
    <published>2023-03-15T00:00:00Z</published>
    <author><name>OpenAI</name></author>
    <link href="http://arxiv.org/abs/2303.08774v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2303.08774v1" rel="related" type="application/pdf"/>
  </entry>
</feed>"""

        results = provider._parse_arxiv_atom_xml(sample_xml)
        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["hash_id"], "2303.08774")
        self.assertEqual(item["source_url"], "https://arxiv.org/abs/2303.08774")
        self.assertEqual(item["other_url"], "http://arxiv.org/abs/2303.08774v1")

    @patch("urllib.request.urlopen")
    def test_openalex_scraper_populates_source_url(self, mock_urlopen):
        """
        Verify OpenAlexScraperProvider populates source_url directly in search results.
        Covers DOI format, landing_page_url fallback, and OpenAlex work ID fallback.
        """
        from research_intelligence.scrapers.openalex import OpenAlexScraperProvider
        provider = OpenAlexScraperProvider()

        fake_api_response = {
            "results": [
                {
                    "id": "https://openalex.org/W1001",
                    "title": "OpenAlex Paper with DOI",
                    "doi": "https://doi.org/10.1016/j.artint.2020.103328",
                    "publication_date": "2020-01-01",
                    "authorships": [{"author": {"display_name": "Alice Researcher"}}],
                },
                {
                    "id": "https://openalex.org/W1002",
                    "title": "OpenAlex Paper with Landing Page",
                    "doi": None,
                    "publication_date": "2021-05-10",
                    "primary_location": {
                        "landing_page_url": "https://repository.tudelft.nl/uuid:1234"
                    },
                    "authorships": [{"author": {"display_name": "Bob Scientist"}}],
                },
                {
                    "id": "https://openalex.org/W1003",
                    "title": "OpenAlex Paper without Landing Page",
                    "doi": None,
                    "publication_date": "2022-09-15",
                    "primary_location": None,
                    "authorships": [{"author": {"display_name": "Charlie Engineer"}}],
                }
            ]
        }

        mock_cm = MagicMock()
        mock_cm.__enter__.return_value.read.return_value = json.dumps(fake_api_response).encode("utf-8")
        mock_urlopen.return_value = mock_cm

        results = provider.search(query="artificial intelligence", limit=5)
        self.assertEqual(len(results), 3)

        # 1. DOI
        self.assertEqual(results[0]["source_url"], "https://doi.org/10.1016/j.artint.2020.103328")
        # 2. Landing page
        self.assertEqual(results[1]["source_url"], "https://repository.tudelft.nl/uuid:1234")
        # 3. OpenAlex ID fallback
        self.assertEqual(results[2]["source_url"], "https://openalex.org/W1003")

    @override_settings(LENS_API_KEY="mock_lens_token")
    @patch("urllib.request.urlopen")
    def test_lens_scraper_populates_source_url(self, mock_urlopen):
        """
        Verify LensScraperProvider populates source_url directly from lens_id.
        """
        from research_intelligence.scrapers.lens import LensScraperProvider
        provider = LensScraperProvider()

        fake_lens_response = {
            "data": [
                {
                    "title": "Lens Breakthrough Study",
                    "lens_id": "012-345-678-901-234",
                    "date_published": "2024-02-01",
                    "abstract": "Breakthrough in solid state tech.",
                    "authors": [{"display_name": "Dr. Battery"}],
                    "source_urls": [{"url": "https://example.com/paper.pdf"}]
                }
            ]
        }

        mock_cm = MagicMock()
        mock_cm.__enter__.return_value.read.return_value = json.dumps(fake_lens_response).encode("utf-8")
        mock_urlopen.return_value = mock_cm

        results = provider.search(
            query="solid state battery",
            limit=5
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source_url"], "https://www.lens.org/lens/scholar/article/012-345-678-901-234")

    def test_email_digest_payload_and_template_renders_source_url(self):
        """
        Verify that build_pipeline_run_digest_payload extracts paper.source_url,
        and that pipeline_digest HTML & text templates render the source URL with badges and links.
        """
        from research_intelligence.tasks.auxiliary.email_digest import build_pipeline_run_digest_payload

        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="digest_source_url_test",
            arxiv_id="2403.01234",
            source_url="https://arxiv.org/abs/2403.01234",
            title="Digest Source URL Verification Paper",
            authors="Test Author",
            abstract="Testing email digest source url rendering."
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="accepted"
        )

        payload = build_pipeline_run_digest_payload(self.pipeline_run)
        papers_data = payload["context"]["papers_data"]
        self.assertEqual(len(papers_data), 1)
        self.assertEqual(papers_data[0]["source_url"], "https://arxiv.org/abs/2403.01234")

        # Verify HTML template contains source_url in title link and scorecard item
        html = payload["html_content"]
        self.assertIn('href="https://arxiv.org/abs/2403.01234"', html)
        self.assertIn("Source URL:</strong>", html)

        # Verify Plaintext template contains source_url
        text = payload["text_content"]
        self.assertIn("- Source URL: https://arxiv.org/abs/2403.01234", text)

    @patch("research_intelligence.llm_providers.get_llm_provider")
    def test_narrative_report_prompt_context_includes_source_url(self, mock_get_llm):
        """
        Verify that generate_executive_narrative_report includes source_url in both
        {papers_json} and formatted text {papers} prompt contexts.
        """
        from research_intelligence.tasks.step_7_reporting.narrative import generate_executive_narrative_report

        mock_provider = MagicMock()
        mock_provider.generate.return_value = "### Executive Summary\nSynthesized report content."
        mock_get_llm.return_value = mock_provider

        self.workspace.narrative_report_prompt = (
            "Briefing:\n"
            "Catalog:\n{papers}\n"
            "Structured:\n{papers_json}\n"
        )
        self.workspace.save()

        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="narrative_source_url_test",
            arxiv_id="2403.99888",
            source_url="https://arxiv.org/abs/2403.99888",
            title="Narrative Report URL Paper",
            authors="Jane Narrative",
            source_database="arxiv"
        )
        PaperMetric.objects.create(
            paper=paper,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="accepted",
            signal_score=95.0
        )

        res = generate_executive_narrative_report(self.pipeline_run)
        self.assertTrue(res["success"])

        mock_provider.generate.assert_called_once()
        prompt = mock_provider.generate.call_args[1]["prompt"]

        # 1. Formatted text block contains URL
        self.assertIn("URL: https://arxiv.org/abs/2403.99888", prompt)

        # 2. Structured JSON block contains "source_url"
        self.assertIn('"source_url": "https://arxiv.org/abs/2403.99888"', prompt)

    def test_admin_source_link_badge(self):
        """
        Verify PaperAdmin and DocumentRegistryAdmin source_link_badge method renders
        a clickable green badge when source_url is present, and '-' when absent.
        """
        from research_intelligence.admin import PaperAdmin, DocumentRegistryAdmin
        from django.contrib.admin.sites import AdminSite

        paper_admin = PaperAdmin(Paper, AdminSite())
        doc_admin = DocumentRegistryAdmin(DocumentRegistry, AdminSite())

        # With URL
        paper_with_url = Paper(source_url="https://doi.org/10.1000/182")
        badge_html = paper_admin.source_link_badge(paper_with_url)
        self.assertIn('href="https://doi.org/10.1000/182"', str(badge_html))
        self.assertIn("🌐 Source ↗", str(badge_html))

        doc_with_url = DocumentRegistry(source_url="https://arxiv.org/abs/2401.00001")
        doc_badge_html = doc_admin.source_link_badge(doc_with_url)
        self.assertIn('href="https://arxiv.org/abs/2401.00001"', str(doc_badge_html))
        self.assertIn("🌐 Source ↗", str(doc_badge_html))

        # Without URL
        paper_no_url = Paper(source_url="")
        self.assertIn("-", str(paper_admin.source_link_badge(paper_no_url)))

        doc_no_url = DocumentRegistry(source_url=None)
        self.assertIn("-", str(doc_admin.source_link_badge(doc_no_url)))


