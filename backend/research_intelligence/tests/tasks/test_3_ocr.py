from django.test import TestCase
from unittest.mock import patch, MagicMock
from ...models import Workspace, PipelineRun, Paper
from ...tasks.step_3_ocr.convert import run_ocr_conversion

class OCRConversionTaskTestCase(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="OCR Test Project",
            acceptance_criteria="Accept active learning.",
            rejection_criteria="Reject rule-based systems.",
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
        
        # Setup mock OCR provider
        mock_provider = MagicMock()
        mock_provider.convert.return_value = "# A great OCR target paper\n\nMocked layout text."
        mock_get_provider.return_value = mock_provider
        
        result = run_ocr_conversion(self.paper.id, output_format="markdown")
        
        self.assertTrue(result)
        
        self.paper.refresh_from_db()
        expected_md_path = f"papers/{self.paper.id}.md"
        self.assertEqual(self.paper.converted_md_path, expected_md_path)
        
        # Assert provider called
        mock_get_provider.assert_called_once_with("pypdf")
        mock_provider.convert.assert_called_once()
        
        # Assert save was called correctly
        mock_save.assert_called_once()
        saved_path, content_file = mock_save.call_args[0]
        self.assertEqual(saved_path, expected_md_path)
        
        expected_md_content = b"# A great OCR target paper\n\nMocked layout text."
        self.assertEqual(content_file.read(), expected_md_content)

    @patch("django.core.files.storage.default_storage.save")
    @patch("django.core.files.storage.default_storage.open")
    @patch("research_intelligence.tasks.step_3_ocr.convert.get_ocr_provider")
    def test_run_ocr_conversion_success_html(self, mock_get_provider, mock_open, mock_save):
        from unittest.mock import mock_open as django_mock_open
        mock_open.side_effect = django_mock_open(read_data=b"%PDF-1.4 mock bytes")
        
        mock_provider = MagicMock()
        mock_provider.convert.return_value = "<h1>A great OCR target paper</h1>\nMocked layout html."
        mock_get_provider.return_value = mock_provider
        
        result = run_ocr_conversion(self.paper.id, output_format="html")
        
        self.assertTrue(result)
        self.paper.refresh_from_db()
        expected_html_path = f"papers/{self.paper.id}.html"
        self.assertEqual(self.paper.converted_md_path, expected_html_path)
        
        mock_save.assert_called_once()
        saved_path, content_file = mock_save.call_args[0]
        self.assertEqual(saved_path, expected_html_path)

    def test_run_ocr_conversion_no_pdf(self):
        # Clear pdf path
        self.paper.original_pdf_path = None
        self.paper.save()
        
        result = run_ocr_conversion(self.paper.id)
        self.assertFalse(result)
