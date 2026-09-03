import io
import unittest
from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from pypdf import PdfWriter

from research_intelligence.models import Workspace, PipelineRun, Paper, PaperMetric
from research_intelligence.utils.pdf_extractor import extract_text_from_pdf_bytes
from research_intelligence.llm_providers.google import GoogleAgentAPIProvider
from research_intelligence.tasks.step_4_screening.full_text import screen_full_text


def create_minimal_pdf_bytes(text_content: str = "Quantum Optical Computing Analysis") -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    # Note: blank page gives minimal valid PDF structure
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class PDFFallbackAndConnectionPoolTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.workspace = Workspace.objects.create(
            name="Optical Computing Workspace",
            screening_llm_model="gemini-3.8-flash",
            llm_provider="google"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running",
            current_stage="screening"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="optical_paper_01",
            title="What should a linear optical frontend compute?",
            authors="Test Author",
            abstract="Optical frontends provide quadratic feature extraction via intensity detection.",
            source_database="arxiv"
        )

    def test_extract_text_from_pdf_bytes_empty_or_invalid(self):
        self.assertEqual(extract_text_from_pdf_bytes(None), "")
        self.assertEqual(extract_text_from_pdf_bytes(b"not a pdf"), "")

    def test_extract_text_from_valid_pdf_bytes(self):
        pdf_bytes = create_minimal_pdf_bytes()
        res = extract_text_from_pdf_bytes(pdf_bytes)
        self.assertIsInstance(res, str)

    @patch("research_intelligence.llm_providers.google.GoogleAgentAPIProvider._get_client")
    def test_google_llm_auto_falls_back_on_400_invalid_argument(self, mock_get_client):
        """
        Validates that when Google GenAI raises 400 INVALID_ARGUMENT on binary Part.from_bytes,
        GoogleAgentAPIProvider automatically extracts text from the PDF and retries with plain text prompt.
        """
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        pdf_bytes = create_minimal_pdf_bytes()

        # First call fails with 400 INVALID_ARGUMENT (binary payload rejected)
        # Second call (after text fallback) succeeds with mock response
        mock_response = MagicMock()
        mock_response.text = '{"passed": true, "reasoning": "Optical computation valid."}'
        mock_response.candidates = [
            MagicMock(content=MagicMock(parts=[MagicMock(text='{"passed": true, "reasoning": "Optical computation valid."}', thought=False)]))
        ]

        from google.genai.errors import ClientError
        mock_client.models.generate_content.side_effect = [
            ClientError(400, {"error": {"code": 400, "message": "Request contains an invalid argument."}}, None),
            mock_response
        ]

        provider = GoogleAgentAPIProvider(api_key="test_key")
        res = provider.generate(
            prompt="Analyze this paper",
            pdf_bytes=pdf_bytes,
            mime_type="application/pdf",
            model="gemini-3.8-flash"
        )

        self.assertIn("Optical computation valid", res)
        self.assertEqual(mock_client.models.generate_content.call_count, 2)

    @patch("research_intelligence.tasks.step_4_screening.full_text.get_llm_provider")
    def test_screen_full_text_recovers_from_gemini_400(self, mock_get_provider):
        """
        Validates that screen_full_text intercepts 400 INVALID_ARGUMENT from Gemini multimodal PDF,
        falls back to text/abstract without failing, and records successful PaperMetric.
        """
        pdf_bytes = create_minimal_pdf_bytes()
        pdf_path = f"workspaces/{self.workspace.id}/runs/{self.pipeline_run.id}/documents/test.pdf"
        default_storage.save(pdf_path, ContentFile(pdf_bytes))
        self.paper.original_pdf_path = pdf_path
        self.paper.save(update_fields=['original_pdf_path'])

        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider

        # First call raises 400 INVALID_ARGUMENT
        # Second call returns valid JSON screening decision
        mock_provider.generate.side_effect = [
            Exception("400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'Request contains an invalid argument.'}}"),
            ({"passed": True, "reasoning": "Passed on fallback text.", "evidence_quotes": []}, {"prompt_tokens": 100, "candidates_tokens": 50})
        ]

        res = screen_full_text(
            paper_id=str(self.paper.id),
            workspace_id=str(self.workspace.id),
            pipeline_run_id=str(self.pipeline_run.id),
            paper_obj=self.paper,
            workspace_obj=self.workspace
        )

        self.assertTrue(res["success"])
        self.assertTrue(res["passed"])
        self.assertEqual(res["screening_status"], "full_text_passed")
        self.assertIn("Passed on fallback text", res["reasoning"])

        pm = PaperMetric.objects.get(paper=self.paper, pipeline_run_id=self.pipeline_run.id)
        self.assertEqual(pm.screening_status, "full_text_passed")
