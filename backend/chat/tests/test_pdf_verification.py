"""
The fact-checker can only vouch for a quote it can read. On the PDF path the
prompt text carries no body (Gemini reads the bytes), so the body is
extracted from the stored PDF for verification; with no stored document at
all, the check is skipped rather than run against the abstract.
"""
import uuid
from unittest.mock import patch, MagicMock

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from chat.engine import PaperChatEngine, PaperContextBuilder, CitationFactChecker
from chat.engine.pdf_text import extract_pdf_text
from chat.models import PaperChatMessage
from .base import BaseChatTestCase

BODY_SENTENCE = "The photonic core dissipates 15 fJ per synaptic operation at 4 GHz"


def make_text_pdf(text: str) -> bytes:
    """A one-page PDF with a single Helvetica text object, enough for pypdf to extract."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


class PdfTextTestCase(BaseChatTestCase):

    def test_extracts_page_text(self):
        text = extract_pdf_text(make_text_pdf(BODY_SENTENCE))
        self.assertIn("## Page 1", text)
        self.assertIn("15 fJ per synaptic operation", text)

    def test_garbage_and_empty_never_raise(self):
        self.assertEqual(extract_pdf_text(b"%PDF-1.4 not really a pdf"), "")
        self.assertEqual(extract_pdf_text(b""), "")
        self.assertEqual(extract_pdf_text(None), "")


class VerificationSourceTestCase(BaseChatTestCase):

    def setUp(self):
        super().setUp()
        self.stored_paths = []

    def tearDown(self):
        for path in self.stored_paths:
            if default_storage.exists(path):
                default_storage.delete(path)
        super().tearDown()

    def _store_pdf(self, text: str) -> str:
        path = f"workspaces/{self.workspace.id}/runs/{self.run.id}/documents/{uuid.uuid4().hex}/original.pdf"
        default_storage.save(path, ContentFile(make_text_pdf(text)))
        self.stored_paths.append(path)
        return path

    def test_stored_pdf_gives_verification_text_but_not_prompt_text(self):
        paper = self.create_paper(
            workspace=self.workspace, pipeline_run=self.run, hash_id="sha256_pdf_verify_01",
            title="Photonic Paper", abstract="An abstract that does not repeat the body.",
            original_pdf_path=self._store_pdf(BODY_SENTENCE),
        )
        doc = PaperContextBuilder().document(paper)
        self.assertTrue(doc.has_body)
        self.assertIn("15 fJ per synaptic operation", doc.verification_text)
        self.assertIsNotNone(doc.pdf_bytes)
        # The model reads the bytes; the extracted text must not double the prompt.
        self.assertNotIn("15 fJ per synaptic operation", doc.text)
        self.assertIn("Attached as native multimodal PDF", doc.text)

    def test_url_only_paper_has_no_body(self):
        paper = self.create_paper(
            workspace=self.workspace, pipeline_run=self.run, hash_id="sha256_url_only_01",
            title="arXiv Paper", abstract="Only the abstract is known.",
            original_pdf_path="https://arxiv.org/pdf/2608.00001v1",
        )
        doc = PaperContextBuilder().document(paper)
        self.assertFalse(doc.has_body)
        self.assertEqual(doc.verification_text, "")
        self.assertIsNone(doc.pdf_bytes)

    def test_verifier_skips_without_a_body(self):
        cits = [{"page": 2, "label": "Fig 1", "quote": "Only the abstract is known"}]
        flagged, guard = CitationFactChecker().verify("Title: x\nAbstract: Only the abstract is known.", cits, has_body=False)
        self.assertIsNone(flagged[0]["verified_in_source"])
        self.assertEqual(guard["status"], "SKIPPED_NO_SOURCE_TEXT")
        self.assertFalse(guard["verified"])
        self.assertEqual(guard["total_count"], 0)

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_body_quote_is_verified_on_the_pdf_path(self, mock_get_llm_provider):
        paper = self.create_paper(
            workspace=self.workspace, pipeline_run=self.run, hash_id="sha256_pdf_verify_02",
            title="Photonic Paper", abstract="An abstract that does not repeat the body.",
            original_pdf_path=self._store_pdf(BODY_SENTENCE),
        )
        session = self.create_session(paper=paper, user=self.user)
        message = PaperChatMessage.objects.create(session=session, sender='user', status='pending',
                                                  question="How much energy per operation?")
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            'It is tiny [Page 1, quote: "dissipates 15 fJ per synaptic operation"] according to the core figures.',
            {"prompt_tokens": 500, "candidates_tokens": 30},
        )
        mock_get_llm_provider.return_value = mock_provider

        result = PaperChatEngine().execute(message)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["visual_citations"][0]["verified_in_source"])
        self.assertEqual(result["hallucination_guard"]["status"], "PASS")
        # And the PDF went to the model as bytes, not as text.
        self.assertIsNotNone(mock_provider.generate.call_args.kwargs["file_bytes"])

    @patch("chat.engine.orchestrator.get_llm_provider")
    def test_abstract_only_paper_is_not_scored_against_the_abstract(self, mock_get_llm_provider):
        paper = self.create_paper(
            workspace=self.workspace, pipeline_run=self.run, hash_id="sha256_url_only_02",
            title="arXiv Paper", abstract="Only the abstract is known.",
            original_pdf_path="https://arxiv.org/pdf/2608.00002v1",
        )
        session = self.create_session(paper=paper, user=self.user)
        message = PaperChatMessage.objects.create(session=session, sender='user', status='pending',
                                                  question="What is known?")
        mock_provider = MagicMock()
        mock_provider.generate.return_value = (
            'The paper says [quote: "Only the abstract is known"] and little else.',
            {"prompt_tokens": 100, "candidates_tokens": 20},
        )
        mock_get_llm_provider.return_value = mock_provider

        result = PaperChatEngine().execute(message)
        self.assertEqual(result["status"], "completed")
        self.assertIsNone(result["visual_citations"][0]["verified_in_source"])
        self.assertEqual(result["hallucination_guard"]["status"], "SKIPPED_NO_SOURCE_TEXT")
