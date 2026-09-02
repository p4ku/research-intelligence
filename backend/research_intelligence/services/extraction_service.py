"""
Domain Service for dynamic parameter extractions, extractions matrix computation,
and HITL (Human-in-the-Loop) verification.
"""
import logging
from typing import Optional, Dict, Any, List
from django.db.models import F, Q
from research_intelligence.models import (
    Extraction,
    Workspace,
    Paper,
    PipelineRun,
    ResearchAgentProcess,
    HITLCorrection,
)

logger = logging.getLogger(__name__)


def build_paper_extractions_matrix(
    user,
    workspace_id: Optional[str] = None,
    pipeline_run_id: Optional[str] = None,
    process_id: Optional[str] = None,
    screening_status: str = "full_text_passed",
    limit: int = 100
) -> Dict[str, Any]:
    """
    Computes an aggregated matrix of accepted/screened papers with all their extracted parameters,
    exit metrics, justifications, and scores in a structured dictionary.
    """
    papers_qs = Paper.objects.select_related('workspace', 'pipeline_run').prefetch_related(
        'extractions',
        'extractions__extraction_definition'
    ).all()

    if process_id:
        try:
            proc = ResearchAgentProcess.objects.select_related('pipeline_run', 'workspace').get(id=process_id)
            if proc.pipeline_run:
                papers_qs = papers_qs.filter(Q(pipeline_run=proc.pipeline_run) | Q(reprocessed_runs=proc.pipeline_run)).distinct()
            else:
                papers_qs = papers_qs.filter(workspace=proc.workspace)
        except (ValueError, ResearchAgentProcess.DoesNotExist):
            return {"error": f"ResearchAgentProcess '{process_id}' not found."}
    elif pipeline_run_id:
        if str(pipeline_run_id).lower() in ('undefined', 'null', ''):
            papers_qs = papers_qs.none()
        else:
            import uuid
            try:
                pr_uuid = uuid.UUID(str(pipeline_run_id))
                papers_qs = papers_qs.filter(Q(pipeline_run_id=pr_uuid) | Q(reprocessed_runs=pr_uuid)).distinct()
            except (ValueError, TypeError):
                return {"error": f"Invalid pipeline_run_id '{pipeline_run_id}'."}
    elif workspace_id:
        papers_qs = papers_qs.filter(workspace_id=workspace_id)
    elif user and not getattr(user, 'is_superuser', False):
        user_ws_ids = Workspace.objects.filter(memberships__user=user).values_list('id', flat=True)
        papers_qs = papers_qs.filter(workspace__id__in=user_ws_ids)

    if screening_status and screening_status != 'all':
        if screening_status == 'all_screened':
            papers_qs = papers_qs.filter(screening_status__in=['abstract_passed', 'full_text_passed', 'accepted', 'rejected'])
        elif screening_status in ['all_passed', 'accepted', 'passed', 'full_text_passed']:
            papers_qs = papers_qs.filter(screening_status__in=['abstract_passed', 'full_text_passed', 'accepted'])
        else:
            papers_qs = papers_qs.filter(screening_status=screening_status)

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

    # Build ready-to-use markdown summary for LLM clients
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

    return {
        "total_papers": len(results),
        "screening_status_filter": screening_status,
        "avg_signal_score": avg_score,
        "top_signal_score": top_score,
        "markdown_summary": markdown_summary,
        "papers": results
    }
