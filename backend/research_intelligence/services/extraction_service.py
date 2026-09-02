"""
Domain Service for dynamic parameter extractions, extractions matrix computation,
and HITL (Human-in-the-Loop) verification.
"""
import logging
from typing import Optional, Dict, Any, List
from django.db.models import F, Q
from django.core.exceptions import ValidationError
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
    papers_qs = Paper.objects.select_related('workspace').prefetch_related(
        'extractions',
        'extractions__extraction_definition',
        'metrics'
    ).all()

    target_pr_id = None
    user_ws_ids = None
    if user and not getattr(user, 'is_superuser', False):
        user_ws_ids = set(Workspace.objects.filter(memberships__user=user).values_list('id', flat=True))
        papers_qs = papers_qs.filter(workspace__id__in=user_ws_ids)

    if process_id:
        if str(process_id).lower() in ('undefined', 'null', ''):
            papers_qs = papers_qs.none()
        else:
            try:
                proc = ResearchAgentProcess.objects.select_related('pipeline_run', 'workspace').get(id=process_id)
                if user_ws_ids is not None and proc.workspace_id not in user_ws_ids:
                    return {"error": f"You do not have access to workspace '{proc.workspace.name}'."}
                if proc.pipeline_run:
                    target_pr_id = proc.pipeline_run.id
                    papers_qs = papers_qs.filter(metrics__pipeline_run=proc.pipeline_run).distinct()
                else:
                    papers_qs = papers_qs.filter(workspace=proc.workspace)
            except (ValueError, TypeError, ValidationError, ResearchAgentProcess.DoesNotExist):
                return {"error": f"ResearchAgentProcess '{process_id}' not found."}
    elif pipeline_run_id:
        if str(pipeline_run_id).lower() in ('undefined', 'null', ''):
            papers_qs = papers_qs.none()
        else:
            import uuid
            try:
                pr_uuid = uuid.UUID(str(pipeline_run_id))
                target_pr_id = pr_uuid
                pr = PipelineRun.objects.filter(pk=pr_uuid).values('workspace_id').first()
                if not pr:
                    return {"error": f"PipelineRun '{pipeline_run_id}' not found."}
                if user_ws_ids is not None and pr['workspace_id'] not in user_ws_ids:
                    return {"error": "You do not have access to this pipeline run."}
                papers_qs = papers_qs.filter(metrics__pipeline_run_id=pr_uuid).distinct()
            except (ValueError, TypeError, ValidationError):
                return {"error": f"Invalid pipeline_run_id '{pipeline_run_id}'."}
    elif workspace_id:
        if str(workspace_id).lower() in ('undefined', 'null', ''):
            papers_qs = papers_qs.none()
        else:
            import uuid
            try:
                ws_uuid = uuid.UUID(str(workspace_id))
                if not Workspace.objects.filter(pk=ws_uuid).exists():
                    return {"error": f"Workspace with ID '{workspace_id}' does not exist."}
                if user_ws_ids is not None and ws_uuid not in user_ws_ids:
                    return {"error": f"You do not have access to workspace '{workspace_id}'."}
                papers_qs = papers_qs.filter(workspace_id=ws_uuid)
            except (ValueError, TypeError, ValidationError):
                return {"error": f"Invalid workspace_id '{workspace_id}'."}

    from django.db.models import Subquery, OuterRef
    from research_intelligence.models import PaperMetric
    if target_pr_id:
        metric_sub = PaperMetric.objects.filter(paper=OuterRef('pk'), pipeline_run_id=target_pr_id)
        papers_qs = papers_qs.annotate(
            annotated_signal_score=Subquery(metric_sub.values('signal_score')[:1]),
            annotated_signal_score_details=Subquery(metric_sub.values('signal_score_details')[:1]),
            annotated_screening_status=Subquery(metric_sub.values('screening_status')[:1]),
            annotated_abstract_screening_reasoning=Subquery(metric_sub.values('abstract_screening_reasoning')[:1]),
            annotated_full_text_screening_reasoning=Subquery(metric_sub.values('full_text_screening_reasoning')[:1]),
            annotated_is_evaluation_benchmark=Subquery(metric_sub.values('is_evaluation_benchmark')[:1]),
            annotated_evaluation_label=Subquery(metric_sub.values('evaluation_label')[:1])
        )
    else:
        metric_sub = PaperMetric.objects.filter(paper=OuterRef('pk')).order_by('-created_at')
        papers_qs = papers_qs.annotate(
            annotated_signal_score=Subquery(metric_sub.values('signal_score')[:1]),
            annotated_signal_score_details=Subquery(metric_sub.values('signal_score_details')[:1]),
            annotated_screening_status=Subquery(metric_sub.values('screening_status')[:1]),
            annotated_abstract_screening_reasoning=Subquery(metric_sub.values('abstract_screening_reasoning')[:1]),
            annotated_full_text_screening_reasoning=Subquery(metric_sub.values('full_text_screening_reasoning')[:1]),
            annotated_is_evaluation_benchmark=Subquery(metric_sub.values('is_evaluation_benchmark')[:1]),
            annotated_evaluation_label=Subquery(metric_sub.values('evaluation_label')[:1])
        )

    if screening_status and screening_status != 'all':
        if target_pr_id:
            if screening_status == 'all_screened':
                papers_qs = papers_qs.filter(metrics__pipeline_run_id=target_pr_id, metrics__screening_status__in=['abstract_passed', 'full_text_passed', 'accepted', 'rejected'])
            elif screening_status in ['all_passed', 'accepted', 'passed', 'full_text_passed']:
                papers_qs = papers_qs.filter(metrics__pipeline_run_id=target_pr_id, metrics__screening_status__in=['abstract_passed', 'full_text_passed', 'accepted'])
            else:
                papers_qs = papers_qs.filter(metrics__pipeline_run_id=target_pr_id, metrics__screening_status=screening_status)
        else:
            if screening_status == 'all_screened':
                papers_qs = papers_qs.filter(metrics__screening_status__in=['abstract_passed', 'full_text_passed', 'accepted', 'rejected'])
            elif screening_status in ['all_passed', 'accepted', 'passed', 'full_text_passed']:
                papers_qs = papers_qs.filter(metrics__screening_status__in=['abstract_passed', 'full_text_passed', 'accepted'])
            else:
                papers_qs = papers_qs.filter(metrics__screening_status=screening_status)

    papers = list(papers_qs.order_by(F('annotated_signal_score').desc(nulls_last=True), '-created_at')[:limit])
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

        score_val = getattr(paper, 'annotated_signal_score', None)
        details_val = getattr(paper, 'annotated_signal_score_details', None)
        status_val = getattr(paper, 'annotated_screening_status', None)
        abstract_reasoning_val = getattr(paper, 'annotated_abstract_screening_reasoning', None)
        full_text_reasoning_val = getattr(paper, 'annotated_full_text_screening_reasoning', None)
        is_benchmark_val = getattr(paper, 'annotated_is_evaluation_benchmark', None)
        eval_label_val = getattr(paper, 'annotated_evaluation_label', None)
        if score_val is None or details_val is None or status_val is None:
            all_m = list(paper.metrics.all())
            pm = None
            if target_pr_id and all_m:
                pm = next((m for m in all_m if str(m.pipeline_run_id) == str(target_pr_id)), None)
            if not pm and all_m:
                pm = sorted(all_m, key=lambda x: x.created_at, reverse=True)[0]
            if pm:
                if score_val is None:
                    score_val = pm.signal_score
                if details_val is None:
                    details_val = pm.signal_score_details
                if status_val is None:
                    status_val = pm.screening_status
                if abstract_reasoning_val is None:
                    abstract_reasoning_val = pm.abstract_screening_reasoning
                if full_text_reasoning_val is None:
                    full_text_reasoning_val = pm.full_text_screening_reasoning
                if is_benchmark_val is None:
                    is_benchmark_val = pm.is_evaluation_benchmark
                if eval_label_val is None:
                    eval_label_val = pm.evaluation_label

        results.append({
            "index": idx,
            "paper_id": str(paper.id),
            "title": paper.title,
            "authors": paper.authors,
            "doi": paper.doi,
            "arxiv_id": paper.arxiv_id,
            "screening_status": status_val or 'pending',
            "abstract_screening_reasoning": abstract_reasoning_val,
            "full_text_screening_reasoning": full_text_reasoning_val,
            "is_evaluation_benchmark": bool(is_benchmark_val) if is_benchmark_val is not None else False,
            "evaluation_label": eval_label_val,
            "signal_score": score_val,
            "signal_score_details": details_val or {},
            "pdf_url": (f"https://arxiv.org/pdf/{paper.arxiv_id}.pdf" if paper.arxiv_id else None) or paper.original_pdf_path,
            "original_pdf_path": paper.original_pdf_path,
            "converted_md_path": paper.converted_md_path,
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
