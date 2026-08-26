import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from research_intelligence.models import Workspace, PipelineRun, ComponentRun, Paper
from research_intelligence.tasks.step_4_screening.full_text import screen_full_text, execute_full_text_screening_job

User = get_user_model()


class MultimodalPDFScreeningTestCase(TestCase):
    """
    Tests direct multimodal PDF binary screening:
    1. When ocr_provider is None (default), the full original.pdf binary is passed directly to Gemini.
    2. Acceptance and rejection criteria evaluation with evidence quotes extraction.
    3. Fallback to paper abstract when raw PDF binary is unavailable.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="multimodal_analyst", email="analyst@example.com", password="password123")
        self.workspace = Workspace.objects.create(
            name="Quantum Computing Review",
            ocr_provider=None,  # Direct multimodal PDF mode
            llm_provider="google",
            screening_llm_model="google/gemini-3.7-flash",
            full_text_acceptance_criteria="Accept experimental superconducting qubit coherence measurements > 100 microseconds.",
            full_text_rejection_criteria="Reject purely theoretical or non-superconducting architectures."
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            triggered_by=self.user,
            status="running"
        )

        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_quantum_001",
            title="Coherence Time Extension in 3D Cavity Superconducting Qubits",
            abstract="We report 120 us T1 coherence times in 3D transmon qubits.",
            screening_status="pending"
        )

        # Store simulated PDF binary in default_storage
        self.pdf_storage_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/{self.paper.hash_id}/original.pdf"
        self.mock_pdf_binary = b"%PDF-1.7 Simulated PDF document binary stream for Gemini Multimodal"
        default_storage.save(self.pdf_storage_path, ContentFile(self.mock_pdf_binary))

        self.paper.original_pdf_path = self.pdf_storage_path
        self.paper.save(update_fields=['original_pdf_path'])

    def test_direct_multimodal_pdf_screening_passed(self):
        """
        Validates that screen_full_text passes raw PDF bytes and mime_type to Gemini provider.
        """
        mock_llm_response = {
            "passed": True,
            "reasoning": "Paper demonstrates 120 us T1 coherence time exceeding the 100 us acceptance threshold.",
            "evidence_quotes": [
                "measured relaxation time T1 = 120.4 +/- 3.2 us across 10 sample runs",
                "3D aluminum cavity architecture suppressed dielectric surface losses"
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
            self.assertEqual(len(result["evidence_quotes"]), 2)

            # Check that generate was called with pdf_bytes and mime_type="application/pdf"
            call_kwargs = mock_provider.generate.call_args[1]
            self.assertEqual(call_kwargs.get("mime_type"), "application/pdf")
            self.assertEqual(call_kwargs.get("pdf_bytes"), self.mock_pdf_binary)

    def test_direct_multimodal_pdf_screening_rejected(self):
        """
        Validates full-text rejection when methodology fails criteria.
        """
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
        """
        Ensures that if PDF binary is absent from storage, screen_full_text falls back to abstract.
        """
        paper_no_pdf = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="paper_no_pdf_002",
            title="Abstract Only Quantum Study",
            abstract="Short abstract about quantum gates.",
            original_pdf_path=None,
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
        """
        Validates that multimodal PDF screening utilizes workspace custom prompts, response schema,
        and exit metric, saving dynamic results into PaperMetric.
        """
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
            self.assertEqual(call_kwargs.get("pdf_bytes"), self.mock_pdf_binary)
            self.assertEqual(call_kwargs.get("mime_type"), "application/pdf")

            # Check PaperMetric
            from research_intelligence.models import PaperMetric
            pm = PaperMetric.objects.get(paper=self.paper, pipeline_run=self.pipeline_run)
            self.assertIn("full_text_screening", pm.metrics_data)
            self.assertEqual(pm.metrics_data["full_text_screening"]["exit_metric_value"], 99.8)
            self.assertEqual(pm.metrics_data["full_text_screening"]["dynamic_data"]["fidelity_score"], 99.8)

