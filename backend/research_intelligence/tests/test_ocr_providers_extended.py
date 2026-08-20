from unittest.mock import patch, MagicMock
from django.test import TestCase

from research_intelligence.ocr_providers.factory import get_ocr_provider
from research_intelligence.ocr_providers.gemini_provider import GeminiOCRProvider
from research_intelligence.ocr_providers.mistral_provider import MistralOCRProvider
from research_intelligence.ocr_providers.pypdf_provider import PyPDFOCRProvider


class OCRProvidersExtendedTestCase(TestCase):
    """
    Validates OCR Provider factory resolution, formatting normalization, and resilient error recovery.
    """

    def test_ocr_provider_factory_resolution(self):
        self.assertIsInstance(get_ocr_provider("pypdf"), PyPDFOCRProvider)
        self.assertIsInstance(get_ocr_provider("gemini"), GeminiOCRProvider)
        self.assertIsInstance(get_ocr_provider("mistral"), MistralOCRProvider)

        with self.assertRaises(ValueError):
            get_ocr_provider("non_existent_ocr")

    @patch("research_intelligence.ocr_providers.gemini_provider.PdfReader")
    def test_gemini_ocr_provider_markdown_formatting_and_code_fence_cleaning(self, mock_reader):
        mock_reader.return_value.pages = []
        provider = GeminiOCRProvider(model_name="google/gemini-3.7-flash")

        mock_llm = MagicMock()
        mock_llm.generate.return_value = "```markdown\n## Introduction\nThis is paper body.\n```"
        provider.provider = mock_llm

        output = provider.convert("/tmp/mock.pdf", title="Quantum Paper", output_format="markdown")
        self.assertIn("## Introduction", output)
        self.assertIn("This is paper body.", output)
        self.assertNotIn("```markdown", output)

    @patch("research_intelligence.ocr_providers.gemini_provider.PdfReader")
    def test_gemini_ocr_provider_html_formatting(self, mock_reader):
        mock_reader.return_value.pages = []
        provider = GeminiOCRProvider(model_name="google/gemini-3.7-flash")

        mock_llm = MagicMock()
        mock_llm.generate.return_value = "<p>Semantic HTML body.</p>"
        provider.provider = mock_llm

        output = provider.convert("/tmp/mock.pdf", title="HTML Paper", output_format="html")
        self.assertIn("<h1>HTML Paper</h1>", output)
        self.assertIn("<p>Semantic HTML body.</p>", output)

    @patch("research_intelligence.ocr_providers.gemini_provider.PdfReader")
    def test_gemini_ocr_provider_fallback_on_exception(self, mock_reader):
        mock_reader.return_value.pages = []
        provider = GeminiOCRProvider(model_name="google/gemini-3.7-flash")

        mock_llm = MagicMock()
        mock_llm.generate.side_effect = RuntimeError("Gemini Vision 503 Overloaded")
        provider.provider = mock_llm

        output = provider.convert("/tmp/mock.pdf", title="Failed Paper", output_format="markdown")
        self.assertIn("# Failed Paper", output)
        self.assertIn("fallback", output.lower())

    def test_mistral_ocr_provider_conversion(self):
        provider = MistralOCRProvider()
        output_md = provider.convert("/tmp/mock.pdf", title="Mistral Paper", output_format="markdown")
        self.assertIn("# Mistral Paper", output_md)
        self.assertIn("Mistral OCR layout extraction stub", output_md)

        output_html = provider.convert("/tmp/mock.pdf", title="Mistral Paper", output_format="html")
        self.assertIn("<h1>Mistral Paper</h1>", output_html)
