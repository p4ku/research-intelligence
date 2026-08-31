import json
from typing import Optional
from research_intelligence.models import Extraction, Workspace, Paper, PipelineRun, ResearchAgentProcess


from research_intelligence.services import check_workspace_access


def list_extractions_logic(
    user,
    workspace_id: Optional[str] = None,
    pipeline_run_id: Optional[str] = None,
    process_id: Optional[str] = None,
    paper_id: Optional[str] = None,
    category: Optional[str] = None,
    validation_status: Optional[str] = None,
    limit: int = 100
) -> str:
    """
    Returns a JSON list of Extraction records.
    Filters by workspace_id, pipeline_run_id, process_id, paper_id, category, or validation_status.
    """
    qs = Extraction.objects.select_related('workspace', 'paper', 'extraction_definition').all()

    if process_id:
        try:
            proc = ResearchAgentProcess.objects.select_related('workspace', 'pipeline_run').get(id=process_id)
            workspace, _, error = check_workspace_access(user, str(proc.workspace.id))
            if error:
                return json.dumps({"error": error})
            if proc.pipeline_run:
                qs = qs.filter(paper__pipeline_run=proc.pipeline_run)
            else:
                qs = qs.filter(workspace=proc.workspace)
        except (ValueError, ResearchAgentProcess.DoesNotExist):
            return json.dumps({"error": f"ResearchAgentProcess '{process_id}' not found."})
    elif pipeline_run_id:
        try:
            pipeline_run = PipelineRun.objects.select_related('workspace').get(id=pipeline_run_id)
            workspace, _, error = check_workspace_access(user, str(pipeline_run.workspace.id))
            if error:
                return json.dumps({"error": error})
            qs = qs.filter(paper__pipeline_run=pipeline_run)
        except (ValueError, PipelineRun.DoesNotExist):
            return json.dumps({"error": f"PipelineRun '{pipeline_run_id}' not found."})
    elif workspace_id:
        workspace, _, error = check_workspace_access(user, workspace_id)
        if error:
            return json.dumps({"error": error})
        qs = qs.filter(workspace=workspace)
    elif user and not getattr(user, 'is_superuser', False):
        from research_intelligence.models import WorkspaceMember
        user_ws_ids = WorkspaceMember.objects.filter(user=user).values_list('workspace_id', flat=True)
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
            "exit_metric": ext.exit_metric or ext.get_exit_metric(),
            "validation_status": ext.validation_status,
            "confidence_score": ext.confidence_score,
            "review_required": ext.review_required,
            "fields_data": ext.fields_data,
            "version_info": ext.version_info,
            "created_at": ext.created_at.isoformat() if ext.created_at else None
        })

    return json.dumps(results, indent=2)


def get_paper_extractions_matrix_logic(
    user,
    workspace_id: Optional[str] = None,
    pipeline_run_id: Optional[str] = None,
    process_id: Optional[str] = None,
    screening_status: str = "full_text_passed",
    limit: int = 100
) -> str:
    """
    Returns an aggregated matrix of accepted/screened papers with all their extracted parameters,
    exit metrics, justifications, and scores in a single structured response.
    Eliminates manual joining of papers and extractions.
    """
    from research_intelligence.services import build_paper_extractions_matrix
    payload = build_paper_extractions_matrix(
        user=user,
        workspace_id=workspace_id,
        pipeline_run_id=pipeline_run_id,
        process_id=process_id,
        screening_status=screening_status,
        limit=limit
    )
    return json.dumps(payload, indent=2)


def get_extraction_logic(user, extraction_id: str) -> str:
    """
    Returns full details for a single Extraction object by UUID.
    """
    try:
        ext = Extraction.objects.select_related('workspace', 'paper', 'extraction_definition').get(pk=extraction_id)
    except (Extraction.DoesNotExist, ValueError):
        from research_intelligence.models import ExtractionDefinition
        if ExtractionDefinition.objects.filter(id=extraction_id).exists():
            from .definitions import get_extraction_definition_logic
            return get_extraction_definition_logic(user, extraction_id)
        return json.dumps({"error": f"Extraction '{extraction_id}' not found."})

    workspace, _, error = check_workspace_access(user, str(ext.workspace.id))
    if error:
        return json.dumps({"error": error})

    payload = {
        "id": str(ext.id),
        "extraction_id": str(ext.id),
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
        "exit_metric": ext.exit_metric or ext.get_exit_metric(),
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
