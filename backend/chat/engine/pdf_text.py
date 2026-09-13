"""
Plain text out of a PDF, for the chat fact-checker.

The OCR step's pypdf provider (`research_intelligence.ocr_providers.pypdf_provider`)
is not reused here: it inlines every page image as base64, which is right for
a stored document and wrong for a string that only has to contain the words
the model may quote.
"""
import io
import logging

logger = logging.getLogger(__name__)


def extract_pdf_text(pdf_bytes: bytes | None) -> str:
    """
    Text of every page, each under a `## Page N` heading so a page-led
    marker can be sanity-checked later. Empty string when the PDF has no
    extractable text (scanned) or cannot be parsed; never raises.
    """
    if not pdf_bytes:
        return ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for number, page in enumerate(reader.pages, start=1):
            try:
                page_text = (page.extract_text() or "").strip()
            except Exception:
                logger.debug("pypdf could not extract page %s", number, exc_info=True)
                page_text = ""
            if page_text:
                pages.append(f"## Page {number}\n{page_text}")
        return "\n\n".join(pages)
    except Exception as e:
        logger.warning(f"PDF text extraction failed: {e}")
        return ""
