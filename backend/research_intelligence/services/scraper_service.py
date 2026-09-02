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
        qs = qs.filter(metrics__pipeline_run_id=pipeline_run_id)

    from django.db.models import Subquery, OuterRef
    from ..models import PaperMetric

    if pipeline_run_id:
        metric_sub = PaperMetric.objects.filter(paper=OuterRef('pk'), pipeline_run_id=pipeline_run_id)
    else:
        metric_sub = PaperMetric.objects.filter(paper=OuterRef('pk')).order_by('-created_at')

    qs = qs.annotate(
        annotated_pipeline_run_id=Subquery(metric_sub.values('pipeline_run_id')[:1]),
        annotated_screening_status=Subquery(metric_sub.values('screening_status')[:1]),
        annotated_screening_reasoning=Subquery(metric_sub.values('screening_reasoning')[:1]),
        annotated_signal_score=Subquery(metric_sub.values('signal_score')[:1]),
    )

    papers = list(qs.order_by('-created_at')[:limit])
    results = []
    import uuid as _uuid
    for p in papers:
        raw_pr = getattr(p, 'annotated_pipeline_run_id', None) or pipeline_run_id
        if raw_pr:
            try:
                pr_id = str(_uuid.UUID(str(raw_pr)))
            except Exception:
                pr_id = str(raw_pr)
        else:
            pr_id = None
        results.append({
            "paper_id": str(p.id),
            "pipeline_run_id": pr_id,
            "run_id": pr_id,
            "title": p.title,
            "authors": p.authors,
            "abstract": p.abstract,
            "source_database": p.source_database,
            "pdf_url": p.original_pdf_path,
            "doi": p.doi,
            "arxiv_id": p.arxiv_id,
            "screening_status": getattr(p, 'annotated_screening_status', None) or 'pending',
            "screening_reasoning": getattr(p, 'annotated_screening_reasoning', None),
            "signal_score": getattr(p, 'annotated_signal_score', None),
            "created_at": p.created_at.isoformat()
        })
    return results
