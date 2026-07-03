import logging
from .base import BaseOCRProvider

logger = logging.getLogger(__name__)

class DoclingOCRProvider(BaseOCRProvider):
    def convert(self, file_path: str, title: str = "Extracted Document", output_format: str = "markdown") -> str:
        logger.info(f"Using Docling to extract layout from {file_path}")
        try:
            from docling.document_converter import DocumentConverter
            converter = DocumentConverter()
            result = converter.convert(file_path)
            
            if output_format.lower() == "html":
                html_text = result.document.export_to_html()
                return f"<h1>{title}</h1>\n{html_text}"
            else:
                markdown_text = result.document.export_to_markdown()
                return f"# {title}\n\n{markdown_text}"
                
        except ImportError:
            logger.error("Docling library is not installed. Please install 'docling'.")
            raise
        except Exception as e:
            logger.error(f"Docling extraction failed for {file_path}: {str(e)}")
            raise
