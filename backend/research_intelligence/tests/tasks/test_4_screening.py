from django.test import TestCase
from unittest.mock import patch
from ...models import Workspace, PipelineRun, Paper, Scraper
from ...tasks.step_4_screening.abstract import screen_abstract
from ...tasks.step_4_screening.full_text import screen_full_text

class ScreeningTasksTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="AI Screening Project",
            acceptance_criteria="Focus on agentic workflows and reasoning loops.",
            rejection_criteria="Exclude studies focused strictly on physical robotics hardware.",
            screening_llm_model="google/gemini-1.5-flash",
            llm_provider="google"
        )
        self.scraper_arxiv = Scraper.objects.create(
            workspace=self.workspace,
            provider="arxiv",
            search_query="all:\"agentic AI\""
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="test_hash_screening",
            title="Reasoning loop architectures",
            authors="Alice Smith",
            abstract="We present a framework for agentic workflows.",
            converted_md_path="papers/test_hash_screening.md",
            source_database="arxiv"
        )

    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_screen_abstract_success(self, mock_generate):
        mock_generate.return_value = {
            "passed": True,
            "reasoning": "Contains agentic keywords."
        }

        result = screen_abstract(self.paper.id, self.workspace.id)

        self.assertTrue(result)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.screening_status, "abstract_passed")
        self.assertEqual(self.paper.screening_reasoning, "Contains agentic keywords.")

        # Ensure correct model parameter was passed
        mock_generate.assert_called_once()
        self.assertEqual(mock_generate.call_args.kwargs.get("model"), "google/gemini-1.5-flash")

    @patch("django.core.files.storage.default_storage.open")
    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_screen_full_text_success(self, mock_generate, mock_open):
        from unittest.mock import mock_open as django_mock_open
        mock_open.side_effect = django_mock_open(read_data=b"Full scientific text showing reasoning loops.")
        mock_generate.return_value = {
            "passed": True,
            "reasoning": "Full text details reasoning workflows."
        }

        result = screen_full_text(self.paper.id, self.workspace.id)

        self.assertTrue(result)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.screening_status, "full_text_passed")
        self.assertEqual(self.paper.screening_reasoning, "Full text details reasoning workflows.")

        # Ensure correct model parameter was passed
        mock_generate.assert_called_once()
        self.assertEqual(mock_generate.call_args.kwargs.get("model"), "google/gemini-1.5-flash")
