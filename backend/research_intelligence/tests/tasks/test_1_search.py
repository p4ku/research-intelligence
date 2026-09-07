import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from ...models import Workspace, PipelineRun, ComponentRun, Paper, Scraper
from ...tasks.step_1_search.search import (
    execute_workspace_search,
    execute_scraper_run_job,
    normalize_doi,
    normalize_arxiv_id,
    normalize_title,
    one_line,
)
from research_intelligence.scrapers.arxiv import ArxivScraperProvider
from research_intelligence.scrapers.openalex import OpenAlexScraperProvider
from research_intelligence.scrapers.lens import LensScraperProvider


class IngestionSearchTasksTestCase(TestCase):
    """
    Consolidated test suite for Step 1 (Search & Ingestion):
    1. Multi-source search triggering (ArXiv, OpenAlex, Lens) and active/inactive status handling.
    2. Search query deduplication by title, DOI, and arXiv ID within workspace.
    3. DOI, arXiv ID, and Title string normalization functions.
    4. Cross-database deduplication (e.g., ArXiv vs OpenAlex duplicates).
    5. Provider API payload parsers and inverted-index abstract reconstruction.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Search Test Project",
            abstract_acceptance_criteria="Accept active learning.",
            abstract_rejection_criteria="Reject rule-based systems."
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        
    @patch("research_intelligence.scrapers.lens.LensScraperProvider.search")
    @patch("research_intelligence.scrapers.openalex.OpenAlexScraperProvider.search")
    @patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.search")
    def test_execute_workspace_search_all_active(self, mock_arxiv_search, mock_openalex_search, mock_lens_search):
        Scraper.objects.create(workspace=self.workspace, provider="arxiv", search_query="arxiv query")
        Scraper.objects.create(workspace=self.workspace, provider="openalex", search_query="openalex query")
        Scraper.objects.create(workspace=self.workspace, provider="lens", search_query="lens query")
        
        mock_arxiv_search.return_value = [
            {
                "title": "Arxiv Paper",
                "authors": "Author A",
                "abstract": "Abstract A",
                "hash_id": "arxiv_123",
                "pdf_url": "https://arxiv.org/pdf/arxiv_123.pdf",
                "other_url": "https://arxiv.org/abs/arxiv_123",
                "source_database": "arxiv",
                "published_date": "2026-05-20"
            }
        ]
        mock_openalex_search.return_value = [
            {
                "title": "OpenAlex Paper",
                "authors": "Author B",
                "abstract": "Abstract B",
                "hash_id": "openalex_123",
                "pdf_url": "https://example.com/openalex_123.pdf",
                "other_url": "https://doi.org/10.1016/j.artint",
                "source_database": "openalex",
                "published_date": "2026-05-20"
            }
        ]
        mock_lens_search.return_value = [
            {
                "title": "Lens Paper",
                "authors": "Author C",
                "abstract": "Abstract C",
                "hash_id": "lens_123",
                "pdf_url": "https://example.com/lens_123.pdf",
                "other_url": "https://www.lens.org/lens/scholar/article/lens_123",
                "source_database": "lens",
                "published_date": "2026-05-20"
            }
        ]
        
        result = execute_workspace_search(self.workspace.id, self.pipeline_run.id, limit=20)
        self.assertEqual(len(result), 3)
        
        papers = Paper.objects.filter(workspace=self.workspace)
        self.assertEqual(papers.count(), 3)
        self.assertEqual(papers.filter(source_database="arxiv").count(), 1)
        self.assertEqual(papers.filter(source_database="openalex").count(), 1)
        self.assertEqual(papers.filter(source_database="lens").count(), 1)
        
        mock_arxiv_search.assert_called_once_with("arxiv query", limit=20, sort_by="relevance", sort_order="desc", start_date=None, end_date=None, n_last_days=7)
        mock_openalex_search.assert_called_once_with("openalex query", limit=20, sort_by="relevance", sort_order="desc", start_date=None, end_date=None, n_last_days=7)
        mock_lens_search.assert_called_once_with("lens query", limit=20, sort_by="relevance", sort_order="desc", start_date=None, end_date=None, n_last_days=7)

    @patch("research_intelligence.scrapers.lens.LensScraperProvider.search")
    @patch("research_intelligence.scrapers.openalex.OpenAlexScraperProvider.search")
    @patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.search")
    def test_execute_workspace_search_some_inactive(self, mock_arxiv_search, mock_openalex_search, mock_lens_search):
        Scraper.objects.create(workspace=self.workspace, provider="arxiv", search_query="arxiv query", is_active=True)
        Scraper.objects.create(workspace=self.workspace, provider="openalex", search_query="openalex query", is_active=False)
        
        mock_arxiv_search.return_value = [
            {
                "title": "Arxiv Paper Only",
                "authors": "Author A",
                "abstract": "Abstract A",
                "hash_id": "arxiv_123",
                "pdf_url": "https://arxiv.org/pdf/arxiv_123.pdf",
                "other_url": "https://arxiv.org/abs/arxiv_123",
                "source_database": "arxiv",
                "published_date": "2026-05-20"
            }
        ]
        
        result = execute_workspace_search(self.workspace.id, self.pipeline_run.id)
        self.assertEqual(len(result), 1)
        
        papers = Paper.objects.filter(workspace=self.workspace)
        self.assertEqual(papers.count(), 1)
        self.assertEqual(papers.first().title, "Arxiv Paper Only")
        
        mock_arxiv_search.assert_called_once_with("arxiv query", limit=50, sort_by="relevance", sort_order="desc", start_date=None, end_date=None, n_last_days=7)
        mock_openalex_search.assert_not_called()
        mock_lens_search.assert_not_called()

    @patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.search")
    def test_execute_workspace_search_deduplication(self, mock_arxiv_search):
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="existing_arxiv_hash",
            arxiv_id="2103.00020",
            title="Ingestion and Learning Systems",
            authors="John Smith",
            abstract="Existing abstract.",
            source_database="arxiv"
        )
        Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="existing_doi_hash",
            doi="10.1016/j.artint.2020.103328",
            title="Another Great Paper",
            authors="Jane Smith",
            abstract="Another abstract.",
            source_database="openalex"
        )

        Scraper.objects.create(workspace=self.workspace, provider="arxiv", search_query="arxiv query")

        mock_arxiv_search.return_value = [
            {
                "title": "Ingestion and Learning Systems!!!",
                "authors": "John Smith",
                "abstract": "...",
                "hash_id": "arxiv_dup_title",
                "pdf_url": "https://example.com/1.pdf",
                "other_url": "",
                "source_database": "arxiv",
                "published_date": "2026-05-20"
            },
            {
                "title": "New Title with Duplicate DOI",
                "authors": "Jane Smith",
                "abstract": "...",
                "hash_id": "arxiv_dup_doi",
                "pdf_url": "https://example.com/2.pdf",
                "other_url": "https://doi.org/10.1016/j.artint.2020.103328",
                "source_database": "arxiv",
                "published_date": "2026-05-20"
            },
            {
                "title": "New Title with Duplicate arXiv ID",
                "authors": "John Smith",
                "abstract": "...",
                "hash_id": "2103.00020v3",
                "pdf_url": "https://example.com/3.pdf",
                "other_url": "",
                "source_database": "arxiv",
                "published_date": "2026-05-20"
            },
            {
                "title": "A Completely Unique Paper",
                "authors": "Alex Smith",
                "abstract": "A completely new abstract.",
                "hash_id": "unique_id_999",
                "pdf_url": "https://example.com/unique.pdf",
                "other_url": "https://doi.org/10.1109/test.999",
                "source_database": "arxiv",
                "published_date": "2026-05-20"
            }
        ]

        result = execute_workspace_search(self.workspace.id, self.pipeline_run.id)
        self.assertEqual(len(result), 1)

        self.assertEqual(Paper.objects.filter(workspace=self.workspace).count(), 3)
        new_paper = Paper.objects.get(id=result[0])
        self.assertEqual(new_paper.title, "A Completely Unique Paper")
        mock_arxiv_search.assert_called_once_with("arxiv query", limit=50, sort_by="relevance", sort_order="desc", start_date=None, end_date=None, n_last_days=7)

    def test_normalization_functions(self):
        self.assertEqual(normalize_doi("https://doi.org/10.1145/3377325.3377498"), "10.1145/3377325.3377498")
        self.assertEqual(normalize_doi("http://doi.org/10.1145/3377325.3377498"), "10.1145/3377325.3377498")
        self.assertEqual(normalize_doi("doi:10.1145/3377325.3377498"), "10.1145/3377325.3377498")
        self.assertEqual(normalize_doi("10.1145/3377325.3377498 "), "10.1145/3377325.3377498")

        self.assertEqual(normalize_arxiv_id("arXiv:2401.12345v1"), "2401.12345")
        self.assertEqual(normalize_arxiv_id("arxiv:2401.12345v3"), "2401.12345")
        self.assertEqual(normalize_arxiv_id("2401.12345"), "2401.12345")

        self.assertEqual(normalize_title("Attention Is All You Need!"), "attentionisallyouneed")
        self.assertEqual(normalize_title("Attention is all you need: A Survey."), "attentionisallyouneedasurvey")

        self.assertEqual(one_line("Hybrid quantum-classical\n  computations"), "Hybrid quantum-classical computations")
        self.assertEqual(one_line("  padded\ttitle \n"), "padded title")
        self.assertEqual(one_line(""), "")
        self.assertEqual(one_line(None), "")

    @patch("research_intelligence.scrapers.openalex.OpenAlexScraperProvider.search")
    def test_ingested_title_and_abstract_are_single_lined(self, mock_openalex_search):
        """A provider's line wrapping must not reach the corpus (and the UI)."""
        Scraper.objects.create(workspace=self.workspace, provider="openalex", search_query="pennylane")

        mock_openalex_search.return_value = [
            {
                "title": "PennyLane: Automatic differentiation of hybrid quantum-classical\n  computations",
                "authors": "Ville Bergholm",
                "abstract": "PennyLane is a Python 3 software framework for\ndifferentiable programming of quantum computers.",
                "hash_id": "openalex_pennylane",
                "pdf_url": "https://arxiv.org/pdf/1811.04968.pdf",
                "other_url": "https://doi.org/10.48550/arXiv.1811.04968",
                "source_database": "openalex",
                "published_date": "2026-05-20",
            }
        ]

        execute_workspace_search(self.workspace.id, self.pipeline_run.id)

        paper = Paper.objects.get(workspace=self.workspace)
        self.assertEqual(
            paper.title,
            "PennyLane: Automatic differentiation of hybrid quantum-classical computations",
        )
        self.assertNotIn("\n", paper.abstract)

    def test_cross_source_search_deduplication(self):
        scraper_arxiv = Scraper.objects.create(workspace=self.workspace, provider="arxiv", search_query="transformer scaling")
        scraper_openalex = Scraper.objects.create(workspace=self.workspace, provider="openalex", search_query="transformer scaling")

        arxiv_items = [
            {
                "hash_id": "2401.00001",
                "arxiv_id": "arXiv:2401.00001v1",
                "doi": "10.1000/arxiv.2401.00001",
                "title": "Scaling Laws for Neural Language Models",
                "authors": "Jared Kaplan, Sam McCandlish",
                "abstract": "We investigate empirical scaling laws for language model performance.",
                "source_database": "arxiv",
                "pdf_url": "https://arxiv.org/pdf/2401.00001.pdf"
            }
        ]

        comp_run_arxiv = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            scraper=scraper_arxiv,
            step_type="search",
            component_name="arxiv_scraper",
            status="pending"
        )

        with patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.search.return_value = arxiv_items
            mock_get_provider.return_value = mock_provider

            res_arxiv = execute_scraper_run_job(str(comp_run_arxiv.id), limit=10)
            self.assertTrue(res_arxiv)

        self.assertEqual(Paper.objects.filter(workspace=self.workspace).count(), 1)

        openalex_items = [
            {
                "hash_id": "W2989912345",
                "arxiv_id": "2401.00001",
                "doi": "https://doi.org/10.1000/arxiv.2401.00001",
                "title": "Scaling Laws for Neural Language Models: An Empirical Analysis",
                "authors": "J. Kaplan, S. McCandlish",
                "abstract": "We investigate empirical scaling laws for language model performance.",
                "source_database": "openalex",
                "pdf_url": "https://openalex.org/pdf/2401.00001.pdf"
            }
        ]

        comp_run_openalex = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            scraper=scraper_openalex,
            step_type="search",
            component_name="openalex_scraper",
            status="pending"
        )

        with patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.search.return_value = openalex_items
            mock_get_provider.return_value = mock_provider

            res_openalex = execute_scraper_run_job(str(comp_run_openalex.id), limit=10)
            self.assertTrue(res_openalex)

        self.assertEqual(Paper.objects.filter(workspace=self.workspace).count(), 1)

    @patch("research_intelligence.scrapers.arxiv.urllib.request.urlopen")
    def test_arxiv_xml_atom_response_parsing(self, mock_urlopen):
        atom_xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title> Scalable High-Temperature Superconductors </title>
    <summary> We report a new room temperature superconducting phase. </summary>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <link title="pdf" href="http://arxiv.org/pdf/2401.12345v1" rel="related" type="application/pdf"/>
    <published>2024-01-15T12:00:00Z</published>
  </entry>
</feed>"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = atom_xml.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        provider = ArxivScraperProvider()
        results = provider.search("superconductors", limit=5)

        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["title"], "Scalable High-Temperature Superconductors")
        self.assertEqual(item["hash_id"], "2401.12345")
        self.assertIn("Alice Smith", item["authors"])
        self.assertIn("Bob Jones", item["authors"])
        self.assertEqual(item["pdf_url"], "http://arxiv.org/pdf/2401.12345v1")
        self.assertIn("meta", item)
        self.assertEqual(item["meta"]["id"], "http://arxiv.org/abs/2401.12345v1")
        self.assertEqual(item["meta"]["title"], "Scalable High-Temperature Superconductors")
        self.assertEqual(len(item["meta"]["authors"]), 2)
        self.assertEqual(item["meta"]["authors"][0]["name"], "Alice Smith")

    @patch("research_intelligence.scrapers.openalex.urllib.request.urlopen")
    def test_openalex_inverted_index_abstract_reconstruction(self, mock_urlopen):
        openalex_json = {
            "results": [
                {
                    "id": "https://openalex.org/W2741809807",
                    "title": "Quantum Error Mitigation for NISQ Devices",
                    "publication_date": "2023-11-20",
                    "authorships": [
                        {"author": {"display_name": "Charlie Brown"}},
                        {"author": {"display_name": "Diana Prince"}}
                    ],
                    "abstract_inverted_index": {
                        "Quantum": [0],
                        "error": [1],
                        "mitigation": [2],
                        "is": [3],
                        "critical": [4],
                        "for": [5],
                        "NISQ": [6],
                        "computing.": [7]
                    },
                    "best_oa_location": {
                        "pdf_url": "https://arxiv.org/pdf/2311.99999.pdf"
                    },
                    "doi": "https://doi.org/10.1103/PhysRevA.99.012345"
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(openalex_json).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        provider = OpenAlexScraperProvider()
        results = provider.search("quantum error mitigation", limit=5)

        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertIn("meta", item)
        self.assertEqual(item["meta"]["id"], "https://openalex.org/W2741809807")
        self.assertEqual(item["title"], "Quantum Error Mitigation for NISQ Devices")
        self.assertEqual(item["abstract"], "Quantum error mitigation is critical for NISQ computing.")
        self.assertEqual(item["authors"], "Charlie Brown, Diana Prince")
        self.assertEqual(item["pdf_url"], "https://arxiv.org/pdf/2311.99999.pdf")
        self.assertEqual(item["other_url"], "https://doi.org/10.1103/PhysRevA.99.012345")

    def test_lens_scraper_without_api_key_returns_empty_list_safely(self):
        with override_settings(LENS_API_KEY=None):
            provider = LensScraperProvider()
            results = provider.search("solid state battery")
            self.assertEqual(results, [])

    @patch("research_intelligence.scrapers.lens.urllib.request.urlopen")
    def test_lens_scholarly_json_response_parsing(self, mock_urlopen):
        lens_json = {
            "data": [
                {
                    "lens_id": "012-345-678-901-234",
                    "title": "Silicon Anode Degradation in Lithium Batteries",
                    "date_published": "2024-02-01",
                    "abstract": "We analyze capacity fade in silicon anodes.",
                    "authors": [
                        {"display_name": "Eva Green"}
                    ],
                    "source_urls": [
                        {"url": "https://publisher.com/article.pdf"}
                    ],
                    "external_ids": [
                        {"type": "doi", "value": "10.1016/j.jpowsour.2024.01"}
                    ]
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(lens_json).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with override_settings(LENS_API_KEY="test_mock_lens_key"):
            provider = LensScraperProvider()
            results = provider.search("silicon anode", limit=5)
            self.assertEqual(len(results), 1)
            item = results[0]
            self.assertEqual(item["title"], "Silicon Anode Degradation in Lithium Batteries")
            self.assertEqual(item["authors"], "Eva Green")
            self.assertEqual(item["pdf_url"], "https://publisher.com/article.pdf")
            self.assertEqual(item["other_url"], "https://www.lens.org/lens/scholar/article/012-345-678-901-234")

    @patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider")
    def test_execute_scraper_run_job_with_date_range(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.search.return_value = []
        mock_get_provider.return_value = mock_provider

        scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="quantum dot",
            is_active=True
        )
        comp_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="search",
            component_name="arxiv_scraper",
            scraper=scraper,
            status="pending",
            input_params={
                "start_date": "2026-08-01",
                "end_date": "2026-08-15",
                "n_last_days": 14
            }
        )

        ok = execute_scraper_run_job(str(comp_run.id))
        self.assertNotEqual(ok, False)

        mock_get_provider.assert_called_once_with("arxiv", n_last_days=14)
        mock_provider.search.assert_called_once()
        call_kwargs = mock_provider.search.call_args[1]
        self.assertEqual(call_kwargs.get("start_date"), "2026-08-01")
        self.assertEqual(call_kwargs.get("end_date"), "2026-08-15")
        self.assertEqual(call_kwargs.get("n_last_days"), 14)

    @patch("research_intelligence.tasks.step_1_search.search.get_scraper_provider")
    def test_multi_scraper_cross_provider_deduplication(self, mock_get_provider):
        """
        Verify that when two scrapers from different providers (e.g. ArXiv and OpenAlex)
        scrape the same paper, only 1 Paper row is created, missing fields are enriched,
        and only 1 PaperMetric row is linked to the active PipelineRun.
        """
        from research_intelligence.models import PaperMetric
        from research_intelligence.tasks.step_1_search.node import SearchNode

        arxiv_scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="transformers attention",
            is_active=True
        )
        openalex_scraper = Scraper.objects.create(
            workspace=self.workspace,
            provider="openalex",
            search_query="transformers attention",
            is_active=True
        )

        arxiv_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="search",
            component_name="arxiv_scraper",
            scraper=arxiv_scraper,
            status="pending",
            input_params={}
        )
        openalex_run = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="search",
            component_name="openalex_scraper",
            scraper=openalex_scraper,
            status="pending",
            input_params={}
        )

        mock_arxiv_provider = MagicMock()
        mock_arxiv_provider.search.return_value = [
            {
                "title": "Attention Is All You Need",
                "authors": "Vaswani et al.",
                "abstract": "We introduce the Transformer architecture...",
                "hash_id": "1706.03762",
                "arxiv_id": "1706.03762",
                "doi": "10.48550/arXiv.1706.03762",
                "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
                "source_database": "arxiv",
                "published_date": "2017-06-12",
                "meta": {"arxiv_version": "v1"}
            }
        ]

        mock_openalex_provider = MagicMock()
        mock_openalex_provider.search.return_value = [
            {
                "title": "Attention is all you need!",
                "authors": "Ashish Vaswani, Noam Shazeer",
                "abstract": "The dominant sequence transduction models...",
                "hash_id": "W2963403868",
                "doi": "10.48550/arxiv.1706.03762",
                "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
                "other_url": "https://openalex.org/W2963403868",
                "source_database": "openalex",
                "published_date": "2017-06-12",
                "meta": {"cited_by_count": 95000}
            }
        ]

        def provider_side_effect(provider_name, **kwargs):
            if provider_name == "arxiv":
                return mock_arxiv_provider
            return mock_openalex_provider

        mock_get_provider.side_effect = provider_side_effect

        # 1. Execute ArXiv scraper
        ok1 = execute_scraper_run_job(str(arxiv_run.id))
        self.assertTrue(ok1)
        arxiv_run.refresh_from_db()
        self.assertEqual(arxiv_run.metrics["total_created"], 1)
        self.assertEqual(arxiv_run.metrics["duplicates_count"], 0)

        # 2. Execute OpenAlex scraper
        ok2 = execute_scraper_run_job(str(openalex_run.id))
        self.assertTrue(ok2)
        openalex_run.refresh_from_db()
        self.assertEqual(openalex_run.metrics["total_created"], 0)
        self.assertEqual(openalex_run.metrics["duplicates_count"], 1)

        # 3. Assert exactly ONE Paper exists in workspace
        papers = Paper.objects.filter(workspace=self.workspace)
        self.assertEqual(papers.count(), 1)
        paper = papers.first()
        self.assertEqual(paper.arxiv_id, "1706.03762")
        self.assertTrue("1706.03762" in paper.doi)

        # 4. Assert exactly ONE PaperMetric exists for this pipeline run
        metrics = PaperMetric.objects.filter(paper=paper, pipeline_run=self.pipeline_run)
        self.assertEqual(metrics.count(), 1)

        # 5. PipelineRun.get_papers() returns exactly 1 paper for Downloader
        run_papers = list(self.pipeline_run.get_papers())
        self.assertEqual(len(run_papers), 1)
        self.assertEqual(run_papers[0].id, paper.id)

    def test_search_node_halt_waits_for_parallel_scrapers(self):
        """
        Verify that SearchNode.should_halt_pipeline does NOT prematurely halt if one scraper
        finished with 0 papers while another parallel scraper is still running or pending.
        """
        from research_intelligence.tasks.step_1_search.node import SearchNode

        scraper_1 = Scraper.objects.create(workspace=self.workspace, provider="arxiv", search_query="q1")
        scraper_2 = Scraper.objects.create(workspace=self.workspace, provider="openalex", search_query="q2")

        run_1 = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="search",
            component_name="arxiv_scraper",
            scraper=scraper_1,
            status="completed",
            metrics={"total_fetched": 0, "total_created": 0, "duplicates_count": 0}
        )
        run_2 = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="search",
            component_name="openalex_scraper",
            scraper=scraper_2,
            status="running",
            metrics={}
        )

        node = SearchNode()
        # While run_2 is running, pipeline must NOT halt even though run_1 completed with 0 papers
        should_halt, msg = node.should_halt_pipeline(self.pipeline_run, self.workspace, {})
        self.assertFalse(should_halt)
        self.assertIsNone(msg)

        # Once run_2 finishes with 0 papers as well, should_halt must cleanly return True with aggregated metrics
        run_2.status = "completed"
        run_2.metrics = {"total_fetched": 5, "total_created": 0, "duplicates_count": 5}
        run_2.save()

        should_halt, msg = node.should_halt_pipeline(self.pipeline_run, self.workspace, {})
        self.assertTrue(should_halt)
        self.assertIn("5 on data sources", msg)
        self.assertIn("all 5 were already ingested", msg)


