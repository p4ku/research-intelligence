import json
from typing import Optional
from research_intelligence.models import Extraction, Workspace


def list_extractions_logic(
    user,
    workspace_id: Optional[str] = None,
    paper_id: Optional[str] = None,
    category: Optional[str] = None,
    validation_status: Optional[str] = None,
    limit: int = 50
) -> str:
    """
    Returns a JSON list of Extraction records (Step 5 outputs).
    Filters by workspace_id, paper_id, category, or validation_status.
    """
    qs = Extraction.objects.select_related('workspace', 'paper', 'extraction_definition').all()

    if workspace_id:
        qs = qs.filter(workspace__id=workspace_id)
    elif user and not user.is_superuser:
        user_ws_ids = Workspace.objects.filter(memberships__user=user).values_list('id', flat=True)
        qs = qs.filter(workspace__id__in=user_ws_ids)

    if paper_id:
        qs = qs.filter(paper__id=paper_id)
    if category:
        qs = qs.filter(category=category)
    if validation_status:
        qs = qs.filter(validation_status=validation_status)

    extractions = list(qs.order_by('-created_at')[:limit])
    results = []

    for ext in extractions:
        results.append({
            "id": str(ext.id),
            "workspace_id": str(ext.workspace.id),
            "workspace_name": ext.workspace.name,
            "paper_id": str(ext.paper.id),
            "paper_title": ext.paper.title,
            "definition_id": str(ext.extraction_definition.id) if ext.extraction_definition else None,
            "definition_name": ext.extraction_definition.name if ext.extraction_definition else ext.category,
            "category": ext.category,
            "validation_status": ext.validation_status,
            "confidence_score": ext.confidence_score,
            "review_required": ext.review_required,
            "fields_data": ext.fields_data,
            "version_info": ext.version_info,
            "created_at": ext.created_at.isoformat() if ext.created_at else None
        })

    return json.dumps(results, indent=2)


def get_extraction_logic(user, extraction_id: str) -> str:
    """
    Returns full details for a single Extraction object by UUID.
    """
    try:
        ext = Extraction.objects.select_related('workspace', 'paper', 'extraction_definition').get(pk=extraction_id)
    except Extraction.DoesNotExist:
        from research_intelligence.models import ExtractionDefinition
        if ExtractionDefinition.objects.filter(id=extraction_id).exists():
            from .extraction_definitions import get_extraction_definition_logic
            return get_extraction_definition_logic(user, extraction_id)
        return json.dumps({"error": f"Extraction '{extraction_id}' not found."})

    payload = {
        "id": str(ext.id),
        "workspace_id": str(ext.workspace.id),
        "workspace_name": ext.workspace.name,
        "paper_id": str(ext.paper.id),
        "paper_title": ext.paper.title,
        "paper_doi": ext.paper.doi,
        "paper_arxiv_id": ext.paper.arxiv_id,
        "definition_id": str(ext.extraction_definition.id) if ext.extraction_definition else None,
        "definition_name": ext.extraction_definition.name if ext.extraction_definition else ext.category,
        "system_prompt": ext.extraction_definition.system_prompt if ext.extraction_definition else None,
        "user_prompt_template": ext.extraction_definition.user_prompt_template if ext.extraction_definition else None,
        "category": ext.category,
        "fields_data": ext.fields_data,
        "validation_status": ext.validation_status,
        "confidence_score": ext.confidence_score,
        "confidence_method": ext.confidence_method,
        "review_required": ext.review_required,
        "is_hitl_validated": ext.is_hitl_validated,
        "version_info": ext.version_info,
        "created_at": ext.created_at.isoformat() if ext.created_at else None
    }

    return json.dumps(payload, indent=2)
