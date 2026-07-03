import logging
from .base import BaseOCRProvider

logger = logging.getLogger(__name__)

class MistralOCRProvider(BaseOCRProvider):
    def convert(self, file_path: str, title: str = "Extracted Document", output_format: str = "markdown") -> str:
        logger.info(f"Using Mistral OCR API to extract layout from {file_path}")
        
        if output_format.lower() == "html":
            logger.warning("Mistral OCR is currently a stub. Returning dummy html.")
            return f"<h1>{title}</h1>\n<p><i>Mistral OCR layout extraction stub.</i></p>"
            
        logger.warning("Mistral OCR is currently a stub. Returning dummy markdown.")
        return f"# {title}\n\n*Mistral OCR layout extraction stub.*"
