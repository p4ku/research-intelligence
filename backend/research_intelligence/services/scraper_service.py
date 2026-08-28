"""
Domain Service for Scraper providers, search normalization, and query preview execution.
"""
import logging
from typing import Dict, Any, List, Optional
from django.core.serializers.json import DjangoJSONEncoder
from research_intelligence.models import Scraper, Paper, Workspace
from research_intelligence.scrapers import factory
from research_intelligence.tasks.step_1_search.dedup import normalize_doi, normalize_arxiv_id, normalize_title

logger = logging.getLogger(__name__)


def preview_search_query(provider: str, search_query: str, limit: int = 10) -> Dict[str, Any]:
    """
    Executes a live search query against a scientific provider (arXiv, OpenAlex, Lens.org)
    without downloading PDFs or persisting records to the database.
    """
    valid_providers = [choice[0] for choice in Scraper.PROVIDER_CHOICES]
    if provider not in valid_providers:
        raise ValueError(f"Invalid provider '{provider}'. Must be one of: {valid_providers}")

    if not search_query or not search_query.strip():
        raise ValueError("search_query is required.")

    scraper_inst = factory.get_scraper_provider(provider)
    results = scraper_inst.search(search_query.strip(), max_results=min(limit, 50))
    return {
        "success": True,
        "provider": provider,
        "search_query": search_query,
        "total_results": len(results),
        "papers": results
    }


def list_workspace_papers(
    user,
    workspace_id: str,
    pipeline_run_id: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Retrieves fetched papers for a workspace (optionally filtered by pipeline_run_id).
    """
    qs = Paper.objects.filter(workspace_id=workspace_id)
    if pipeline_run_id:
        qs = qs.filter(pipeline_run_id=pipeline_run_id)

    papers = list(qs.order_by('-created_at')[:limit])
    results = []
    for p in papers:
        results.append({
            "paper_id": str(p.id),
            "title": p.title,
            "authors": p.authors,
            "abstract": p.abstract,
            "source_database": p.source_database,
            "pdf_url": p.original_pdf_path,
            "doi": p.doi,
            "arxiv_id": p.arxiv_id,
            "screening_status": p.screening_status,
            "screening_reasoning": p.screening_reasoning,
            "signal_score": p.signal_score,
            "created_at": p.created_at.isoformat()
        })
    return results
