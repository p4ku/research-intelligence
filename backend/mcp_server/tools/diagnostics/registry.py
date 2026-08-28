import json
import logging
from django.db.models import Sum, Count
from django.core.files.storage import default_storage

from research_intelligence.models import DocumentRegistry

logger = logging.getLogger(__name__)


def get_document_registry_stats_logic(user) -> str:
    """
    Returns global analytics and efficiency metrics for the DocumentRegistry:
    - Total cached papers (PDFs and OCR artifacts)
    - Total cache hits / reuse count (bandwidth and OCR compute saved)
    - Total storage footprint in bytes and human-readable format
    - Top 10 most reused research documents across workspaces
    """
    total_docs = DocumentRegistry.objects.count()
    aggregates = DocumentRegistry.objects.aggregate(
        total_hits=Sum('access_count'),
        total_bytes=Sum('pdf_file_size_bytes')
    )

    total_hits = aggregates['total_hits'] or 0
    total_bytes = aggregates['total_bytes'] or 0

    # Human-friendly formatting
    if total_bytes < 1024 * 1024:
        size_formatted = f"{total_bytes / 1024:.1f} KB"
    elif total_bytes < 1024 * 1024 * 1024:
        size_formatted = f"{total_bytes / (1024 * 1024):.2f} MB"
    else:
        size_formatted = f"{total_bytes / (1024 * 1024 * 1024):.2f} GB"

    # Top reused papers
    top_papers = []
    for doc in DocumentRegistry.objects.filter(access_count__gt=1).order_by('-access_count')[:10]:
        top_papers.append({
            "id": str(doc.id),
            "title": doc.title,
            "doi": doc.doi,
            "arxiv_id": doc.arxiv_id,
            "access_count": doc.access_count,
            "primary_source": doc.primary_source,
            "ocr_provider": doc.ocr_provider,
            "has_ocr_cache": bool(doc.canonical_ocr_md_path and default_storage.exists(doc.canonical_ocr_md_path)),
            "last_accessed_at": doc.last_accessed_at.isoformat() if doc.last_accessed_at else None
        })

    payload = {
        "status": "success",
        "total_cached_documents": total_docs,
        "total_cache_hits": total_hits,
        "bandwidth_saved_multiplier": round(total_hits / max(total_docs, 1), 2),
        "total_storage_bytes": total_bytes,
        "total_storage_formatted": size_formatted,
        "top_reused_documents": top_papers
    }

    return json.dumps(payload, indent=2)
