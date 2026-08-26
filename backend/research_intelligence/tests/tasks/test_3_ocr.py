from django.test import TestCase
from unittest.mock import patch, MagicMock
from ...models import Workspace, PipelineRun, Paper
from ...tasks.step_3_ocr.convert import run_ocr_conversion

class OCRConversionTaskTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="OCR Test Project",
            abstract_acceptance_criteria="Accept active learning.",
            abstract_rejection_criteria="Reject rule-based systems.",
            ocr_provider="pypdf"
        )
        self.pipeline_run = PipelineRun.objects.create(
            workspace=self.workspace,
            status="running"
        )
        self.paper = Paper.objects.create(
            workspace=self.workspace,
            pipeline_run=self.pipeline_run,
            hash_id="test_hash_ocr",
            title="A great OCR target paper",
            authors="Alice Cooper",
            abstract="Some abstract text.",
            original_pdf_path="papers/12345.pdf",
            source_database="arxiv"
        )

    @patch("django.core.files.storage.default_storage.save")
    @patch("django.core.files.storage.default_storage.open")
    @patch("research_intelligence.tasks.step_3_ocr.convert.get_ocr_provider")
    def test_run_ocr_conversion_success_markdown(self, mock_get_provider, mock_open, mock_save):
        from unittest.mock import mock_open as django_mock_open
        mock_open.side_effect = django_mock_open(read_data=b"%PDF-1.4 mock bytes")
        mock_save.side_effect = lambda path, content: path
        
        # Setup mock OCR provider
        mock_provider = MagicMock()
        mock_provider.convert.return_value = "# A great OCR target paper\n\nMocked layout text."
        mock_get_provider.return_value = mock_provider
        
        result = run_ocr_conversion(self.paper.id, output_format="markdown")
        
        self.assertTrue(result)
        
        self.paper.refresh_from_db()
        self.assertIsNotNone(self.paper.converted_md_path)
        self.assertTrue(self.paper.converted_md_path.endswith("ocr.md"))
        
        # Assert provider called
        mock_get_provider.assert_called_once_with("pypdf")
        mock_provider.convert.assert_called_once()
        
        # Assert save was called correctly
        mock_save.assert_called_once()
        saved_path, content_file = mock_save.call_args[0]
        self.assertTrue(saved_path.endswith("ocr.md"))
        
        expected_md_content = b"# A great OCR target paper\n\nMocked layout text."
        self.assertEqual(content_file.read(), expected_md_content)

    @patch("django.core.files.storage.default_storage.save")
    @patch("django.core.files.storage.default_storage.open")
    @patch("research_intelligence.tasks.step_3_ocr.convert.get_ocr_provider")
    def test_run_ocr_conversion_success_html(self, mock_get_provider, mock_open, mock_save):
        from unittest.mock import mock_open as django_mock_open
        mock_open.side_effect = django_mock_open(read_data=b"%PDF-1.4 mock bytes")
        mock_save.side_effect = lambda path, content: path
        
        mock_provider = MagicMock()
        mock_provider.convert.return_value = "<h1>A great OCR target paper</h1>\nMocked layout html."
        mock_get_provider.return_value = mock_provider
        
        result = run_ocr_conversion(self.paper.id, output_format="html")
        
        self.assertTrue(result)
        self.paper.refresh_from_db()
        self.assertIsNotNone(self.paper.converted_md_path)
        self.assertTrue(self.paper.converted_md_path.endswith("ocr.md"))
        
        mock_save.assert_called_once()
        saved_path, content_file = mock_save.call_args[0]
        self.assertTrue(saved_path.endswith("ocr.md"))

    def test_run_ocr_conversion_no_pdf(self):
        # Clear pdf path
        self.paper.original_pdf_path = None
        self.paper.save()
        
        result = run_ocr_conversion(self.paper.id)
        if isinstance(result, dict):
            self.assertFalse(result.get("success"))
        else:
            self.assertFalse(result)

    def test_gemini_ocr_provider_factory(self):
        from ...ocr_providers.factory import get_ocr_provider
        from ...ocr_providers.gemini_provider import GeminiOCRProvider
        provider = get_ocr_provider("gemini")
        self.assertIsInstance(provider, GeminiOCRProvider)

    @patch("research_intelligence.ocr_providers.gemini_provider.GoogleAgentAPIProvider.generate")
    @patch("research_intelligence.ocr_providers.gemini_provider.PdfReader")
    def test_gemini_ocr_provider_convert(self, mock_pdf_reader, mock_google_generate):
        from ...ocr_providers.gemini_provider import GeminiOCRProvider
        
        mock_google_generate.return_value = "## Gemini Extracted Section\n\nFull text layout content."
        mock_pdf_reader.return_value.pages = []
        
        provider = GeminiOCRProvider()
        
        # Test markdown conversion
        res_md = provider.convert("fake/path.pdf", title="Test Gemini Paper", output_format="markdown")
        self.assertIn("Gemini Extracted Section", res_md)
        
        # Test html conversion
        res_html = provider.convert("fake/path.pdf", title="Test Gemini Paper", output_format="html")
        self.assertIn("<h1>Test Gemini Paper</h1>", res_html)


class OCRProvidersExtendedTestCase(TestCase):
    """
    Validates OCR Provider factory resolution, formatting normalization, and resilient error recovery.
    """
    def test_ocr_provider_factory_resolution(self):
        from ...ocr_providers.factory import get_ocr_provider
        from ...ocr_providers.gemini_provider import GeminiOCRProvider
        from ...ocr_providers.mistral_provider import MistralOCRProvider
        from ...ocr_providers.pypdf_provider import PyPDFOCRProvider

        self.assertIsInstance(get_ocr_provider("pypdf"), PyPDFOCRProvider)
        self.assertIsInstance(get_ocr_provider("gemini"), GeminiOCRProvider)
        self.assertIsInstance(get_ocr_provider("mistral"), MistralOCRProvider)

        with self.assertRaises(ValueError):
            get_ocr_provider("non_existent_ocr")

    @patch("research_intelligence.ocr_providers.gemini_provider.PdfReader")
    def test_gemini_ocr_provider_markdown_formatting_and_code_fence_cleaning(self, mock_reader):
        from ...ocr_providers.gemini_provider import GeminiOCRProvider
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
    def test_gemini_ocr_provider_fallback_on_exception(self, mock_reader):
        from ...ocr_providers.gemini_provider import GeminiOCRProvider
        mock_reader.return_value.pages = []
        provider = GeminiOCRProvider(model_name="google/gemini-3.7-flash")

        mock_llm = MagicMock()
        mock_llm.generate.side_effect = RuntimeError("Gemini Vision 503 Overloaded")
        provider.provider = mock_llm

        output = provider.convert("/tmp/mock.pdf", title="Failed Paper", output_format="markdown")
        self.assertIn("# Failed Paper", output)
        self.assertIn("fallback", output.lower())

    def test_mistral_ocr_provider_conversion(self):
        from ...ocr_providers.mistral_provider import MistralOCRProvider
        provider = MistralOCRProvider()
        output_md = provider.convert("/tmp/mock.pdf", title="Mistral Paper", output_format="markdown")
        self.assertIn("# Mistral Paper", output_md)
        self.assertIn("Mistral OCR layout extraction stub", output_md)

        output_html = provider.convert("/tmp/mock.pdf", title="Mistral Paper", output_format="html")
        self.assertIn("<h1>Mistral Paper</h1>", output_html)




