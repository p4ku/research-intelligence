import logging
from django.db.models import Q
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from ...models import Paper

logger = logging.getLogger(__name__)


def try_reuse_cached_pdf(paper: Paper, target_path: str, title_snippet: str = "") -> dict | None:
    """
    Cross-Workspace / Cross-Run PDF Cache Reuse (Zero-Network Fast Path).
    Checks if ANY paper record across the entire platform has already stored this document in default_storage.
    If found, copies the binary locally into `target_path` without hitting external network scrapers.
    
    Returns:
        dict with status payload if cache hit succeeded, or None if no valid cache exists.
    """
    lookup_q = None
    if paper.hash_id:
        lookup_q = Q(hash_id=paper.hash_id)
    if paper.doi:
        lookup_q = (lookup_q | Q(doi=paper.doi)) if lookup_q else Q(doi=paper.doi)
    if paper.arxiv_id:
        lookup_q = (lookup_q | Q(arxiv_id=paper.arxiv_id)) if lookup_q else Q(arxiv_id=paper.arxiv_id)

    if not lookup_q:
        return None

    cached_paper = (
        Paper.objects.filter(lookup_q)
        .exclude(id=paper.id)
        .exclude(original_pdf_path__startswith="http://")
        .exclude(original_pdf_path__startswith="https://")
        .exclude(original_pdf_path="")
        .exclude(original_pdf_path__isnull=True)
        .first()
    )

    if not cached_paper or not default_storage.exists(cached_paper.original_pdf_path):
        return None

    try:
        with default_storage.open(cached_paper.original_pdf_path, 'rb') as src_file:
            file_bytes = src_file.read()

        if file_bytes and len(file_bytes) > 0:
            saved_path = default_storage.save(target_path, ContentFile(file_bytes))
            paper.original_pdf_path = saved_path
            paper.save(update_fields=['original_pdf_path'])
            size_bytes = len(file_bytes)
            size_kb = size_bytes / 1024
            logger.info(
                f"⚡ [CACHE REUSE] Reused cached PDF [{size_kb:.1f} KB] from "
                f"'{cached_paper.original_pdf_path}' -> saved to: '{saved_path}' (Paper: '{title_snippet}...')",
            )
            return {
                "status": "downloaded",
                "paper_id": str(paper.id),
                "title": paper.title,
                "size_bytes": size_bytes,
                "size_kb": round(size_kb, 1),
                "storage_path": saved_path,
                "cache_hit": True,
                "cached_from": cached_paper.original_pdf_path
            }
    except Exception as e:
        logger.warning(f"Failed to copy cached PDF from '{cached_paper.original_pdf_path}': {e}")
        return None

    return None
