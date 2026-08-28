import json
import uuid
from django.core.serializers.json import DjangoJSONEncoder
from research_intelligence.models import Scraper, Paper
from research_intelligence.services import (
    check_workspace_access,
    preview_search_query,
    list_workspace_papers,
)


def preview_search_query_logic(user, provider: str, search_query: str, limit: int = 10) -> str:
    """Executes a live search query against a scientific provider (arXiv, OpenAlex, Lens.org) without downloading PDFs or storing DB runs."""
    valid_providers = [choice[0] for choice in Scraper.PROVIDER_CHOICES]
    if provider not in valid_providers:
        return f"Error: Invalid provider '{provider}'. Must be one of: {valid_providers}"

    if not search_query or not search_query.strip():
        return "Error: search_query is required."

    try:
        payload = preview_search_query(provider=provider, search_query=search_query, limit=limit)
        return json.dumps(payload, indent=2, cls=DjangoJSONEncoder)
    except Exception as e:
        return f"Error previewing scraper query: {e}"


def list_papers_logic(user, workspace_id: str, pipeline_run_id: str = None, limit: int = 50) -> str:
    """List fetched paper records for a workspace (optionally filtered by pipeline_run_id) without downloading PDFs."""
    workspace, membership, error = check_workspace_access(user, workspace_id)
    if error:
        return error

    if pipeline_run_id:
        try:
            uuid.UUID(pipeline_run_id)
        except ValueError:
            return f"Error: '{pipeline_run_id}' is not a valid UUID format."

    results = list_workspace_papers(
        user=user,
        workspace_id=str(workspace.id),
        pipeline_run_id=pipeline_run_id,
        limit=limit
    )
    if not results:
        return json.dumps({"message": f"No papers found for workspace '{workspace.name}'."}, indent=2)

    return json.dumps(results, indent=2, cls=DjangoJSONEncoder)

