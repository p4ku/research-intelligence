from django.test import TestCase
from unittest.mock import patch
from ...models import Workspace, PipelineRun, Paper, Scraper
from ...tasks.step_1_search.search import execute_workspace_search

class IngestionSearchTasksTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Search Test Project",
            acceptance_criteria="Accept active learning.",
            rejection_criteria="Reject rule-based systems."
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        
    @patch("research_intelligence.scrapers.lens.LensScraperProvider.search")
    @patch("research_intelligence.scrapers.openalex.OpenAlexScraperProvider.search")
    @patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.search")
    def test_execute_workspace_search_all_active(self, mock_arxiv_search, mock_openalex_search, mock_lens_search):
        # Create active scrapers for all three
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
        # Should return list of all ingested paper IDs (3 unique papers)
        self.assertEqual(len(result), 3)
        
        # Verify database contents
        papers = Paper.objects.filter(workspace=self.workspace)
        self.assertEqual(papers.count(), 3)
        self.assertEqual(papers.filter(source_database="arxiv").count(), 1)
        self.assertEqual(papers.filter(source_database="openalex").count(), 1)
        self.assertEqual(papers.filter(source_database="lens").count(), 1)
        
        mock_arxiv_search.assert_called_once_with("arxiv query", limit=20)
        mock_openalex_search.assert_called_once_with("openalex query", limit=20)
        mock_lens_search.assert_called_once_with("lens query", limit=20)

    @patch("research_intelligence.scrapers.lens.LensScraperProvider.search")
    @patch("research_intelligence.scrapers.openalex.OpenAlexScraperProvider.search")
    @patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.search")
    def test_execute_workspace_search_some_inactive(self, mock_arxiv_search, mock_openalex_search, mock_lens_search):
        # Arxiv active, OpenAlex inactive, Lens not created
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
        
        mock_arxiv_search.assert_called_once_with("arxiv query", limit=50)
        mock_openalex_search.assert_not_called()
        mock_lens_search.assert_not_called()

    @patch("research_intelligence.scrapers.arxiv.ArxivScraperProvider.search")
    def test_execute_workspace_search_deduplication(self, mock_arxiv_search):
        # Setup existing papers for workspace
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

        # Mock search returns:
        # 1. A paper with matching title but different casing/punctuation
        # 2. A paper with matching DOI but formatted differently
        # 3. A paper with matching arXiv ID but with version suffix
        # 4. A completely new unique paper
        mock_arxiv_search.return_value = [
            {
                "title": "Ingestion and Learning Systems!!!",  # Duplicate Title (norm = ingestionandlearningsystems)
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
                "other_url": "https://doi.org/10.1016/j.artint.2020.103328",  # Duplicate DOI
                "source_database": "arxiv",
                "published_date": "2026-05-20"
            },
            {
                "title": "New Title with Duplicate arXiv ID",
                "authors": "John Smith",
                "abstract": "...",
                "hash_id": "2103.00020v3",  # Duplicate arXiv ID (version normalized to 2103.00020)
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
        # Should only ingest the unique paper (1 paper)
        self.assertEqual(len(result), 1)

        # Total papers in database should be 3 (2 original setup + 1 newly ingested)
        self.assertEqual(Paper.objects.filter(workspace=self.workspace).count(), 3)
        
        # Verify the newly ingested paper title
        new_paper = Paper.objects.get(id=result[0])
        self.assertEqual(new_paper.title, "A Completely Unique Paper")
        mock_arxiv_search.assert_called_once_with("arxiv query", limit=50)

