import json
from typing import Optional
from research_intelligence.models import Extraction, Workspace, Paper, PipelineRun, ResearchAgentProcess


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
    Returns a JSON list of Extraction records (Step 5 outputs).
    Filters by workspace_id, pipeline_run_id, process_id, paper_id, category, or validation_status.
    """
    qs = Extraction.objects.select_related('workspace', 'paper', 'extraction_definition').all()

    if process_id:
        try:
            proc = ResearchAgentProcess.objects.select_related('pipeline_run').get(id=process_id)
            if proc.pipeline_run:
                qs = qs.filter(paper__pipeline_run=proc.pipeline_run)
            else:
                qs = qs.filter(workspace=proc.workspace)
        except (ValueError, ResearchAgentProcess.DoesNotExist):
            return json.dumps({"error": f"ResearchAgentProcess '{process_id}' not found."})
    elif pipeline_run_id:
        qs = qs.filter(paper__pipeline_run_id=pipeline_run_id)
    elif workspace_id:
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
    papers_qs = Paper.objects.select_related('workspace', 'pipeline_run').prefetch_related('extractions', 'extractions__extraction_definition').all()

    if process_id:
        try:
            proc = ResearchAgentProcess.objects.select_related('pipeline_run', 'workspace').get(id=process_id)
            if proc.pipeline_run:
                papers_qs = papers_qs.filter(pipeline_run=proc.pipeline_run)
            else:
                papers_qs = papers_qs.filter(workspace=proc.workspace)
        except (ValueError, ResearchAgentProcess.DoesNotExist):
            return json.dumps({"error": f"ResearchAgentProcess '{process_id}' not found."})
    elif pipeline_run_id:
        papers_qs = papers_qs.filter(pipeline_run_id=pipeline_run_id)
    elif workspace_id:
        papers_qs = papers_qs.filter(workspace_id=workspace_id)
    elif user and not user.is_superuser:
        user_ws_ids = Workspace.objects.filter(memberships__user=user).values_list('id', flat=True)
        papers_qs = papers_qs.filter(workspace__id__in=user_ws_ids)

    if screening_status and screening_status != 'all':
        if screening_status == 'all_screened':
            papers_qs = papers_qs.filter(screening_status__in=['abstract_passed', 'full_text_passed', 'accepted', 'rejected'])
        elif screening_status in ['all_passed', 'accepted']:
            papers_qs = papers_qs.filter(screening_status__in=['abstract_passed', 'full_text_passed', 'accepted'])
        else:
            papers_qs = papers_qs.filter(screening_status=screening_status)

    from django.db.models import F
    papers = list(papers_qs.order_by(F('signal_score').desc(nulls_last=True), '-created_at')[:limit])
    results = []

    for idx, paper in enumerate(papers, 1):
        extractions = list(paper.extractions.all())
        extractions.sort(key=lambda x: (x.extraction_definition.name if x.extraction_definition else x.category))

        metrics_summary = {}
        extractions_list = []

        for ext in extractions:
            def_name = ext.extraction_definition.name if ext.extraction_definition else ext.category
            metric_val = ext.exit_metric or ext.get_exit_metric()
            if def_name:
                metrics_summary[def_name] = metric_val

            extractions_list.append({
                "extraction_id": str(ext.id),
                "definition_name": def_name,
                "exit_metric": metric_val,
                "validation_status": ext.validation_status,
                "confidence_score": ext.confidence_score,
                "fields_data": ext.fields_data
            })

        results.append({
            "index": idx,
            "paper_id": str(paper.id),
            "title": paper.title,
            "authors": paper.authors,
            "doi": paper.doi,
            "arxiv_id": paper.arxiv_id,
            "screening_status": paper.screening_status,
            "signal_score": paper.signal_score,
            "signal_score_details": paper.signal_score_details,
            "pdf_url": (f"https://arxiv.org/pdf/{paper.arxiv_id}.pdf" if paper.arxiv_id else None) or paper.original_pdf_path,
            "original_pdf_path": paper.original_pdf_path,
            "abstract": paper.abstract,
            "metrics_summary": metrics_summary,
            "extractions_count": len(extractions_list),
            "extractions": extractions_list
        })

    scored_vals = [p["signal_score"] for p in results if p.get("signal_score") is not None]
    avg_score = round(sum(scored_vals) / len(scored_vals), 2) if scored_vals else None
    top_score = round(max(scored_vals), 2) if scored_vals else None

    # Build ready-to-use markdown summary for LLM clients so they don't need external parsing scripts
    md_lines = [
        f"### Paper Extractions Matrix ({len(results)} papers, Avg Score: {avg_score or 'N/A'}, Top Score: {top_score or 'N/A'})\n"
    ]
    for p in results[:30]:
        score_str = f"Score: {p['signal_score']}" if p.get('signal_score') is not None else "Unscored"
        metrics_str = ", ".join(f"{k}: {v}" for k, v in p.get("metrics_summary", {}).items())
        md_lines.append(f"{p['index']}. **{p['title']}** [{score_str}]")
        if p.get('authors'):
            md_lines.append(f"   *Authors:* {p['authors']}")
        if p.get('pdf_url'):
            md_lines.append(f"   *PDF:* {p['pdf_url']}")
        if metrics_str:
            md_lines.append(f"   *Extracted Metrics:* {metrics_str}")
        md_lines.append("")
    markdown_summary = "\n".join(md_lines)

    payload = {
        "total_papers": len(results),
        "screening_status_filter": screening_status,
        "avg_signal_score": avg_score,
        "top_signal_score": top_score,
        "markdown_summary": markdown_summary,
        "papers": results
    }
    return json.dumps(payload, indent=2)


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
