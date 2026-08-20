import logging
from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import Paper, DocumentRegistry

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=Paper)
def on_paper_deleted_decrement_registry(sender, instance, **kwargs):
    """
    When a Paper is deleted (directly via Admin, API, or through cascading deletion
    of PipelineRun/Workspace/ResearchAgentProcess), decrement the access_count
    of the associated DocumentRegistry entry.
    """
    doc_reg_id = getattr(instance, 'document_registry_id', None)
    try:
        doc_reg = None
        if doc_reg_id:
            doc_reg = DocumentRegistry.objects.filter(id=doc_reg_id).first()
        elif getattr(instance, 'hash_id', None):
            doc_reg = DocumentRegistry.objects.filter(sha256_hash=instance.hash_id).first()
        elif getattr(instance, 'arxiv_id', None):
            doc_reg = DocumentRegistry.objects.filter(arxiv_id=instance.arxiv_id).first()
        elif getattr(instance, 'doi', None):
            doc_reg = DocumentRegistry.objects.filter(doi=instance.doi).first()

        if doc_reg:
            new_count = max(0, doc_reg.access_count - 1)
            DocumentRegistry.objects.filter(id=doc_reg.id).update(access_count=new_count)
            logger.info(
                f"📉 [DOCUMENT REGISTRY] Paper '{getattr(instance, 'id', 'unknown')}' deleted -> decremented "
                f"DocumentRegistry '{doc_reg.id}' ('{doc_reg.title[:30]}...') access_count: {doc_reg.access_count} -> {new_count}"
            )
    except Exception as e:
        logger.warning(f"Error decrementing DocumentRegistry access_count for deleted paper '{getattr(instance, 'id', 'unknown')}': {e}")
