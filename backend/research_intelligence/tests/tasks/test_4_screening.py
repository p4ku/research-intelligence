from django.test import TestCase
from unittest.mock import patch, MagicMock
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from ...models import Workspace, PipelineRun, Paper, PaperMetric, Scraper, ComponentRun
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
            screening_llm_model="google/gemini-3.8-flash",
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
        metric = PaperMetric.objects.filter(paper=self.paper).order_by('-created_at').first()
        self.assertIsNotNone(metric)
        self.assertEqual(metric.screening_status, "abstract_passed")
        self.assertEqual(metric.abstract_screening_reasoning, "Contains agentic keywords.")

        # Ensure correct model and reasoning_effort parameters were passed
        mock_generate.assert_called_once()
        self.assertEqual(mock_generate.call_args.kwargs.get("model"), "google/gemini-3.8-flash")
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
        metric = PaperMetric.objects.filter(paper=self.paper).order_by('-created_at').first()
        self.assertIsNotNone(metric)
        self.assertEqual(metric.screening_status, "full_text_passed")
        self.assertEqual(metric.full_text_screening_reasoning, "Full text details reasoning workflows.")

        # Ensure correct model and reasoning_effort parameters were passed
        mock_generate.assert_called_once()
        self.assertEqual(mock_generate.call_args.kwargs.get("model"), "google/gemini-3.8-flash")
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
        metric_pass = PaperMetric.objects.filter(paper=self.paper).order_by('-created_at').first()
        self.assertEqual(metric_pass.screening_status, "abstract_passed")
        self.assertEqual(metric_pass.abstract_screening_reasoning, "Abstract satisfies inclusion criteria.")
        
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
        metric_rej = PaperMetric.objects.filter(paper=self.paper).order_by('-created_at').first()
        self.assertEqual(metric_rej.screening_status, "rejected")
        self.assertEqual(metric_rej.abstract_screening_reasoning, "Abstract matches rejection criteria (robotics hardware).")

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
        m_abs = PaperMetric.objects.filter(paper=self.paper).order_by('-created_at').first()
        self.assertEqual(m_abs.screening_status, "abstract_passed")
        self.assertEqual(m_abs.abstract_screening_reasoning, "Abstract passed initial screening.")

        # Stage 2: Full-Text Screening
        mock_generate.reset_mock()
        mock_generate.return_value = {
            "passed": True,
            "reasoning": "Full text confirms technical feasibility and agentic architecture.",
            "evidence_quotes": ["detailed benchmarks"]
        }
        ft_res = screen_full_text(self.paper.id, self.workspace.id)
        self.assertTrue(ft_res)
        m_ft = PaperMetric.objects.filter(paper=self.paper).order_by('-created_at').first()
        self.assertEqual(m_ft.screening_status, "full_text_passed")
        self.assertEqual(m_ft.abstract_screening_reasoning, "Abstract passed initial screening.")
        self.assertEqual(m_ft.full_text_screening_reasoning, "Full text confirms technical feasibility and agentic architecture.")

    @patch("django.core.files.storage.default_storage.open")
    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider.generate")
    def test_abstract_pass_but_full_text_reject(self, mock_generate, mock_open):
        """Test paper passing Abstract Screening but failing Full-Text Screening when full text reveals hardware focus."""
        from unittest.mock import mock_open as django_mock_open
        mock_open.side_effect = django_mock_open(read_data=b"Full text reveals hardware implementation on physical robotics.")

        # Stage 1: Abstract Screening passes
        mock_generate.return_value = {"passed": True, "reasoning": "Abstract sounds relevant."}
        screen_abstract(self.paper.id, self.workspace.id)
        m1 = PaperMetric.objects.filter(paper=self.paper).order_by('-created_at').first()
        self.assertEqual(m1.screening_status, "abstract_passed")
        self.assertEqual(m1.abstract_screening_reasoning, "Abstract sounds relevant.")

        # Stage 2: Full-Text Screening fails
        mock_generate.reset_mock()
        mock_generate.return_value = {
            "passed": False,
            "reasoning": "Full text analysis reveals physical robotics hardware constraint.",
            "evidence_quotes": ["physical robotics"]
        }
        screen_full_text(self.paper.id, self.workspace.id)
        m2 = PaperMetric.objects.filter(paper=self.paper).order_by('-created_at').first()
        self.assertEqual(m2.screening_status, "rejected")
        self.assertEqual(m2.abstract_screening_reasoning, "Abstract sounds relevant.")
        self.assertEqual(m2.full_text_screening_reasoning, "Full text analysis reveals physical robotics hardware constraint.")

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
        m_skip = PaperMetric.objects.filter(paper=self.paper).order_by('-created_at').first()
        self.assertEqual(m_skip.screening_status, "full_text_passed")

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
        from ...tasks.step_4_screening.node import AbstractScreeningNode, FullTextScreeningNode
        from ...models import ComponentRun, PaperMetric
        abs_node = AbstractScreeningNode()
        ft_node = FullTextScreeningNode()

        # Create paper 2 as withdrawn, paper 1 as rejected
        PaperMetric.objects.update_or_create(
            paper=self.paper,
            pipeline_run=self.pipeline_run,
            defaults={"workspace": self.workspace, "screening_status": "rejected"}
        )

        p2 = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_withdrawn",
            title="Withdrawn Study",
            authors="Bob",
            abstract="Withdrawn"
        )
        PaperMetric.objects.create(
            paper=p2,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="withdrawn"
        )

        # Before screening component run completes
        should_halt, msg = abs_node.should_halt_pipeline(self.pipeline_run, self.workspace, {})
        self.assertFalse(should_halt)

        # Abstract screening completed with 0 passed
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="abstract_screening",
            status="completed",
            metrics={"total_screened": 2, "passed": 0, "rejected": 2}
        )

        should_halt, msg = abs_node.should_halt_pipeline(self.pipeline_run, self.workspace, {})
        self.assertTrue(should_halt)
        self.assertIn("0 papers accepted", msg)

        # Full text screening completed with 0 passed
        ComponentRun.objects.create(
            pipeline_run=self.pipeline_run,
            step_type="screening",
            component_name="full_text_screening",
            status="completed",
            metrics={"total_screened": 2, "passed": 0, "rejected": 2}
        )
        should_halt_ft, msg_ft = ft_node.should_halt_pipeline(self.pipeline_run, self.workspace, {})
        self.assertTrue(should_halt_ft)
        self.assertIn("0 papers accepted", msg_ft)

        # If one paper passes, it should not halt
        PaperMetric.objects.filter(paper=p2, pipeline_run=self.pipeline_run).update(screening_status="accepted")
        should_halt, msg = abs_node.should_halt_pipeline(self.pipeline_run, self.workspace, {})
        self.assertFalse(should_halt)
        should_halt_ft, msg_ft = ft_node.should_halt_pipeline(self.pipeline_run, self.workspace, {})
        self.assertFalse(should_halt_ft)

    def test_direct_multimodal_pdf_screening_passed(self):
        pdf_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{self.paper.hash_id}/original.pdf"
        mock_pdf_binary = b"%PDF-1.7 Simulated PDF document binary stream for Gemini Multimodal"
        default_storage.save(pdf_path, ContentFile(mock_pdf_binary))
        self.paper.original_pdf_path = pdf_path
        self.paper.save(update_fields=['original_pdf_path'])

        mock_llm_response = {
            "passed": True,
            "reasoning": "Paper demonstrates 120 us T1 coherence time exceeding the 100 us acceptance threshold.",
            "evidence_quotes": [
                "measured relaxation time T1 = 120.4 +/- 3.2 us across 10 sample runs"
            ],
            "decision_category": "ACCEPTED: Coherence criterion met"
        }
        mock_usage = {"prompt_tokens": 4500, "candidates_tokens": 120, "total_tokens": 4620}

        with patch("research_intelligence.tasks.step_4_screening.full_text.get_llm_provider") as mock_provider_factory:
            mock_provider = MagicMock()
            mock_provider.generate.return_value = (mock_llm_response, mock_usage)
            mock_provider_factory.return_value = mock_provider

            result = screen_full_text(
                str(self.paper.id),
                str(self.workspace.id),
                workspace_obj=self.workspace,
                paper_obj=self.paper
            )

            self.assertTrue(result["success"])
            self.assertTrue(result["passed"])
            self.assertEqual(result["input_source"], "multimodal_pdf")
            self.assertEqual(result["screening_status"], "full_text_passed")
            self.assertEqual(len(result["evidence_quotes"]), 1)

            call_kwargs = mock_provider.generate.call_args[1]
            self.assertEqual(call_kwargs.get("mime_type"), "application/pdf")
            self.assertEqual(call_kwargs.get("pdf_bytes"), mock_pdf_binary)

    def test_direct_multimodal_pdf_screening_rejected(self):
        pdf_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{self.paper.hash_id}/original.pdf"
        mock_pdf_binary = b"%PDF-1.7 Simulated PDF document binary stream for Gemini Multimodal"
        default_storage.save(pdf_path, ContentFile(mock_pdf_binary))
        self.paper.original_pdf_path = pdf_path
        self.paper.save(update_fields=['original_pdf_path'])

        mock_llm_response = {
            "passed": False,
            "reasoning": "Study is purely numerical simulation without experimental device measurements.",
            "evidence_quotes": [
                "We perform numerical master equation simulations of idealized transmons"
            ],
            "decision_category": "REJECTED: Purely theoretical simulation"
        }
        mock_usage = {"prompt_tokens": 3800, "candidates_tokens": 90, "total_tokens": 3890}

        with patch("research_intelligence.tasks.step_4_screening.full_text.get_llm_provider") as mock_provider_factory:
            mock_provider = MagicMock()
            mock_provider.generate.return_value = (mock_llm_response, mock_usage)
            mock_provider_factory.return_value = mock_provider

            result = screen_full_text(
                str(self.paper.id),
                str(self.workspace.id),
                workspace_obj=self.workspace,
                paper_obj=self.paper
            )

            self.assertTrue(result["success"])
            self.assertFalse(result["passed"])
            self.assertEqual(result["screening_status"], "rejected")

    def test_fallback_to_abstract_when_pdf_missing(self):
        paper_no_pdf = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_no_pdf_002",
            title="Abstract Only Quantum Study",
            abstract="Short abstract about quantum gates.",
            original_pdf_path=None
        )
        PaperMetric.objects.create(
            paper=paper_no_pdf,
            pipeline_run=self.pipeline_run,
            workspace=self.workspace,
            screening_status="pending"
        )

        mock_llm_response = {
            "passed": True,
            "reasoning": "Passed on abstract evaluation fallback.",
            "evidence_quotes": ["quantum gates"],
            "decision_category": "ACCEPTED: Abstract fallback"
        }
        mock_usage = {"prompt_tokens": 350, "candidates_tokens": 40, "total_tokens": 390}

        with patch("research_intelligence.tasks.step_4_screening.full_text.get_llm_provider") as mock_provider_factory:
            mock_provider = MagicMock()
            mock_provider.generate.return_value = (mock_llm_response, mock_usage)
            mock_provider_factory.return_value = mock_provider

            result = screen_full_text(
                str(paper_no_pdf.id),
                str(self.workspace.id),
                workspace_obj=self.workspace,
                paper_obj=paper_no_pdf
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["input_source"], "abstract_fallback")

    def test_multimodal_pdf_screening_with_custom_dynamic_schema_and_exit_metric(self):
        custom_schema = {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "fidelity_score": {"type": "number"},
                "reasoning": {"type": "string"}
            },
            "required": ["passed", "fidelity_score"]
        }
        self.workspace.full_text_screening_system_prompt = "Custom Multimodal Quantum Screener System Prompt"
        self.workspace.full_text_screening_user_prompt_template = "Analyze PDF: {full_text} for criteria: {acceptance_criteria}"
        self.workspace.full_text_screening_response_schema = custom_schema
        self.workspace.full_text_screening_exit_metric = "fidelity_score"
        self.workspace.save()

        pdf_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{self.paper.hash_id}/original.pdf"
        mock_pdf_binary = b"%PDF-1.7 Simulated PDF document binary stream for Gemini Multimodal"
        default_storage.save(pdf_path, ContentFile(mock_pdf_binary))
        self.paper.original_pdf_path = pdf_path
        self.paper.save(update_fields=['original_pdf_path'])

        mock_llm_response = {
            "passed": True,
            "fidelity_score": 99.8,
            "reasoning": "High fidelity state preparation achieved in 3D cavity.",
            "decision_category": "ACCEPTED: High Fidelity"
        }
        mock_usage = {"prompt_tokens": 5200, "candidates_tokens": 80, "total_tokens": 5280}

        with patch("research_intelligence.tasks.step_4_screening.full_text.get_llm_provider") as mock_provider_factory:
            mock_provider = MagicMock()
            mock_provider.generate.return_value = (mock_llm_response, mock_usage)
            mock_provider_factory.return_value = mock_provider

            result = screen_full_text(
                str(self.paper.id),
                str(self.workspace.id),
                workspace_obj=self.workspace,
                paper_obj=self.paper
            )

            self.assertTrue(result["success"])
            self.assertTrue(result["passed"])
            self.assertEqual(result["exit_metric_key"], "fidelity_score")
            self.assertEqual(result["exit_metric_value"], 99.8)

            call_kwargs = mock_provider.generate.call_args[1]
            self.assertEqual(call_kwargs.get("system_instruction"), "Custom Multimodal Quantum Screener System Prompt")
            self.assertEqual(call_kwargs.get("response_schema"), custom_schema)
            self.assertEqual(call_kwargs.get("pdf_bytes"), mock_pdf_binary)
            self.assertEqual(call_kwargs.get("mime_type"), "application/pdf")

            pm = PaperMetric.objects.get(paper=self.paper, pipeline_run=self.pipeline_run)
            self.assertIn("full_text_screening", pm.metrics_data)
            self.assertEqual(pm.metrics_data["full_text_screening"]["exit_metric_value"], 99.8)
            self.assertEqual(pm.metrics_data["full_text_screening"]["dynamic_data"]["fidelity_score"], 99.8)

    def test_screen_abstract_with_json_in_prompt_template_succeeds(self):
        self.workspace.abstract_screening_user_prompt_template = (
            "Review paper: {title}\n"
            "Schema: {\"format\": \"json\", \"accepted\": true}\n"
            "Criteria: {acceptance_criteria}\n"
            "LaTeX Math: \\mathcal{O}(n)"
        )
        self.workspace.abstract_acceptance_criteria = "Study on LLM agents"
        self.workspace.save()

        run = PipelineRun.objects.create(workspace=self.workspace, status='running')
        paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=run,
            hash_id="p_test_json_template",
            title="Agentic Coding Workflows",
            authors="DeepMind",
            abstract="Study on autonomous programming agents."
        )

        mock_llm_response = {
            "decision": "PASSED",
            "passed": True,
            "reasoning": "Fits criteria well",
            "evidence_quotes": ["autonomous programming agents"]
        }

        with patch('research_intelligence.tasks.step_4_screening.abstract.get_llm_provider') as mock_get_provider:
            mock_prov = MagicMock()
            mock_prov.generate.return_value = (mock_llm_response, {"tokens_in": 50, "tokens_out": 20, "total_tokens": 70})
            mock_get_provider.return_value = mock_prov

            res = screen_abstract(
                str(paper.id),
                str(self.workspace.id),
                workspace_obj=self.workspace,
                paper_obj=paper,
                pipeline_run_id=str(run.id)
            )

            self.assertTrue(res.get("success"))
            self.assertTrue(res.get("passed"))

            call_kwargs = mock_prov.generate.call_args[1]
            prompt_sent = call_kwargs["prompt"]
            self.assertIn("Review paper: Agentic Coding Workflows", prompt_sent)
            self.assertIn("Criteria: Study on LLM agents", prompt_sent)
            self.assertIn("Schema: {\"format\": \"json\", \"accepted\": true}", prompt_sent)
            self.assertIn("\\mathcal{O}(n)", prompt_sent)

            pm = PaperMetric.objects.filter(paper=paper, pipeline_run=run).first()
            self.assertIsNotNone(pm)
            self.assertTrue(pm.metrics_data["abstract_screening"]["passed"])
            self.assertEqual(pm.metrics_data["abstract_screening"]["reasoning"], "Fits criteria well")
