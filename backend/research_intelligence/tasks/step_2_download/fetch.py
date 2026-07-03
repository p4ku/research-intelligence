import logging
from celery import shared_task
from ...models import Paper
from ...scrapers import get_scraper_provider
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

@shared_task
def download_pdf_to_s3(paper_id):
    """
    Downloads paper PDF using the appropriate scraper provider and uploads it to storage.
    """
    try:
        paper = Paper.objects.get(pk=paper_id)
        if not paper.original_pdf_path:
            logger.warning(f"Paper {paper_id} has no source PDF URL configured.")
            return False
            
        # If it's already downloaded and stored locally in S3, no need to download again
        if not (paper.original_pdf_path.startswith("http://") or paper.original_pdf_path.startswith("https://")):
            logger.info(f"Paper {paper_id} is already stored in storage: {paper.original_pdf_path}")
            return True

        provider = get_scraper_provider(paper.source_database)
        logger.info(f"Downloading PDF for paper {paper.id} from {paper.original_pdf_path} using {paper.source_database}")
        
        file_bytes = provider.download_file(paper.original_pdf_path)
        if not file_bytes:
            logger.error(f"Downloaded empty file bytes for paper {paper_id}")
            return False
            
        target_path = f"papers/{paper.id}.pdf"
        default_storage.save(target_path, ContentFile(file_bytes))
        
        paper.original_pdf_path = target_path
        paper.save()
        
        logger.info(f"Successfully downloaded and uploaded paper {paper.id} to {target_path}")
        return True
    except Paper.DoesNotExist:
        logger.error(f"Paper {paper_id} does not exist.")
        return False
    except Exception as e:
        logger.exception(f"Error downloading PDF for paper {paper_id}: {str(e)}")
        return False
