from django.test import TestCase
from unittest.mock import patch
from ...models import Workspace, PipelineRun, Paper, Scraper
from ...tasks.step_4_screening.abstract import screen_abstract
from ...tasks.step_4_screening.full_text import screen_full_text

class ScreeningTasksTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="AI Screening Project",
            abstract_acceptance_criteria="Focus on agentic workflows and reasoning loops.",
            abstract_rejection_criteria="Exclude studies focused strictly on physical robotics hardware.",
            full_text_acceptance_criteria="Focus on agentic workflows and reasoning loops.",
            full_text_rejection_criteria="Exclude studies focused strictly on physical robotics hardware.",
            screening_llm_model="google/gemini-3.7-flash",
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

        # Ensure correct model and reasoning_effort parameters were passed
        mock_generate.assert_called_once()
        self.assertEqual(mock_generate.call_args.kwargs.get("model"), "google/gemini-3.7-flash")
        self.assertEqual(mock_generate.call_args.kwargs.get("reasoning_effort"), "medium")

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

        # Ensure correct model and reasoning_effort parameters were passed
        mock_generate.assert_called_once()
        self.assertEqual(mock_generate.call_args.kwargs.get("model"), "google/gemini-3.7-flash")
        self.assertEqual(mock_generate.call_args.kwargs.get("reasoning_effort"), "medium")

    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_screen_abstract_with_custom_reasoning_effort(self, mock_generate):
        mock_generate.return_value = {"passed": True, "reasoning": "Deep reasoning applied."}
        self.workspace.reasoning_effort = "high"
        self.workspace.save()

        screen_abstract(self.paper.id, self.workspace.id)
        self.assertEqual(mock_generate.call_args.kwargs.get("reasoning_effort"), "high")

    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_only_abstract_screening_pass_and_reject(self, mock_generate):
        """Test Abstract-Only screening for both passing and failing criteria."""
        # 1. Test Passing Paper
        mock_generate.return_value = {
            "passed": True,
            "reasoning": "Abstract satisfies inclusion criteria.",
            "evidence_quotes": ["agentic workflows"],
            "decision_category": "ACCEPTED: Scope match"
        }
        res_pass = screen_abstract(self.paper.id, self.workspace.id)
        self.assertTrue(res_pass)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.screening_status, "abstract_passed")
        self.assertEqual(self.paper.screening_reasoning, "Abstract satisfies inclusion criteria.")
        
        # Verify prompt contained abstract_acceptance_criteria
        prompt_text = mock_generate.call_args.kwargs.get("prompt", "")
        self.assertIn("Focus on agentic workflows and reasoning loops.", prompt_text)

        # 2. Test Rejecting Paper
        mock_generate.reset_mock()
        mock_generate.return_value = {
            "passed": False,
            "reasoning": "Abstract matches rejection criteria (robotics hardware).",
            "evidence_quotes": ["physical robotics"],
            "decision_category": "REJECTED: Excluded hardware"
        }
        res_reject = screen_abstract(self.paper.id, self.workspace.id)
        self.assertTrue(res_reject)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.screening_status, "rejected")
        self.assertEqual(self.paper.screening_reasoning, "Abstract matches rejection criteria (robotics hardware).")

    @patch("django.core.files.storage.default_storage.open")
    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_abstract_and_full_text_screening_combined_pipeline(self, mock_generate, mock_open):
        """Test 2-Stage Sequential Screening: Abstract Screening followed by Full-Text Screening."""
        from unittest.mock import mock_open as django_mock_open
        mock_open.side_effect = django_mock_open(read_data=b"Full paper content with detailed benchmarks.")

        # Stage 1: Abstract Screening
        mock_generate.return_value = {
            "passed": True,
            "reasoning": "Abstract passed initial screening.",
            "evidence_quotes": ["reasoning loop architectures"]
        }
        abs_res = screen_abstract(self.paper.id, self.workspace.id)
        self.assertTrue(abs_res)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.screening_status, "abstract_passed")

        # Stage 2: Full-Text Screening
        mock_generate.reset_mock()
        mock_generate.return_value = {
            "passed": True,
            "reasoning": "Full text confirms technical feasibility and agentic architecture.",
            "evidence_quotes": ["detailed benchmarks"]
        }
        ft_res = screen_full_text(self.paper.id, self.workspace.id)
        self.assertTrue(ft_res)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.screening_status, "full_text_passed")
        self.assertEqual(self.paper.screening_reasoning, "Full text confirms technical feasibility and agentic architecture.")

    @patch("django.core.files.storage.default_storage.open")
    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_abstract_pass_but_full_text_reject(self, mock_generate, mock_open):
        """Test paper passing Abstract Screening but failing Full-Text Screening when full text reveals hardware focus."""
        from unittest.mock import mock_open as django_mock_open
        mock_open.side_effect = django_mock_open(read_data=b"Full text reveals hardware implementation on physical robotics.")

        # Stage 1: Abstract Screening passes
        mock_generate.return_value = {"passed": True, "reasoning": "Abstract sounds relevant."}
        screen_abstract(self.paper.id, self.workspace.id)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.screening_status, "abstract_passed")

        # Stage 2: Full-Text Screening fails
        mock_generate.reset_mock()
        mock_generate.return_value = {
            "passed": False,
            "reasoning": "Full text analysis reveals physical robotics hardware constraint.",
            "evidence_quotes": ["physical robotics"]
        }
        screen_full_text(self.paper.id, self.workspace.id)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.screening_status, "rejected")
        self.assertEqual(self.paper.screening_reasoning, "Full text analysis reveals physical robotics hardware constraint.")

    @patch("django.core.files.storage.default_storage.open")
    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_skip_abstract_screening_mode(self, mock_generate, mock_open):
        """Test workspace skip_abstract_screening=True setting performing direct full-text screening."""
        from unittest.mock import mock_open as django_mock_open
        mock_open.side_effect = django_mock_open(read_data=b"Direct full text content.")

        self.workspace.skip_abstract_screening = True
        self.workspace.save()

        mock_generate.return_value = {
            "passed": True,
            "reasoning": "Direct full-text evaluation passed."
        }

        # Direct Full-Text Screening without abstract step
        result = screen_full_text(self.paper.id, self.workspace.id)
        self.assertTrue(result)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.screening_status, "full_text_passed")

    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_dynamic_abstract_screening_custom_prompt_and_schema(self, mock_generate):
        """Test custom system prompt, prompt template, response schema, and exit metric in abstract screening."""
        self.workspace.abstract_screening_system_prompt = "Custom Abstract Scanner System Prompt."
        self.workspace.abstract_screening_user_prompt_template = "PAPER_TITLE: {title} | CRITERIA: {acceptance_criteria}"
        self.workspace.abstract_screening_response_schema = {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "relevance_score": {"type": "number"},
                "reasoning": {"type": "string"}
            },
            "required": ["passed", "relevance_score"]
        }
        self.workspace.abstract_screening_exit_metric = "relevance_score"
        self.workspace.save()

        mock_generate.return_value = {
            "passed": True,
            "relevance_score": 9.5,
            "reasoning": "Highly relevant custom output.",
            "decision_category": "ACCEPTED: High Score"
        }

        res = screen_abstract(self.paper.id, self.workspace.id)
        self.assertTrue(res["success"])
        self.assertTrue(res["passed"])
        self.assertEqual(res["exit_metric_key"], "relevance_score")
        self.assertEqual(res["exit_metric_value"], 9.5)
        self.assertEqual(res["dynamic_data"]["relevance_score"], 9.5)

        # Check prompt args passed to LLM provider
        call_kwargs = mock_generate.call_args.kwargs
        self.assertEqual(call_kwargs.get("system_instruction"), "Custom Abstract Scanner System Prompt.")
        self.assertIn("PAPER_TITLE: Reasoning loop architectures", call_kwargs.get("prompt", ""))
        self.assertEqual(call_kwargs.get("response_schema"), self.workspace.abstract_screening_response_schema)

        # Check PaperMetric storage
        from ...models import PaperMetric
        pm = PaperMetric.objects.get(paper=self.paper, pipeline_run=self.pipeline_run)
        self.assertIn("abstract_screening", pm.metrics_data)
        self.assertEqual(pm.metrics_data["abstract_screening"]["exit_metric_value"], 9.5)

    @patch("django.core.files.storage.default_storage.exists", return_value=True)
    @patch("django.core.files.storage.default_storage.open")
    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_dynamic_full_text_screening_custom_prompt_and_schema(self, mock_generate, mock_open, mock_exists):
        """Test custom system prompt, prompt template, response schema, and exit metric in full-text screening."""
        from unittest.mock import mock_open as django_mock_open
        mock_open.side_effect = django_mock_open(read_data=b"Detailed quantum algorithm paper.")

        self.workspace.full_text_screening_system_prompt = "Custom Full-Text Screener System Prompt."
        self.workspace.full_text_screening_user_prompt_template = "FULL_DOC: {full_text} | REJECT_IF: {rejection_criteria}"
        self.workspace.full_text_screening_response_schema = {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "fit_score": {"type": "number"},
                "reasoning": {"type": "string"}
            },
            "required": ["passed", "fit_score"]
        }
        self.workspace.full_text_screening_exit_metric = "fit_score"
        self.workspace.save()

        mock_generate.return_value = {
            "passed": True,
            "fit_score": 8.8,
            "reasoning": "Fits full-text criteria accurately.",
            "decision_category": "ACCEPTED: Full-text"
        }

        res = screen_full_text(self.paper.id, self.workspace.id)
        self.assertTrue(res["success"])
        self.assertTrue(res["passed"])
        self.assertEqual(res["exit_metric_key"], "fit_score")
        self.assertEqual(res["exit_metric_value"], 8.8)

        call_kwargs = mock_generate.call_args.kwargs
        self.assertEqual(call_kwargs.get("system_instruction"), "Custom Full-Text Screener System Prompt.")
        self.assertIn("FULL_DOC: Detailed quantum algorithm paper.", call_kwargs.get("prompt", ""))
        self.assertEqual(call_kwargs.get("response_schema"), self.workspace.full_text_screening_response_schema)

        # Check PaperMetric storage
        from ...models import PaperMetric
        pm = PaperMetric.objects.get(paper=self.paper, pipeline_run=self.pipeline_run)
        self.assertIn("full_text_screening", pm.metrics_data)
        self.assertEqual(pm.metrics_data["full_text_screening"]["exit_metric_value"], 8.8)

    def test_screening_node_should_halt_pipeline(self):
        """Test ScreeningNode halts cleanly when 0 papers are accepted (even with withdrawn/rejected mix)."""
        from ...tasks.step_4_screening.node import ScreeningNode
        from ...models import ComponentRun
        node = ScreeningNode()

        # Create paper 2 as withdrawn, paper 1 as rejected
        self.paper.screening_status = "rejected"
        self.paper.save()

        p2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_withdrawn",
            title="Withdrawn Study",
            authors="Bob",
            abstract="Withdrawn",
            screening_status="withdrawn"
        )

        # Before screening component run completes
        should_halt, msg = node.should_halt_pipeline(self.pipeline_run, self.workspace, {})
        self.assertFalse(should_halt)

        # Abstract screening completed with 0 passed
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="abstract_screening",
            status="completed",
            metrics={"total_screened": 2, "passed": 0, "rejected": 1, "withdrawn": 1}
        )

        should_halt, msg = node.should_halt_pipeline(self.pipeline_run, self.workspace, {"skip_full_text_screening": True})
        self.assertTrue(should_halt)
        self.assertIn("0 papers accepted", msg)

        # If one paper passes, it should not halt
        p2.screening_status = "accepted"
        p2.save()
        should_halt, msg = node.should_halt_pipeline(self.pipeline_run, self.workspace, {"skip_full_text_screening": True})
        self.assertFalse(should_halt)


