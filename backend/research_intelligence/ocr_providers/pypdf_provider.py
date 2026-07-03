import logging
from pypdf import PdfReader
from .base import BaseOCRProvider
import base64

logger = logging.getLogger(__name__)

class PyPDFOCRProvider(BaseOCRProvider):
    def convert(self, file_path: str, title: str = "Extracted Document", output_format: str = "markdown") -> str:
        logger.info(f"Using PyPDF to extract text from {file_path} in format {output_format}")
        
        is_html = output_format.lower() == "html"
        
        output_content = f"<h1>{title}</h1>\n\n" if is_html else f"# {title}\n\n"
        
        try:
            reader = PdfReader(file_path)
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    if is_html:
                        output_content += f"<h2>Page {page_num + 1}</h2>\n<p>{text}</p>\n\n"
                    else:
                        output_content += f"## Page {page_num + 1}\n{text}\n\n"
                
                # Extract images and embed them as Base64
                for image_file_object in page.images:
                    try:
                        base64_img = base64.b64encode(image_file_object.data).decode('utf-8')
                        mime_type = "image/png"
                        if image_file_object.name.lower().endswith((".jpg", ".jpeg")):
                            mime_type = "image/jpeg"
                            
                        if is_html:
                            output_content += f'<img src="data:{mime_type};base64,{base64_img}" alt="{image_file_object.name}" />\n\n'
                        else:
                            output_content += f"![{image_file_object.name}](data:{mime_type};base64,{base64_img})\n\n"
                    except Exception as img_err:
                        logger.warning(f"Failed to extract image {image_file_object.name}: {str(img_err)}")
                        
            return output_content
        except Exception as e:
            logger.error(f"PyPDF extraction failed for {file_path}: {str(e)}")
            raise
