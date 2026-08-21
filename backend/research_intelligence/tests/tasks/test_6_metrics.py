from django.test import TestCase
from unittest.mock import patch, MagicMock
from ...models import Workspace, PipelineRun, Paper, PaperMetric
from ...tasks.step_6_metrics.trl import assess_technology_readiness

class TRLAssessmentTaskTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Metrics Test Project",
            abstract_acceptance_criteria="Inclusion rules",
            abstract_rejection_criteria="Exclusion rules",
            llm_provider="google"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="test_hash_trl",
            title="Analysis of Vaccine Efficacy",
            authors="John Doe",
            abstract="Study on vaccine immunology and TRL 3 criteria proof of concept.",
            original_pdf_path="papers/vaccine.pdf",
            converted_md_path="papers/vaccine.md",
            source_database="arxiv"
        )

    @patch("django.core.files.storage.default_storage.exists")
    @patch("django.core.files.storage.default_storage.open")
    @patch("research_intelligence.tasks.step_6_metrics.trl.get_llm_provider")
    def test_trl_assessment_success_with_md(self, mock_get_llm_provider, mock_open, mock_exists):
        # 1. Setup mock storage to simulate converted markdown layout file
        mock_exists.return_value = True
        from unittest.mock import mock_open as django_mock_open
        mock_open.side_effect = django_mock_open(read_data=b"Mocked parsed paper markdown layout content with TRL 4 details.")

        # 2. Setup mock LLM provider returning structured JSON response matching response_schema
        mock_provider = MagicMock()
        mock_provider.generate.return_value = {
            "trl_score": 4,
            "trl_reasoning": "The research describes lab validation of efficacy.",
            "trl_evidence": ["TRL 4 details"]
        }
        mock_get_llm_provider.return_value = mock_provider

        # 3. Execute the Celery task
        result = assess_technology_readiness(self.paper.id)

        # 4. Assertions
        self.assertTrue(result)
        
        # Verify PaperMetric model instance is created in database
        metric = PaperMetric.objects.get(paper=self.paper)
        self.assertEqual(metric.metrics_data["trl_score"], 4)
        self.assertEqual(metric.metrics_data["trl_reasoning"], "The research describes lab validation of efficacy.")
        self.assertEqual(metric.metrics_data["trl_evidence"], ["TRL 4 details"])

        # Verify LLM provider was resolved and called
        mock_get_llm_provider.assert_called_once_with("google")
        mock_provider.generate.assert_called_once()

    @patch("django.core.files.storage.default_storage.exists")
    @patch("research_intelligence.tasks.step_6_metrics.trl.get_llm_provider")
    def test_trl_assessment_fallback_to_abstract(self, mock_get_llm_provider, mock_exists):
        # 1. Simulate that the converted markdown file does not exist in storage
        mock_exists.return_value = False

        # 2. Setup mock LLM provider
        mock_provider = MagicMock()
        mock_provider.generate.return_value = {
            "trl_score": 3,
            "trl_reasoning": "Abstract details a proof of concept.",
            "trl_evidence": ["TRL 3 criteria proof of concept"]
        }
        mock_get_llm_provider.return_value = mock_provider

        # 3. Execute the Celery task
        result = assess_technology_readiness(self.paper.id)

        # 4. Assertions
        self.assertTrue(result)
        
        metric = PaperMetric.objects.get(paper=self.paper)
        self.assertEqual(metric.metrics_data["trl_score"], 3)
        self.assertEqual(metric.metrics_data["trl_reasoning"], "Abstract details a proof of concept.")
        
        # Confirm provider prompt contained the abstract since md file was missing
        called_args, called_kwargs = mock_provider.generate.call_args
        prompt_arg = called_kwargs.get("prompt") or called_args[0] if called_args else called_kwargs.get("prompt", "")
        self.assertIn("TRL 3 criteria proof of concept", prompt_arg)

    @patch("django.core.files.storage.default_storage.exists")
    @patch("research_intelligence.tasks.step_6_metrics.trl.get_llm_provider")
    def test_trl_assessment_invalid_llm_response(self, mock_get_llm_provider, mock_exists):
        mock_exists.return_value = False

        # Simulate LLM returning missing score
        mock_provider = MagicMock()
        mock_provider.generate.return_value = {
            "trl_score": None,
            "trl_reasoning": "Failed to determine",
            "trl_evidence": []
        }
        mock_get_llm_provider.return_value = mock_provider

        result = assess_technology_readiness(self.paper.id)
        self.assertFalse(result)
        self.assertFalse(PaperMetric.objects.filter(paper=self.paper).exists())

    def test_trl_assessment_missing_paper(self):
        result = assess_technology_readiness("00000000-0000-0000-0000-000000000000")
        self.assertFalse(result)
