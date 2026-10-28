import base64
import logging
from pypdf import PdfReader
from .base import BaseOCRProvider
from research_intelligence.llm_providers.google import GoogleAgentAPIProvider

logger = logging.getLogger(__name__)

GEMINI_OCR_SYSTEM_INSTRUCTION_HTML = """You are an enterprise-grade document OCR and vision layout engine. Your job is to convert scientific papers and technical PDFs into valid, semantic, clean HTML documents.

ROBUST TRANSCRIPTION RULES:
1. STRUCTURE & HEADINGS: Use semantic HTML elements (<h1> for title, <h2> for sections, <h3> for subsections, <p> for paragraphs, <ul>, <ol>, <li>, <blockquote>, <section>).
2. TABLES: Convert tables into clean HTML <table> structures with <thead>, <tbody>, <tr>, <th>, <td>. Preserve exact numerical values and column headers.
3. EQUATIONS: Convert mathematical equations into LaTeX syntax wrapped in $$...$$ for block equations or \\(...\\) for inline equations, or semantic <code>/<pre> blocks.
4. METADATA & CAPTIONS: Preserve paper title, author list, abstract, section titles, figure captions (<figcaption>), and reference lists.
5. PURE OUTPUT: Output ONLY raw HTML. Do NOT include markdown code blocks (e.g. ```html) or any conversational preamble/postscript text.
"""

GEMINI_OCR_SYSTEM_INSTRUCTION_MD = """You are an enterprise-grade document OCR and vision layout engine. Your job is to convert scientific papers and technical PDFs into structured GitHub-Flavored Markdown.

ROBUST TRANSCRIPTION RULES:
1. STRUCTURE & HEADINGS: Use standard Markdown headers (# Title, ## Section, ### Subsection), paragraphs, and bullet/numbered lists.
2. TABLES: Convert data tables into clean GFM Markdown tables (| Header | Header | ...). Preserve exact numbers and column alignments.
3. EQUATIONS: Convert mathematical formulas into LaTeX syntax ($$...$$ for display equations, $...$ for inline equations).
4. METADATA & CAPTIONS: Preserve paper title as '# Title', author list, abstract blockquote (> Abstract), figure captions (*Figure X: ...*), and references.
5. PURE OUTPUT: Output ONLY raw Markdown text. Do NOT wrap the response in ```markdown code blocks or add preamble/postscript text.
"""


class GeminiOCRProvider(BaseOCRProvider):
    """
    OCR & Document Layout Extraction Provider using Google Gemini Multimodal API (Default: gemini-3.8-flash).
    Transcribes text, headings, equations, and tables via Gemini Vision into rich HTML or Markdown, and extracts embedded figures/images as inline Base64 Data URIs.
    """
    def __init__(self, model_name: str = "google/gemini-3.8-flash"):
        self.model_name = model_name
        self.provider = GoogleAgentAPIProvider()


    def _extract_images_as_base64(self, file_path: str, is_html: bool) -> str:
        """Extract embedded images from PDF pages and return them formatted as Base64 HTML or Markdown."""
        images_content = ""
        try:
            reader = PdfReader(file_path)
            for page_num, page in enumerate(reader.pages):
                for image_file_object in page.images:
                    try:
                        base64_img = base64.b64encode(image_file_object.data).decode('utf-8')
                        mime_type = "image/png"
                        if image_file_object.name.lower().endswith((".jpg", ".jpeg")):
                            mime_type = "image/jpeg"
                            
                        img_title = f"Page {page_num + 1} - {image_file_object.name}"
                        if is_html:
                            images_content += f'<div class="pdf-image" style="margin: 15px 0;"><img src="data:{mime_type};base64,{base64_img}" alt="{img_title}" style="max-width: 100%; border-radius: 4px;" /><p style="font-size: 12px; color: #666;"><i>{img_title}</i></p></div>\n\n'
                        else:
                            images_content += f"![{img_title}](data:{mime_type};base64,{base64_img})\n*Figure: {img_title}*\n\n"
                    except Exception as img_err:
                        logger.warning(f"Failed to extract image {getattr(image_file_object, 'name', 'img')} on page {page_num+1}: {str(img_err)}")
        except Exception as e:
            logger.warning(f"PyPDF image extraction failed for {file_path}: {str(e)}")
        return images_content

    def _clean_output(self, text: str) -> str:
        """Strip markdown code fence blocks if present."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned

    def convert(self, file_path: str, title: str = "Extracted Document", output_format: str = "markdown") -> str:
        logger.info(f"Using Gemini OCR ({self.model_name}) to extract layout from {file_path} (Format: {output_format})")
        
        is_html = output_format.lower() == "html"
        system_instruction = GEMINI_OCR_SYSTEM_INSTRUCTION_HTML if is_html else GEMINI_OCR_SYSTEM_INSTRUCTION_MD
        title_header = f"<h1>{title}</h1>\n\n" if is_html else f"# {title}\n\n"
        
        prompt = (
            f"Please transcribe and convert the attached PDF document '{title}' into complete {'semantic HTML' if is_html else 'Markdown'}. "
            f"Preserve all section titles, paragraphs, tables, formulas, and references."
        )
        
        gemini_text = ""
        try:
            res = self.provider.generate(
                prompt=prompt,
                system_instruction=system_instruction,
                pdf_path=file_path,
                model=self.model_name
            )
            if isinstance(res, str):
                gemini_text = res
            elif isinstance(res, dict) and "text" in res:
                gemini_text = str(res["text"])
            elif hasattr(res, "text") and res.text:
                gemini_text = str(res.text)
            else:
                gemini_text = str(res)
        except Exception as e:
            logger.error(f"Gemini OCR extraction failed for {file_path}: {str(e)}")
            gemini_text = f"<p>Gemini OCR layout extraction fallback.</p>" if is_html else "*Gemini OCR layout extraction fallback.*"

        gemini_text = self._clean_output(gemini_text)

        # Extract embedded images as Base64 data URIs
        images_html_or_md = self._extract_images_as_base64(file_path, is_html=is_html)
        
        # Combine text layout + base64 embedded images
        final_output = gemini_text.strip()
        if is_html:
            if not final_output.startswith("<h1"):
                final_output = title_header + final_output
        else:
            if not final_output.startswith("#"):
                final_output = title_header + final_output

        if images_html_or_md:
            img_section_header = "<h2>Document Figures & Images</h2>\n\n" if is_html else "\n\n## Document Figures & Images\n\n"
            final_output += "\n\n" + img_section_header + images_html_or_md

        return final_output
