import json
import uuid
from django.core.serializers.json import DjangoJSONEncoder
from research_intelligence.models import Scraper, Paper
from mcp.tools.workspaces import _check_workspace_access


def preview_search_query_logic(user, provider: str, search_query: str, limit: int = 10) -> str:
    """Executes a live search query against a scientific provider (arXiv, OpenAlex, Lens.org) without downloading PDFs or storing DB runs."""
    valid_providers = [choice[0] for choice in Scraper.PROVIDER_CHOICES]
    if provider not in valid_providers:
        return f"Error: Invalid provider '{provider}'. Must be one of: {valid_providers}"

    if not search_query or not search_query.strip():
        return "Error: search_query is required."

    try:
        from research_intelligence.scrapers.factory import get_scraper_provider
        scraper_inst = get_scraper_provider(provider)
        results = scraper_inst.search(search_query.strip(), max_results=min(limit, 50))
        return json.dumps({
            "success": True,
            "provider": provider,
            "search_query": search_query,
            "total_results": len(results),
            "papers": results
        }, indent=2, cls=DjangoJSONEncoder)
    except Exception as e:
        return f"Error previewing scraper query: {e}"


def list_papers_logic(user, workspace_id: str, pipeline_run_id: str = None, limit: int = 50) -> str:
    """List fetched paper records for a workspace (optionally filtered by pipeline_run_id) without downloading PDFs."""
    workspace, membership, error = _check_workspace_access(user, workspace_id)
    if error:
        return error

    qs = Paper.objects.filter(workspace=workspace)
    if pipeline_run_id:
        try:
            pr_uuid = uuid.UUID(pipeline_run_id)
            qs = qs.filter(pipeline_run_id=pr_uuid)
        except ValueError:
            return f"Error: '{pipeline_run_id}' is not a valid UUID format."

    papers = list(qs.order_by('-created_at')[:limit])
    if not papers:
        return json.dumps({"message": f"No papers found for workspace '{workspace.name}'."}, indent=2)

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
            "created_at": p.created_at.isoformat()
        })
    return json.dumps(results, indent=2, cls=DjangoJSONEncoder)
