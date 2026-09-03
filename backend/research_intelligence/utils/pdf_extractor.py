import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def extract_text_from_pdf_bytes(pdf_bytes: Optional[bytes], max_chars: int = 120000) -> str:
    """
    Safely extract plain text from in-memory PDF bytes using pypdf.
    Fast (<0.1s), memory-efficient, and resilient to damaged or unreadable pages.
    Used as an automatic fallback when Google GenAI rejects binary PDF with 400 INVALID_ARGUMENT
    or when PDF exceeds the 15MB inline multimodal threshold.
    """
    if not pdf_bytes:
        return ""
    try:
        from pypdf import PdfReader
        stream = io.BytesIO(pdf_bytes)
        reader = PdfReader(stream)
        extracted = []
        curr_chars = 0
        for page_idx, page in enumerate(reader.pages):
            try:
                t = page.extract_text()
                if t:
                    extracted.append(t)
                    curr_chars += len(t)
                    if curr_chars >= max_chars:
                        break
            except Exception as page_err:
                logger.debug(f"Skipped unreadable page {page_idx} during PDF text extraction: {page_err}")
                continue
        return "\n\n".join(extracted)[:max_chars]
    except Exception as e:
        logger.warning(f"Failed to extract text from PDF bytes via PyPDF: {e}")
        return ""
