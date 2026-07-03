import tempfile
import os
import logging
from celery import shared_task
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from ...models import Paper
from ...ocr_providers.factory import get_ocr_provider

logger = logging.getLogger(__name__)

@shared_task
def run_ocr_conversion(paper_id, output_format="markdown"):
    """
    Downloads the paper PDF from storage, parses it into text using the Workspace's configured OCR provider,
    and saves the resulting layout (Markdown or HTML) back to storage.
    """
    try:
        paper = Paper.objects.get(pk=paper_id)
        if not paper.original_pdf_path:
            logger.warning(f"Paper {paper_id} has no source PDF path configured. Cannot run OCR.")
            return False

        if paper.converted_md_path and default_storage.exists(paper.converted_md_path):
            logger.info(f"Paper {paper_id} is already converted to {output_format} at {paper.converted_md_path}")
            return True

        logger.info(f"Starting OCR conversion to {output_format} for paper {paper.id} from {paper.original_pdf_path} using {paper.workspace.ocr_provider}")

        # 1. Download PDF to a local temporary file
        with default_storage.open(paper.original_pdf_path, 'rb') as pdf_file:
            pdf_bytes = pdf_file.read()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
            temp_pdf.write(pdf_bytes)
            temp_pdf_path = temp_pdf.name

        # 2. Extract text using the configured OCR Provider
        try:
            provider = get_ocr_provider(paper.workspace.ocr_provider)
            converted_content = provider.convert(temp_pdf_path, title=paper.title, output_format=output_format)
        except Exception as parse_err:
            logger.error(f"Failed to parse PDF {temp_pdf_path} for paper {paper.id}: {str(parse_err)}")
            os.remove(temp_pdf_path)
            return False
            
        os.remove(temp_pdf_path)

        # 3. Save converted output to storage
        extension = "html" if output_format.lower() == "html" else "md"
        target_path = f"papers/{paper.id}.{extension}"
        default_storage.save(target_path, ContentFile(converted_content.encode("utf-8")))

        # 4. Update Paper model (keeping converted_md_path for both as it's the target doc path)
        paper.converted_md_path = target_path
        paper.save(update_fields=['converted_md_path'])

        logger.info(f"Successfully converted paper {paper.id} to {extension} at {target_path}")
        return True

    except Paper.DoesNotExist:
        logger.error(f"Paper {paper_id} does not exist.")
        return False
    except Exception as e:
        logger.exception(f"Error during OCR conversion for paper {paper_id}: {str(e)}")
        return False
