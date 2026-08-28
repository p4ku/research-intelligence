import json
import uuid
from django.core.serializers.json import DjangoJSONEncoder
from research_intelligence.models import Scraper
from ..workspaces import _check_workspace_access


def list_scrapers_logic(user, workspace_id: str) -> str:
    """List data scraper configurations (arXiv, OpenAlex, Lens.org) for a workspace."""
    workspace, membership, error = _check_workspace_access(user, workspace_id)
    if error:
        return error

    scrapers = Scraper.objects.filter(workspace=workspace).order_by('-created_at')
    if not scrapers.exists():
        return json.dumps({"message": f"No scrapers configured for workspace '{workspace.name}'."}, indent=2)

    results = []
    for s in scrapers:
        results.append({
            "scraper_id": str(s.id),
            "provider": s.provider,
            "provider_name": s.get_provider_display(),
            "search_query": s.search_query,
            "limit": getattr(s, 'limit', 50),
            "sort_by": getattr(s, 'sort_by', 'relevance'),
            "sort_order": getattr(s, 'sort_order', 'desc'),
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat()
        })
    return json.dumps(results, indent=2, cls=DjangoJSONEncoder)


def get_scraper_logic(user, scraper_id: str) -> str:
    """Retrieve detailed view of a specific scraper configuration."""
    try:
        s_uuid = uuid.UUID(scraper_id)
    except ValueError:
        return f"Error: '{scraper_id}' is not a valid UUID format."

    try:
        scraper = Scraper.objects.select_related('workspace').get(id=s_uuid)
    except Scraper.DoesNotExist:
        return f"Error: Scraper with ID '{scraper_id}' does not exist."

    # Check permission for the associated workspace
    workspace, membership, error = _check_workspace_access(user, str(scraper.workspace.id))
    if error:
        return error

    details = {
        "scraper_id": str(scraper.id),
        "workspace_id": str(scraper.workspace.id),
        "workspace_name": scraper.workspace.name,
        "provider": scraper.provider,
        "provider_name": scraper.get_provider_display(),
        "search_query": scraper.search_query,
        "limit": getattr(scraper, 'limit', 50),
        "sort_by": getattr(scraper, 'sort_by', 'relevance'),
        "sort_order": getattr(scraper, 'sort_order', 'desc'),
        "is_active": scraper.is_active,
        "created_at": scraper.created_at.isoformat()
    }
    return json.dumps(details, indent=2, cls=DjangoJSONEncoder)


def create_scraper_logic(
    user,
    workspace_id: str,
    provider: str,
    search_query: str,
    limit: int = 50,
    sort_by: str = "relevance",
    sort_order: str = "desc",
    is_active: bool = True
) -> str:
    """Create a new data scraper configuration (arXiv, OpenAlex, or Lens.org) for a workspace."""
    workspace, membership, error = _check_workspace_access(user, workspace_id, required_roles=['admin', 'manager'])
    if error:
        return error

    valid_providers = [choice[0] for choice in Scraper.PROVIDER_CHOICES]
    if provider not in valid_providers:
        return f"Error: Invalid provider '{provider}'. Must be one of: {valid_providers}"

    if not search_query or not search_query.strip():
        return "Error: search_query is required and cannot be blank."

    try:
        scraper = Scraper.objects.create(
            workspace=workspace,
            provider=provider,
            search_query=search_query.strip(),
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            is_active=is_active
        )
        return json.dumps({
            "success": True,
            "message": f"Successfully created {scraper.get_provider_display()} scraper for workspace '{workspace.name}'.",
            "scraper_id": str(scraper.id),
            "provider": scraper.provider,
            "search_query": scraper.search_query,
            "limit": scraper.limit,
            "sort_by": scraper.sort_by,
            "sort_order": scraper.sort_order,
            "is_active": scraper.is_active
        }, indent=2)
    except Exception as e:
        return f"Error creating scraper: {e}"


def update_scraper_logic(
    user,
    scraper_id: str,
    provider: str = None,
    search_query: str = None,
    limit: int = None,
    sort_by: str = None,
    sort_order: str = None,
    is_active: bool = None
) -> str:
    """Update an existing scraper configuration."""
    try:
        s_uuid = uuid.UUID(scraper_id)
    except ValueError:
        return f"Error: '{scraper_id}' is not a valid UUID format."

    try:
        scraper = Scraper.objects.select_related('workspace').get(id=s_uuid)
    except Scraper.DoesNotExist:
        return f"Error: Scraper with ID '{scraper_id}' does not exist."

    workspace, membership, error = _check_workspace_access(user, str(scraper.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return error

    if provider is not None:
        valid_providers = [choice[0] for choice in Scraper.PROVIDER_CHOICES]
        if provider not in valid_providers:
            return f"Error: Invalid provider '{provider}'. Must be one of: {valid_providers}"
        scraper.provider = provider

    if search_query is not None:
        if not search_query.strip():
            return "Error: search_query cannot be empty."
        scraper.search_query = search_query.strip()

    if limit is not None:
        scraper.limit = limit

    if sort_by is not None:
        scraper.sort_by = sort_by

    if sort_order is not None:
        scraper.sort_order = sort_order

    if is_active is not None:
        scraper.is_active = is_active

    scraper.save()

    return json.dumps({
        "success": True,
        "message": f"Scraper '{scraper.id}' successfully updated.",
        "scraper_id": str(scraper.id),
        "provider": scraper.provider,
        "search_query": scraper.search_query,
        "limit": scraper.limit,
        "sort_by": scraper.sort_by,
        "sort_order": scraper.sort_order,
        "is_active": scraper.is_active
    }, indent=2)


def delete_scraper_logic(user, scraper_id: str) -> str:
    """Delete a scraper configuration from a workspace."""
    try:
        s_uuid = uuid.UUID(scraper_id)
    except ValueError:
        return f"Error: '{scraper_id}' is not a valid UUID format."

    try:
        scraper = Scraper.objects.select_related('workspace').get(id=s_uuid)
    except Scraper.DoesNotExist:
        return f"Error: Scraper with ID '{scraper_id}' does not exist."

    workspace, membership, error = _check_workspace_access(user, str(scraper.workspace.id), required_roles=['admin', 'manager'])
    if error:
        return error

    provider_name = scraper.get_provider_display()
    scraper.delete()

    return json.dumps({
        "success": True,
        "message": f"Successfully deleted {provider_name} scraper configuration ({scraper_id})."
    }, indent=2)
