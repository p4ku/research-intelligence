import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model

from research_intelligence.models import Workspace, PipelineRun, ComponentRun, Paper, Scraper
from research_intelligence.tasks.step_1_search.search import (
    normalize_doi,
    normalize_arxiv_id,
    normalize_title,
    execute_scraper_run_job
)

User = get_user_model()


class SearchDeduplicationMultiSourceTestCase(TestCase):
    """
    Tests multi-source search ingestion and cross-database deduplication (Step 1):
    1. Normalization of DOIs (stripping https://doi.org/, doi:, casing).
    2. Normalization of arXiv IDs (stripping arxiv: prefix and version numbers v1/v2).
    3. Normalization of Titles (case folding, non-alphanumeric character stripping).
    4. Multi-source deduplication preventing duplicate Paper creation across ArXiv, OpenAlex, and Lens.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="dedup_tester", email="dedup@example.com", password="password123")
        self.workspace = Workspace.objects.create(name="Deduplication Lab")
        self.pipeline_run = PipelineRun.objects.create(workspace=self.workspace, triggered_by=self.user, status="running")

        self.scraper_arxiv = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="transformer scaling"
        )
        self.scraper_openalex = Scraper.objects.create(
            workspace=self.workspace,
            provider="openalex",
            search_query="transformer scaling"
        )

    def test_normalization_functions(self):
        """
        Tests DOI, arXiv ID, and title normalization helper functions.
        """
        # DOI Normalization
        self.assertEqual(normalize_doi("https://doi.org/10.1145/3377325.3377498"), "10.1145/3377325.3377498")
        self.assertEqual(normalize_doi("http://doi.org/10.1145/3377325.3377498"), "10.1145/3377325.3377498")
        self.assertEqual(normalize_doi("doi:10.1145/3377325.3377498"), "10.1145/3377325.3377498")
        self.assertEqual(normalize_doi("10.1145/3377325.3377498 "), "10.1145/3377325.3377498")

        # arXiv ID Normalization (strips version and prefix)
        self.assertEqual(normalize_arxiv_id("arXiv:2401.12345v1"), "2401.12345")
        self.assertEqual(normalize_arxiv_id("arxiv:2401.12345v3"), "2401.12345")
        self.assertEqual(normalize_arxiv_id("2401.12345"), "2401.12345")

        # Title Normalization (alphanumeric only, lowercase)
        self.assertEqual(normalize_title("Attention Is All You Need!"), "attentionisallyouneed")
        self.assertEqual(normalize_title("Attention is all you need: A Survey."), "attentionisallyouneedasurvey")

    def test_cross_source_search_deduplication(self):
        """
        Runs two scraper jobs where OpenAlex returns the same paper previously ingested by ArXiv.
        Verifies that only 1 Paper DB record is created and the duplicate is skipped.
        """
        # 1. Run ArXiv Scraper
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
            scraper=self.scraper_arxiv,
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

        # 2. Run OpenAlex Scraper with the same paper (different ID format, slightly altered title)
        openalex_items = [
            {
                "hash_id": "W999888777",
                "arxiv_id": "2401.00001v2",  # Updated version of same arXiv paper
                "doi": "https://doi.org/10.1000/ARXIV.2401.00001",  # Same DOI with URL prefix and uppercase
                "title": "Scaling Laws for Neural Language Models!",  # Same title with punctuation
                "authors": "J. Kaplan, S. McCandlish",
                "abstract": "We investigate empirical scaling laws.",
                "source_database": "openalex",
                "pdf_url": "https://openalex.org/pdf/W999888777.pdf"
            },
            {
                "hash_id": "W111222333",
                "arxiv_id": None,
                "doi": "10.1000/new.paper.2024",
                "title": "Completely Novel Architecture for Vision Transformers",
                "authors": "Alice Smith",
                "abstract": "A brand new paper.",
                "source_database": "openalex",
                "pdf_url": "https://openalex.org/pdf/W111222333.pdf"
            }
        ]

        comp_run_openalex = ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            scraper=self.scraper_openalex,
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

        # Total papers should now be 2 (1 from ArXiv + 1 novel from OpenAlex, duplicate skipped)
        self.assertEqual(Paper.objects.filter(workspace=self.workspace).count(), 2)

        comp_run_openalex.refresh_from_db()
        self.assertEqual(comp_run_openalex.metrics["total_fetched"], 2)
        self.assertEqual(comp_run_openalex.metrics["total_created"], 1)
        self.assertEqual(comp_run_openalex.metrics["ingested_new"], 1)
        self.assertEqual(comp_run_openalex.metrics["duplicates_count"], 1)
        self.assertEqual(comp_run_openalex.metrics["total_duplicates"], 1)
        self.assertEqual(comp_run_openalex.metrics["duplicates"], 1)
        self.assertEqual(comp_run_openalex.metrics["total_duplicates_skipped"], 1)
